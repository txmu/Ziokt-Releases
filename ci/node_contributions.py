"""CI acceptance network: independent validators mine and synchronize real NNS blocks."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import time

from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec

NETWORK='ci-independent'


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def prepare(directory):
    if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('acceptance identities are generated on disposable CI only')
    identities=[];keys=[];reservations=[]
    for label in ('seed','client-1','client-2'):
        root=directory/label;identity_dir=root/'corium/etc/corix/networks'/NETWORK
        identity_dir.mkdir(mode=0o700,parents=True)
        key=ec.generate_private_key(ec.SECP256K1());keys.append(key)
        public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode().rstrip('\n')
        identity=hashlib.sha256(public.encode()).hexdigest();name='temp-'+secrets.token_hex(10)
        private_file=identity_dir/'identity.key';private_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));private_file.chmod(0o600)
        public_file=identity_dir/'identity.key.pub';public_file.write_text(public+'\n');public_file.chmod(0o600)
        identities.append({'label':label,'identity':identity,'public_key':public,'domain':name})
        reservations.append({'owner_id':identity,'domains':[name]})
    payload=json.dumps(reservations,separators=(',',':'))
    genesis={'timestamp':int(time.time()),'genesis_validators':[{'public_key':entry['public_key'],'stake':1000} for entry in identities],
             'nomen_genesis_commitment':{'reservations_payload':payload,'signature':keys[0].sign(payload.encode(),ec.ECDSA(hashes.SHA256())).hex()}}
    path=directory/'acceptance-public-genesis.json';path.write_text(json.dumps(genesis,indent=2)+'\n')
    return {'path':path,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'identities':identities}


def core(node,script,*arguments,timeout=180):
    root=Path(node['root'])/'corium';entry=root/'bin/corix_v108.sh'
    command=['bash','-c','source "$1"\nload_config || exit 1\n'+script,'acceptance-node',str(entry),*map(str,arguments)]
    result=subprocess.run(command,env=dict(os.environ,CORIUM_ROOT=str(root),CORIUM_NETWORK_ID_OVERRIDE=NETWORK,PYTHON_CMD=sys.executable),capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise RuntimeError('native acceptance operation failed: '+result.stderr[-2500:])
    return result.stdout


def database(node,kind='blockchain/chain.db'):
    return Path(node['root'])/'corium/var/lib/corix/networks'/NETWORK/kind


def rows(path,query,params=()):
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
    try:return db.execute(query,params).fetchall()
    finally:db.close()


def verify_and_authorize(nodes,material,output):
    genesis=json.loads(material['path'].read_text());commitment=genesis['nomen_genesis_commitment']
    authority=serialization.load_pem_public_key(genesis['genesis_validators'][0]['public_key'].encode())
    authority.verify(bytes.fromhex(commitment['signature']),commitment['reservations_payload'].encode(),ec.ECDSA(hashes.SHA256()))
    expected={(entry['identity'],1000) for entry in material['identities']}
    for node in nodes:
        path=Path(node['corix_config']).parent/'genesis.json'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=material['sha256']:raise RuntimeError('acceptance public genesis pin changed')
        if set(rows(database(node),'SELECT public_key_hash,stake FROM validators'))!=expected:raise RuntimeError('all independent genesis validators must be installed')
        if rows(database(node),'SELECT MAX(height) FROM blocks')!=[(0,)]:raise RuntimeError('fresh acceptance prefix required')
        replay=Path(node['root'])/'acceptance-genesis-replay'
        core(node,'_internal_replay_chain_state 0 "$2"',replay)
        if set(rows(replay/'chain.db','SELECT public_key_hash,stake FROM validators'))!=expected:raise RuntimeError('actual native genesis replay changed validator authority')
        with sqlite3.connect(replay/'forum.db') as db:
            names=set(db.execute('SELECT domain_name,owner_id FROM nns_records').fetchall())
        if names!={(entry['domain'],entry['identity']) for entry in material['identities']}:raise RuntimeError('actual native genesis replay changed NNS ownership')
        hold_path=Path(node['consensus_hold']);hold=json.loads(hold_path.read_text())
        if hold.get('network')!=NETWORK or hold.get('active') is not True:raise RuntimeError('explicit held acceptance genesis required')
        receipt={'schema':'ziokt.acceptance-genesis.v1','network':NETWORK,'genesis_sha256':material['sha256'],
                 'genesis_hash':node['native']['genesis_hash'],'verified_height':0,'native_genesis_replayed':True,
                 'validators':sorted(identity for identity,_ in expected),'operator_identity':node['native']['identity']}
        key=serialization.load_pem_private_key((Path(node['corix_config']).parent/'identity.key').read_bytes(),password=None)
        signature=key.sign(b'Ziokt/acceptance-genesis/v1\0'+canonical(receipt),ec.ECDSA(hashes.SHA256())).hex()
        hold.update(active=False,reason_code='ACCEPTANCE_GENESIS_REPLAY_VERIFIED',acceptance_authorization={'receipt':receipt,'signature':signature})
        temporary=hold_path.with_suffix('.verified');temporary.write_text(json.dumps(hold,indent=2)+'\n');temporary.chmod(0o600);os.replace(temporary,hold_path)
    (output/'verified-acceptance-genesis.json').write_text(json.dumps({'genesis':genesis,'sha256':material['sha256'],'validators':material['identities']},indent=2)+'\n')


def contribute(nodes,material,output):
    verify_and_authorize(nodes,material,output)
    by_identity={node['native']['identity']:node for node in nodes}
    names={entry['identity']:entry['domain'] for entry in material['identities']}
    produced={identity:[] for identity in by_identity};records=[]
    for _ in range(32):
        public=core(nodes[0],'blockchain_get_next_validator').strip()
        match=re.search(r'-----BEGIN PUBLIC KEY-----[\s\S]*?-----END PUBLIC KEY-----',public)
        if match is None:raise RuntimeError('native validator selection did not return its public key')
        identity=hashlib.sha256(match.group().encode()).hexdigest()
        if identity not in by_identity:raise RuntimeError('native round selected a foreign acceptance validator')
        node=by_identity[identity];target=secrets.token_hex(32);payload=json.dumps({'records':[{'domain_name':names[identity],'target_hash':target}]},separators=(',',':'))
        previous=rows(database(nodes[0]),'SELECT MAX(height) FROM blocks')[0][0]
        result=core(node,'tx=$(blockchain_create_transaction nns_update "$2") || exit 1\nblockchain_mine_block || exit 1\nprintf "ACCEPTANCE_TX:%s\\n" "${tx##*$\'\\n\'}"',payload)
        txs=re.findall(r'ACCEPTANCE_TX:([a-f0-9]{64})',result)
        if len(txs)!=1:raise RuntimeError('native NNS transaction identity missing')
        tip=rows(database(node),'SELECT height,hash,validator,transactions FROM blocks ORDER BY height DESC LIMIT 1')[0]
        if tip[0]!=previous+1 or tip[2]!=identity or txs[0] not in json.loads(tip[3]):raise RuntimeError('selected independent validator did not mine a nonempty native block')
        port=11234+nodes.index(node)*3000
        for other in nodes:
            if other is not node and rows(database(other),'SELECT hash FROM blocks ORDER BY height DESC LIMIT 1')[0][0]!=tip[1]:
                core(other,'_blockchain_reorganize_to "$2" 127.0.0.1 "$3"',tip[1],port)
            if rows(database(other),'SELECT hash FROM blocks ORDER BY height DESC LIMIT 1')[0][0]!=tip[1]:raise RuntimeError('native peer history did not converge after real synchronization')
            if rows(database(other,'forum/forum.db'),'SELECT target_hash FROM nns_records WHERE domain_name=?',(names[identity],))!=[(target,)]:raise RuntimeError('peer NNS projection differs from the mined block')
        produced[identity].append(tip[0]);records.append({'height':tip[0],'hash':tip[1],'validator':identity,'transaction':txs[0],'domain':names[identity],'target_hash':target})
        if all(produced.values()):break
    if not all(produced.values()):raise RuntimeError('each of the three independent validators must actually produce at least one nonempty block')
    height=records[-1]['height']
    for node in nodes:
        replay=Path(node['root'])/'acceptance-full-replay';core(node,'_internal_replay_chain_state "$2" "$3"',height,replay,timeout=300)
        expected=rows(database(node,'forum/forum.db'),'SELECT domain_name,owner_id,target_hash FROM nns_records ORDER BY domain_name')
        if rows(replay/'forum.db','SELECT domain_name,owner_id,target_hash FROM nns_records ORDER BY domain_name')!=expected:raise RuntimeError('independent full history replay changed NNS state')
    report={'schema':'ziokt.independent-validator-contributions.v1','network':NETWORK,'validators':[{'identity':identity,'produced_heights':heights} for identity,heights in produced.items()],
            'blocks':records,'nonempty_blocks':len(records),'native_history_synchronized':True,'all_nodes_replayed':True,'registration_cleanup_transactions':False}
    (output/'validator-contributions.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
