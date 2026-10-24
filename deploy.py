#!/usr/bin/env python3
"""Checksum-pinned, bounded ecosystem deployment and cross-platform service manager.

Only fixed Ziokt service entrypoints are executed. User data and existing
credentials are never removed. Installing a binary does not activate consensus.
"""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import urlsplit
import zipfile
import xml.etree.ElementTree as ET
REPOSITORY='txmu/Ziokt-Releases'
SERVICES={'gateway':('ziokt.pyz',['gateway','serve']),'mcp':('ziokt.pyz',['mcp','serve']),'content':('ziokt.pyz',[]),'effort':('ziokt.pyz',['effort-web']),'openci':('openci.pyz',[])}


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,value,private=True):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise ValueError('symlink state/config rejected')
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name);stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());stream.flush();os.fsync(stream.fileno())
    temporary.chmod(0o600 if private else 0o644);os.replace(temporary,path)
def valid_repo(value):
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value):raise ValueError('owner/repository required')
    return value

def opener(proxy=None):
    if proxy:
        value=urlsplit(proxy)
        if value.scheme not in {'http','https'} or not value.hostname:raise ValueError('HTTP/HTTPS CONNECT proxy URL required')
    return urllib.request.build_opener(urllib.request.ProxyHandler({'http':proxy,'https':proxy} if proxy else {}))

def fetch(url,destination,expected=None,limit=2*1024**3,proxy=None):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.username or parsed.password:raise ValueError('HTTPS artifact origin required')
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix(destination.suffix+'.partial')
    if temporary.is_symlink():raise ValueError('download symlink rejected')
    total=0;digest=hashlib.sha256()
    try:
        with opener(proxy).open(url,timeout=120) as response,temporary.open('wb') as output:
            if urlsplit(response.url).scheme!='https':raise ValueError('HTTPS downgrade rejected')
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>limit:raise ValueError('download budget exceeded')
                digest.update(chunk);output.write(chunk)
            output.flush();os.fsync(output.fileno())
        if expected is not None and digest.hexdigest()!=expected:raise ValueError('artifact SHA-256 mismatch')
        os.replace(temporary,destination)
    finally:temporary.unlink(missing_ok=True)
    return digest.hexdigest()


def catalog(repo,root,proxy=None,expected=None):
    valid_repo(repo);path=root/'catalog.json'
    fetch(f'https://github.com/{repo}/releases/download/catalog/catalog.json',path,expected,64*1024**2,proxy)
    value=json.loads(path.read_text())
    if value.get('schema')!='ziokt.distribution-catalog.v1' or value.get('release_repository')!=repo:raise ValueError('distribution catalog authority mismatch')
    if type(value.get('artifacts')) is not list or len(value['artifacts'])>10000:raise ValueError('catalog entry budget')
    return value


