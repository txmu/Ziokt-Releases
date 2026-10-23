#!/usr/bin/env python3
"""Preserve existing signed/unsigned client packages in the common release hub."""
import argparse
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import quote
from publish import gh,api,HUB,ROOT,file_sha,prior_catalog


def mirror(repository,tag):
    if repository not in {s['repository'] for s in json.loads((ROOT/'sources.json').read_text())['sources']}:raise ValueError('unapproved source')
    if not re.fullmatch('[A-Za-z0-9_.-]{1,150}',tag):raise ValueError('bounded source tag required')
    source=api(f'repos/{repository}/releases/tags/{quote(tag,safe="")}')
    central='mirror-'+repository.split('/')[1].lower()+'-'+tag
    with tempfile.TemporaryDirectory(prefix='ziokt-mirror-') as temporary:
        area=Path(temporary);records=[]
        for asset in source['assets']:
            name=asset['name']
            if not re.fullmatch('[A-Za-z0-9_. -]{1,180}',name) or not 0<asset['size']<=2*1024**3:raise ValueError('source asset budget or name rejected')
            path=area/name
            result=gh('release','download',tag,'--repo',repository,'--pattern',name,'--output',path)
            digest=file_sha(path)
            if asset.get('digest') and asset['digest']!='sha256:'+digest:raise ValueError('source release asset digest mismatch')
            records.append({'id':repository+'/release/'+name,'kind':'release-asset','name':name,'file':name,'url':f'https://github.com/{HUB}/releases/download/{quote(central,safe="")}/{quote(name,safe="")}', 'bytes':path.stat().st_size,'sha256':digest,'source_repository':repository,'source_release':source['html_url'],'source_release_tag':tag,'source_revision':'not_assessed','source_run_conclusion':'not_assessed','signing':'preserved source package; no additional signing','individual_business_acceptance':'not_assessed','files':[]})
        provenance={'schema':'ziokt.mirrored-release.v1','source_release':source['html_url'],'source_body':source['body'],'artifacts':records}
        (area/'mirror-provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
        notes=area/'central-notes.md';notes.write_text('Original release: '+source['html_url']+'\n\nOriginal package bytes and signing state preserved. No store signature, Apple notarization or additional device acceptance is added. Source release notes are retained in mirror-provenance.json.\n')
        if gh('release','view',central,'--repo',HUB,check=False).returncode:
            gh('release','create',central,'--repo',HUB,'--draft','--title',source['name'],'--notes-file',notes)
            for path in sorted(area.iterdir()):
                if path.is_file() and path!=notes:gh('release','upload',central,path,'--repo',HUB)
            args=['release','edit',central,'--repo',HUB,'--draft=false']
            if source['prerelease']:args+=['--prerelease']
            gh(*args)
        catalog=prior_catalog(area);previous={r['id']:r for r in catalog['artifacts']};previous.update({r['id']:r for r in records});catalog.update(release_repository=HUB,artifacts=sorted(previous.values(),key=lambda r:r['id']))
        path=area/'catalog.json';path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n');checksum=area/'catalog.json.sha256';checksum.write_text(file_sha(path)+'  catalog.json\n');gh('release','upload','catalog',path,checksum,'--repo',HUB,'--clobber')
        print(json.dumps({'release':f'https://github.com/{HUB}/releases/tag/{central}','artifacts':len(records)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--tag',required=True);a=p.parse_args();mirror(a.source,a.tag)
