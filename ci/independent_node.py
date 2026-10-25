"""CI-only: install an already green release into three fresh native node roots.

Uses actual deploy/bootstrap/systemd/ZDNS/TLS-native APIs. No production keys,
mainnet transactions, public scanning, proof fabrication or native compilation.
"""
import argparse,hashlib,json,os,shlex,sqlite3,subprocess,sys,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import deploy


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--catalog-sha256',required=True);parser.add_argument('--source-revision',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0:raise RuntimeError('disposable root CI host required')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    nodes=[];units=[]
    try:
        catalog=deploy.catalog(deploy.REPOSITORY,output,expected=args.catalog_sha256)
        approved=deploy.plan(catalog,['txmu/Ziokt/ziokt-enabled-native-artifacts','txmu/Ziokt/openci-light-compiler-'+args.source_revision],include=['*.pyz','corix-ziokt.sh','*.py','*.wasm','*.js','manifest.json'])
        if len(approved['artifacts'])!=2:raise RuntimeError('both exact native and compiler bundles required')
        if any(a['source_revision']!=args.source_revision or a.get('all_revision_workflows_passed') is not True for a in approved['artifacts']):raise RuntimeError('only the exact completed green revision may enter independent deployment acceptance')
        for index in range(3):
            label='seed' if index==0 else 'client-'+str(index)
            root=output/label;deploy.install(root,approved)
            prefix='ziokt-ci-'+label;units.extend(prefix+'-'+name for name in ('gateway','mcp','openci','effort','corium-p2p'))
            options={}
            if index:
                seed=nodes[0];genesis=Path(seed['corix_config']).parent/'genesis.json';certificate=Path(seed['corix_config']).parent/'tls.crt'
                options={'seed_peer':'127.0.0.1:11234','gateway_peer':'http://127.0.0.1:18185','genesis':genesis,'genesis_sha256':deploy.sha(genesis),'seed_certificate':certificate,'seed_certificate_sha256':deploy.sha(certificate)}
            node=deploy.bootstrap(root,network='ci-independent',public_ip=None if index else '127.0.0.1',connectivity='outbound' if index else 'auto',enable_services=True,service_prefix=prefix,p2p_port=11234+index*3000,gateway_port=18185+index*1000,mcp_port=18186+index*1000,openci_port=18768+index*1000,dns_port=15353+index*1000,doh_port=18188+index*1000,effort_port=18081+index*1000,**options)
            nodes.append(node)
        if len({node['native']['identity'] for node in nodes})!=3:raise RuntimeError('independent identity separation failed')
        if len({node['native']['genesis_hash'] for node in nodes})!=1:raise RuntimeError('shared public genesis differs')
        # Explicit bilateral public certificate pins, never global TLS bypass.
        pairs=[(source,target,11234+index*3000) for source in nodes for index,target in enumerate(nodes) if source is not target]
        def exchange(source,target,port):
            root=Path(source['root'])/'corium';cache=root/'var/lib/corix/p2p/peer_certs';certificate=Path(target['corix_config']).parent/'tls.crt';pin=cache/('127.0.0.1_'+str(port)+'.pem');pin.write_bytes(certificate.read_bytes());pin.chmod(0o600)
            command='source "$1"\nload_config || exit 1\ndht_add_node "$2" ipv4 127.0.0.1 "$3"\ndht_send_message "$2" PING independent-deploy'
            result=subprocess.run(['bash','-c',command,'peer-check',str(root/'bin/corix_v108.sh'),target['native']['identity'],str(port)],env=dict(os.environ,CORIUM_ROOT=str(root),CORIUM_NETWORK_ID_OVERRIDE='ci-independent'),text=True,capture_output=True,timeout=45)
            if result.returncode or 'PONG' not in result.stdout:raise RuntimeError('real signed native peer exchange failed: '+result.stderr[-500:])
        for source,target,port in pairs:exchange(source,target,port)
        observations=[];content_identities=set()
        for index,node in enumerate(nodes):
            with urllib.request.urlopen('http://127.0.0.1:'+str(18185+index*1000)+'/api/gateway/sites',timeout=10) as response:sites=json.load(response)
            if not sites['configured'] or sites['default_resolver']!='node-zdns':raise RuntimeError('own-node ZDNS site resolution unavailable')
            with urllib.request.urlopen('http://127.0.0.1:'+str(18185+index*1000)+'/api/gateway/status',timeout=10) as response:status=json.load(response)
            if status['build']['source_commit']!=args.source_revision:raise RuntimeError('deployed Gateway source identity differs')
            with urllib.request.urlopen('http://127.0.0.1:'+str(18081+index*1000)+'/api/people/config',timeout=10) as response:effort=json.load(response)
            if effort['network_id']!='ci-independent':raise RuntimeError('effort client network binding differs')
            with urllib.request.urlopen('http://127.0.0.1:'+str(18081+index*1000)+'/openci/v1/light/config',timeout=10) as response:light=json.load(response)
            if light['node_arch'] not in light['targets'] or light['cross_compile'] is not False:raise RuntimeError('own pinned native-architecture compiler unavailable')
            content=deploy.probe_gateway_tool(Path(node['root']),'content_health')
            if content.get('status')!='ok' or content['data'].get('schema')!='ziokt.content-health.v1':raise RuntimeError('own-node Content Fabric is unavailable through Gateway/MCP')
            content_identities.add(content['data']['node'])

            if not json.loads(Path(node['consensus_hold']).read_text())['active']:raise RuntimeError('bootstrap must preserve unverified-history hold')
            observations.append({'identity':node['native']['identity'],'genesis_hash':node['native']['genesis_hash'],'own_gateway':True,'own_zdns':True,'own_mcp':True,'own_openci':True,'own_effort':True,'own_content_fabric':True,'own_compiler_admission':True,'unverified_history_consensus_held':True,'connectivity':node['connectivity']})
        if len(content_identities)!=3:raise RuntimeError('independent Content Fabric identities were not preserved')
        seed_units=[unit for unit in units if unit.startswith('ziokt-ci-seed-')]
        subprocess.run(['systemctl','stop',*seed_units],check=True,capture_output=True)
        exchange(nodes[1],nodes[2],17234);exchange(nodes[2],nodes[1],14234)
        for node in nodes[1:]:
            if deploy.probe_gateway_tool(Path(node['root']),'content_health').get('status')!='ok':raise RuntimeError('surviving node depends on seed content infrastructure')
        subprocess.run(['systemctl','restart',*seed_units],check=True,capture_output=True)
        for node in nodes:
            public=Path(node['corix_config']).parent/'identity.key.pub'
            if hashlib.sha256(public.read_text().rstrip('\n').encode()).hexdigest()!=node['native']['identity']:raise RuntimeError('node identity changed on service restart')
        (output/'acceptance.json').write_text(json.dumps({'schema':'ziokt.independent-deployment.v1','source_revision':args.source_revision,'catalog_sha256':args.catalog_sha256,'nodes':observations,'signed_native_ping':True,'seed_stopped_survivors_exchanged':True,'restarted_identity_preserved':True,'production_identity_copied':False,'mainnet_consensus_acceptance':False,'physical_failure_domains':False,'native_compilation':False},indent=2)+'\n')
    finally:
        if units:subprocess.run(['systemctl','stop',*units],check=False,capture_output=True)
        if units:subprocess.run(['systemctl','disable',*units],check=False,capture_output=True)


if __name__=='__main__':main()