def plan(catalog_value,selection,include=(),exclude=()):
    chosen=[]
    for item in catalog_value['artifacts']:
        if not any(fnmatch.fnmatchcase(item['id'],pattern) for pattern in selection):continue
        if not re.fullmatch('[a-f0-9]{64}',item['sha256']) or not 0<item['bytes']<=2*1024**3:raise ValueError('artifact integrity declaration invalid')
        files=[f for f in item.get('files',[]) if (not include or any(fnmatch.fnmatchcase(f['path'],p) for p in include)) and not any(fnmatch.fnmatchcase(f['path'],p) for p in exclude)]
        if files:chosen.append({**item,'selected_files':files})
    if not chosen:raise ValueError('no matching product files; inspect the catalog IDs and platform first')
    result={'schema':'ziokt.install-plan.v1','artifacts':chosen,'download_bytes':sum(a['bytes'] for a in chosen),'platform':platform.system().lower(),'architecture':platform.machine(),'consensus_changed':False}
    result['sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest();return result


def unpack(path,destination,members):
    selected={m['path']:m for m in members};seen=set();budget=0
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>100000:raise ValueError('archive file count budget')
        for item in archive.infolist():
            p=PurePosixPath(item.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in item.filename or ':' in item.filename or item.filename in seen:raise ValueError('unsafe or duplicate archive path')
            seen.add(item.filename)
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('archive symlinks rejected')
            budget+=item.file_size
            if budget>8*1024**3 or item.file_size>2*1024**3:raise ValueError('archive expansion budget')
            if item.is_dir() or item.filename not in selected:continue
            if item.file_size!=selected[item.filename]['bytes']:raise ValueError('member size differs from approved manifest')
            target=destination.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as source,target.open('xb') as output:shutil.copyfileobj(source,output,1024*1024)
            target.chmod(0o555 if selected[item.filename].get('executable') else 0o444)
    if set(selected)-seen:raise ValueError('manifest members missing from archive')


def install(root,approved,proxy=None):
    root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink():raise ValueError('installation root cannot be a symlink')
    release=root/'releases'/approved['sha256'];release.parent.mkdir(exist_ok=True)
    if not release.exists():
        with tempfile.TemporaryDirectory(prefix='.install-',dir=release.parent) as temporary:
            stage=Path(temporary);files=stage/'files';files.mkdir()
            for item in approved['artifacts']:
                archive=stage/(item['sha256']+'.zip');fetch(item['url'],archive,item['sha256'],item['bytes']+1024,proxy)
                area=files/item['sha256'];area.mkdir();unpack(archive,area,item['selected_files'])
            write(files/'install-manifest.json',approved)
            os.replace(files,release)
    current=root/'active.json';previous=json.loads(current.read_text()) if current.exists() else None
    write(current,{'schema':'ziokt.active-install.v1','release':str(release),'plan_sha256':approved['sha256'],'previous':previous['release'] if previous else None})
    return {'state':'installed','release':str(release),'files':sum(len(i['selected_files']) for i in approved['artifacts']),'services_enabled':False,'consensus_changed':False}


def active(root):
    state=json.loads((root/'active.json').read_text());release=Path(state['release'])
    if release.parent.resolve()!=(root/'releases').resolve() or release.is_symlink():raise ValueError('active release outside installation')
    return release

def executable(root,name):
    files=[p for p in active(root).rglob(name) if p.is_file()]
    if len(files)!=1:raise ValueError('exactly one '+name+' required; select one portable/native bundle')
    return files[0]


def python_executable(root):
    candidate=root/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    return str(candidate) if candidate.is_file() else sys.executable

def runtime(root,proxy=None):
    candidate=root/'venv'
    if not candidate.exists():subprocess.run([sys.executable,'-m','venv',str(candidate)],check=True)
    command=[python_executable(root),'-m','pip','install','--only-binary=:all:','cryptography==50.0.1']
    if proxy:command+=['--proxy',proxy]
    subprocess.run(command,check=True)


def command(root,service,config=None,port=8768):
    file,args=SERVICES[service];binary=executable(root,file)
    if service=='openci':return [python_executable(root),str(binary),'--root',str(root/'state/openci'),'serve','--port',str(port)]
    if not config:raise ValueError(service+' requires an explicit existing scoped configuration')
    config=Path(config).resolve()
    if config.is_symlink() or not config.is_file():raise ValueError('existing regular service config required')
    if os.name!='nt' and config.stat().st_mode&0o077:raise ValueError('service config must be owner-only')
    if service=='content':return [python_executable(root),'-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('ziokt.content_server',run_name='__main__')",str(binary),'--config',str(config)]
    return [python_executable(root),str(binary),*args,'--config',str(config)]


def persist(root,service,argv):
    name='ziokt-'+service
    if sys.platform.startswith('linux'):
        def escape(value):return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('\n','\\n')+'"'
        system=os.geteuid()==0;directory=Path('/etc/systemd/system') if system else Path.home()/'.config/systemd/user';directory.mkdir(parents=True,exist_ok=True)
        unit=directory/(name+'.service')
        if unit.exists():raise ValueError('existing system service retained; choose an unused service name or review it manually')
        unit.write_text('[Unit]\nDescription=Ziokt '+service+'\nAfter=network-online.target\n[Service]\nType=simple\nExecStart='+' '.join(map(escape,argv))+'\nWorkingDirectory='+escape(str(root))+'\nRestart=on-failure\nRestartSec=5\nUMask=0077\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nReadWritePaths='+escape(str(root))+'\n[Install]\nWantedBy='+('multi-user.target' if system else 'default.target')+'\n')
        control=['systemctl']+([] if system else ['--user']);subprocess.run([*control,'daemon-reload'],check=True);subprocess.run([*control,'enable','--now',name],check=True)
        return str(unit)
    if sys.platform=='darwin':
        directory=Path.home()/'Library/LaunchAgents';directory.mkdir(parents=True,exist_ok=True);path=directory/('org.ziokt.'+service+'.plist')
        if path.exists():raise ValueError('existing launch agent retained')
        path.write_bytes(plistlib.dumps({'Label':'org.ziokt.'+service,'ProgramArguments':argv,'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'StandardOutPath':str(root/(service+'.log')),'StandardErrorPath':str(root/(service+'.error.log'))}))
        subprocess.run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(path)],check=True);return str(path)
    if os.name=='nt':
        task=ET.Element('Task',{'version':'1.2','xmlns':'http://schemas.microsoft.com/windows/2004/02/mit/task'});triggers=ET.SubElement(task,'Triggers');ET.SubElement(ET.SubElement(triggers,'LogonTrigger'),'Enabled').text='true';actions=ET.SubElement(task,'Actions');execute=ET.SubElement(actions,'Exec');ET.SubElement(execute,'Command').text=argv[0];ET.SubElement(execute,'Arguments').text=subprocess.list2cmdline(argv[1:]);ET.SubElement(execute,'WorkingDirectory').text=str(root)
        path=root/(service+'-task.xml');ET.ElementTree(task).write(path,encoding='utf-16',xml_declaration=True)
        subprocess.run(['schtasks','/Create','/TN',name,'/XML',str(path)],check=True);subprocess.run(['schtasks','/Run','/TN',name],check=True);return str(path)
    raise ValueError('persistence backend unsupported on this platform')


def preflight(root, repo=REPOSITORY, proxy=None):
    root = Path(root).expanduser().resolve()
    checks = []
    def record(name, passed, detail=''):
        checks.append({'name': name, 'passed': passed, 'detail': detail})
        return passed
    all_pass = True
    all_pass &= record('python_version', sys.version_info >= (3, 10), f'python {sys.version.split()[0]} (>= 3.10)')
    all_pass &= record('platform_supported', sys.platform in {'linux', 'darwin', 'win32'}, sys.platform)
    arch = platform.machine().lower()
    all_pass &= record('architecture_supported', arch in {'x86_64', 'amd64', 'aarch64', 'arm64'}, arch)
    try:
        if root.is_symlink(): raise ValueError('root cannot be a symlink')
        root.mkdir(parents=True, exist_ok=True)
        probe = root / '.preflight-probe'
        probe.write_text('ok'); probe.unlink()
        writable = True
    except Exception as e:
        writable = False
    all_pass &= record('installation_root_writable', writable, str(root))
    backend_ok = False; backend_name = 'unknown'
    if sys.platform.startswith('linux'):
        system = os.geteuid() == 0
        backend_ok = shutil.which('systemctl') is not None
        backend_name = 'systemd (system)' if system else 'systemd (user)'
    elif sys.platform == 'darwin':
        backend_ok = shutil.which('launchctl') is not None
        backend_name = 'launchd'
    elif os.name == 'nt':
        backend_ok = shutil.which('schtasks') is not None
        backend_name = 'schtasks'
    all_pass &= record('persistence_backend_available', backend_ok, backend_name)
    try:
        valid_repo(repo)
        repo_ok = True
    except ValueError:
        repo_ok = False
    all_pass &= record('release_repository_valid', repo_ok, repo)
    result = {
        'schema': 'ziokt.deploy-preflight.v1',
        'overall_pass': all_pass,
        'checks': checks,
        'root': str(root),
        'repository': repo
    }
    return result


def status(root):
    result={'schema':'ziokt.manager-status.v1','platform':sys.platform,'architecture':platform.machine(),'installed':(root/'active.json').is_file(),'business_operational':'not_assessed','remote_verified':'not_assessed'}
    if result['installed']:result['release']=str(active(root))
    if (root/'services.json').is_file():
        result['services']=json.loads((root/'services.json').read_text())
        for service in result['services']:
            if sys.platform.startswith('linux'):
                control=['systemctl']+([] if os.geteuid()==0 else ['--user']);probe=subprocess.run([*control,'is-active','ziokt-'+service],capture_output=True,text=True,timeout=5);result['services'][service]['process_active']=probe.returncode==0
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path.home()/'.local/share/ziokt-node');sub=p.add_subparsers(dest='action',required=True)
    for name in ('plan','install'):
        q=sub.add_parser(name);q.add_argument('--repository',default=REPOSITORY);q.add_argument('--catalog-sha256');q.add_argument('--artifact',action='append',default=[]);q.add_argument('--profile',choices=['gateway','openci','portable']);q.add_argument('--runtime',action='store_true');q.add_argument('--include',action='append',default=[]);q.add_argument('--exclude',action='append',default=[]);q.add_argument('--proxy');q.add_argument('--confirm');q.add_argument('--yes',action='store_true')
    q=sub.add_parser('enable');q.add_argument('service',choices=SERVICES);q.add_argument('--config',type=Path);q.add_argument('--port',type=int,default=8768)
    q=sub.add_parser('preflight');q.add_argument('--repository',default=REPOSITORY);q.add_argument('--proxy')
    sub.add_parser('status');sub.add_parser('rollback');a=p.parse_args();root=a.root.expanduser().absolute()
    if a.action == 'preflight':
        res = preflight(root, a.repository, a.proxy)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if not res['overall_pass']: raise SystemExit(1)
        return
    if a.action in {'plan','install'}:
        if a.action == 'install':
            pf = preflight(root, a.repository, a.proxy)
            if not pf['overall_pass']:
                raise ValueError('Preflight check failed: ' + json.dumps([c for c in pf['checks'] if not c['passed']], ensure_ascii=False))
        with tempfile.TemporaryDirectory(prefix='ziokt-plan-') as temporary:
            selection=a.artifact or (['txmu/Ziokt/ziokt-enabled-native-artifacts'] if a.profile in {'gateway','openci'} else ['txmu/Ziokt/ziokt-'+('windows-latest' if os.name=='nt' else 'macos-latest' if sys.platform=='darwin' else 'ubuntu-24.04')] if a.profile=='portable' else [])
            if not selection:p.error('choose --profile or explicit --artifact selectors')
            approved=plan(catalog(a.repository,Path(temporary),a.proxy,a.catalog_sha256),selection,a.include,a.exclude)
        if a.action=='plan':print(json.dumps(approved,ensure_ascii=False,indent=2));return
        if not a.yes and a.confirm!=approved['sha256']:raise ValueError('inspect the plan and supply --confirm SHA256, or explicitly use --yes')
        result=install(root,approved,a.proxy)
        if a.runtime:runtime(root,a.proxy)
        print(json.dumps(result));return
    if a.action=='enable':
        if not 1<=a.port<=65535:p.error('port must be 1..65535')
        argv=command(root,a.service,a.config,a.port)
        if a.service=='openci':
            area=root/'state/openci'
            if not (area/'controller.json').exists():subprocess.run([python_executable(root),str(executable(root,'openci.pyz')),'--root',str(area),'init'],check=True)
        definition=persist(root,a.service,argv);file=root/'services.json';entries=json.loads(file.read_text()) if file.exists() else {};entries[a.service]={'definition':definition,'command':argv,'business_operational':'not_assessed'};write(file,entries);print(json.dumps({'service':a.service,'enabled':True,'definition':definition}));return
    if a.action=='rollback':
        state=json.loads((root/'active.json').read_text());previous=state.get('previous')
        if not previous or Path(previous).parent.resolve()!=(root/'releases').resolve() or not Path(previous).is_dir():raise ValueError('previous retained release unavailable')
        write(root/'active.json',{'schema':state['schema'],'release':previous,'previous':state['release']});print(json.dumps({'state':'rolled_back','release':previous,'services_restarted':False}));return
    print(json.dumps(status(root),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as error:print('Deployment failed: '+str(error),file=sys.stderr);raise SystemExit(2)
