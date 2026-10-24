"""CI-only: install an already green release into two fresh native node roots.

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
        approved=deploy.plan(catalog,['txmu/Ziokt/ziokt-enabled-native-artifacts'],include=['*.pyz','corix-ziokt.sh'])
        if any(a['source_revision']!=args.source_revision or a.get('all_revision_workflows_passed') is not True for a in approved['artifacts']):raise RuntimeError('only the exact completed green revision may enter independent deployment acceptance')
        for index in range(2):
            root=output/('seed' if index==0 else 'client');deploy.install(root,approved)
            prefix='ziokt-ci-'+('seed' if index==0 else 'client');units.extend(prefix+'-'+name for name in ('gateway','mcp','openci','corium-p2p'))
            options={}
            if index:
                seed=nodes[0];genesis=Path(seed['corix_config']).parent/'genesis.json';certificate=Path(seed['corix_config']).parent/'tls.crt'
                options={'seed_peer':'127.0.0.1:17234','gateway_peer':'http://127.0.0.1:18185','genesis':genesis,'genesis_sha256':deploy.sha(genesis),'seed_certificate':certificate,'seed_certificate_sha256':deploy.sha(certificate)}
            node=deploy.bootstrap(root,network='ci-independent',public_ip=None if index else '127.0.0.1',connectivity='outbound' if index else 'auto',enable_services=True,service_prefix=prefix,p2p_port=17234+index*1000,gateway_port=18185+index*1000,mcp_port=18186+index*1000,openci_port=18768+index*1000,dns_port=15353+index*1000,doh_port=18188+index*1000,**options)
            nodes.append(node)
        if nodes[0]['native']['identity']==nodes[1]['native']['identity']:raise RuntimeError('independent identity separation failed')
        if nodes[0]['native']['genesis_hash']!=nodes[1]['native']['genesis_hash']:raise RuntimeError('shared public genesis differs')
        # Explicit bilateral public certificate pins, never global TLS bypass.
        for source,target,port in [(nodes[0],nodes[1],18234),(nodes[1],nodes[0],17234)]:
            root=Path(source['root'])/'corium';cache=root/'var/lib/corix/p2p/peer_certs';certificate=Path(target['corix_config']).parent/'tls.crt';pin=cache/('127.0.0.1_'+str(port)+'.pem');pin.write_bytes(certificate.read_bytes());pin.chmod(0o600)
            command='source "$1"\nload_config || exit 1\ndht_add_node "$2" ipv4 127.0.0.1 "$3"\ndht_send_message "$2" PING independent-deploy'
            result=subprocess.run(['bash','-c',command,'peer-check',str(root/'bin/corix_v108.sh'),target['native']['identity'],str(port)],env=dict(os.environ,CORIUM_ROOT=str(root),CORIUM_NETWORK_ID_OVERRIDE='ci-independent'),text=True,capture_output=True,timeout=45)
            if result.returncode or 'PONG' not in result.stdout:raise RuntimeError('real signed native peer exchange failed: '+result.stderr[-500:])
        observations=[]
        for index,node in enumerate(nodes):
            with urllib.request.urlopen('http://127.0.0.1:'+str(18185+index*1000)+'/api/gateway/sites',timeout=10) as response:sites=json.load(response)
            if not sites['configured'] or sites['default_resolver']!='node-zdns':raise RuntimeError('own-node ZDNS site resolution unavailable')
            with urllib.request.urlopen('http://127.0.0.1:'+str(18185+index*1000)+'/api/gateway/status',timeout=10) as response:status=json.load(response)
            if status['build']['source_commit']!=args.source_revision:raise RuntimeError('deployed Gateway source identity differs')
            if not json.loads(Path(node['consensus_hold']).read_text())['active']:raise RuntimeError('bootstrap must preserve unverified-history hold')
            observations.append({'identity':node['native']['identity'],'genesis_hash':node['native']['genesis_hash'],'own_gateway':True,'own_zdns':True,'own_mcp':True,'own_openci':True,'unverified_history_consensus_held':True,'connectivity':node['connectivity']})
        (output/'acceptance.json').write_text(json.dumps({'schema':'ziokt.independent-deployment.v1','source_revision':args.source_revision,'catalog_sha256':args.catalog_sha256,'nodes':observations,'signed_native_ping':True,'production_identity_copied':False,'mainnet_consensus_acceptance':False,'physical_failure_domains':False,'native_compilation':False},indent=2)+'\n')
    finally:
        if units:subprocess.run(['systemctl','stop',*units],check=False,capture_output=True)
        if units:subprocess.run(['systemctl','disable',*units],check=False,capture_output=True)


if __name__=='__main__':main()
