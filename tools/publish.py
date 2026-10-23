#!/usr/bin/env python3
"""Transfer trusted completed build artifacts to immutable ecosystem Releases.

No compilation, shell interpolation, implicit success claim, or source tokens in
URLs. The moving catalog points to immutable releases with per-artifact digests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
HUB=os.environ.get('ZIOKT_RELEASE_REPO','txmu/Ziokt-Releases')


def gh(*args,check=True):
    result=subprocess.run(['gh',*map(str,args)],capture_output=True,text=True,timeout=1800 if args[:2]==('release','upload') else 120)
    if check and result.returncode:raise RuntimeError('GitHub operation failed: '+' '.join(str(a) for a in args[:4])+': '+result.stderr[:256])
    return result


def api(path):return json.loads(gh('api',path).stdout)
def file_sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def validate_repository(value):
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value):raise ValueError('owner/repository required')
    return value


def archive_members(path):
    total=0;members=[];names=set()
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist())>100000:raise ValueError('archive file budget')
        for item in archive.infolist():
            name=item.filename
            if name.startswith(('/','\\')) or '\\' in name or ':' in name or any(p in ('..','') for p in name.rstrip('/').split('/')) or name in names:raise ValueError('unsafe artifact member')
            names.add(name);total+=item.file_size
            if total>8*1024**3 or item.file_size>2*1024**3:raise ValueError('archive expansion budget')
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('artifact symlink rejected')
            if not item.is_dir():members.append({'path':name,'bytes':item.file_size,'executable':bool(item.external_attr>>16&0o111)})
    return members


def prior_catalog(directory):
    path=directory/'prior.json'
    result=subprocess.run(['gh','release','download','catalog','--repo',HUB,'--pattern','catalog.json','--output',str(path)],capture_output=True,timeout=120)
    if result.returncode:return {'schema':'ziokt.distribution-catalog.v1','artifacts':[]}
    value=json.loads(path.read_text())
    if value.get('schema')!='ziokt.distribution-catalog.v1':raise ValueError('catalog schema mismatch')
    return value


def publish_run(repository,run_id,directory):
    source=next((s for s in json.loads((ROOT/'sources.json').read_text())['sources'] if s['repository']==repository),None)
    if not source:raise ValueError('source repository is not approved')
    run=api(f'repos/{repository}/actions/runs/{int(run_id)}')
    if run['status']!='completed' or run['event'] not in {'push','workflow_dispatch','schedule','release'} or run['head_repository']['full_name']!=repository:
        raise ValueError('only completed trusted owner build events may publish')
    artifacts=api(f'repos/{repository}/actions/runs/{int(run_id)}/artifacts?per_page=100')['artifacts']
    filters=json.loads((ROOT/'sources.json').read_text())['exclude_fragments']
    artifacts=[a for a in artifacts if not a['expired'] and any(a['name'].startswith(p) for p in source['prefixes']) and not any(f in a['name'] for f in filters)]
    if not artifacts:return []
    tag=repository.split('/')[1].lower()+'-ci-'+str(run_id)
    exists=gh('release','view',tag,'--repo',HUB,check=False)
    if not exists.returncode:
        old=directory/(tag+'-existing');old.mkdir()
        result=gh('release','download',tag,'--repo',HUB,'--pattern','build-manifest.json','--dir',old)
        return json.loads((old/'build-manifest.json').read_text())['artifacts']
    area=directory/tag;area.mkdir();records=[]
    for artifact in artifacts:
        name=artifact['name']
        if not re.fullmatch('[A-Za-z0-9_.() -]{1,150}',name):raise ValueError('unsupported artifact name')
        if not 1<=artifact['size_in_bytes']<=2*1024**3:raise ValueError('artifact compressed size budget')
        path=area/(name+'.zip')
        with path.open('wb') as output:
            process=subprocess.run(['gh','api',f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip'],stdout=output,stderr=subprocess.PIPE,timeout=1800)
        if process.returncode:raise RuntimeError('source artifact transfer failed')
        digest=file_sha(path);declared=artifact.get('digest')
        if declared and declared!='sha256:'+digest:raise ValueError('source Actions artifact digest mismatch')
        members=archive_members(path)
        records.append({'id':repository+'/'+name,'name':name,'kind':'github-actions-artifact-zip','file':path.name,'url':f'https://github.com/{HUB}/releases/download/{quote(tag,safe="")}/{quote(path.name,safe="")}', 'sha256':digest,'bytes':path.stat().st_size,'source_repository':repository,'source_revision':run['head_sha'],'source_run':run['html_url'],'source_run_conclusion':run['conclusion'],'source_artifact_id':artifact['id'],'source_artifact_digest_verified':bool(declared),'individual_business_acceptance':'not_assessed','files':members})
    manifest={'schema':'ziokt.distribution-build.v1','source_repository':repository,'source_revision':run['head_sha'],'source_run':run['html_url'],'source_run_conclusion':run['conclusion'],'artifacts':records,'assurance':'Transfer and source digest verification are separate from build, signing, runtime and business acceptance.'}
    (area/'build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (area/'SHA256SUMS').write_text(''.join(file_sha(p)+'  '+p.name+'\n' for p in sorted(area.iterdir()) if p.is_file()))
    notes=area/'release-notes.md';notes.write_text(f'Source: {repository}@{run["head_sha"]}\n\nCI: {run["html_url"]}\n\nOverall workflow: {run["conclusion"]}. An uploaded artifact is not proof that every test passed. Signing and platform requirements are inherited from the source build; no store signing is added.\n')
    gh('release','create',tag,'--repo',HUB,'--draft','--title',repository+' build '+str(run_id),'--notes-file',notes)
    for path in sorted(area.iterdir()):
        if path.is_file() and path!=notes:gh('release','upload',tag,path,'--repo',HUB)
    options=['release','edit',tag,'--repo',HUB,'--draft=false']
    if run['conclusion']!='success':options+=['--prerelease']
    gh(*options)
    return records


def publish(repository=None,run_id=None,limit=100):
    validate_repository(HUB)
    with tempfile.TemporaryDirectory(prefix='ziokt-release-') as temporary:
        area=Path(temporary);catalog=prior_catalog(area);records={r['id']:r for r in catalog['artifacts']}
        sources=json.loads((ROOT/'sources.json').read_text())['sources']
        for source in sources:
            repo=source['repository']
            if repository and repo!=repository:continue
            runs=[{'id':run_id}] if run_id else api(f'repos/{repo}/actions/runs?per_page={limit}')['workflow_runs']
            for run in reversed(runs):
                try:items=publish_run(repo,run['id'],area)
                except ValueError as error:print('Excluded',repo,run['id'],str(error));continue
                for item in items:records[item['id']]=item
        catalog={'schema':'ziokt.distribution-catalog.v1','release_repository':HUB,'artifacts':sorted(records.values(),key=lambda r:r['id']),'limits':'Per-platform and per-build acceptance is explicit. Missing architectures are not represented as binaries.'}
        path=area/'catalog.json';path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n');sha=area/'catalog.json.sha256';sha.write_text(file_sha(path)+'  catalog.json\n')
        if gh('release','view','catalog','--repo',HUB,check=False).returncode:
            gh('release','create','catalog','--repo',HUB,'--title','Ziokt ecosystem download catalog','--notes','Machine-readable index of immutable ecosystem build Releases. Verify SHA-256 before installation; review each build acceptance and signing state.')
        gh('release','upload','catalog',path,sha,'--repo',HUB,'--clobber')
        print(json.dumps({'repository':HUB,'catalog_artifacts':len(records),'catalog_sha256':file_sha(path)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source');p.add_argument('--run',type=int);p.add_argument('--limit',type=int,default=100);a=p.parse_args()
    if not 1<=a.limit<=100:p.error('limit must be 1..100')
    if a.run and not a.source:p.error('--run requires --source')
    publish(a.source,a.run,a.limit)
