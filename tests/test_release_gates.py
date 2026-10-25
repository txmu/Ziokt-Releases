import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import deploy

spec=importlib.util.spec_from_file_location('publisher',Path(__file__).resolve().parents[1]/'tools/publish.py')
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


class GateTests(unittest.TestCase):
    def test_bootstrap_has_no_inherited_identity_or_history_authorization(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(deploy,'preflight',return_value={'overall_pass':True}):
            result=deploy.bootstrap(Path(directory),public_ip='192.0.2.1',service_prefix='node-test')
            conf=Path(result['corix_config']).read_text();gateway=json.loads(Path(result['gateway_config']).read_text());hold=json.loads(Path(result['consensus_hold']).read_text());mcp=json.loads(Path(result['mcp_config']).read_text())
            self.assertIn('seed_peers = \n',conf);self.assertEqual(gateway['peers'],[]);self.assertTrue(hold['active']);self.assertNotIn('authorized_recovery',hold);self.assertNotIn('validator',hold);self.assertFalse(mcp['writes_enabled']);self.assertFalse(result['native_consensus_ready']);self.assertEqual(gateway['service_units']['gateway'],'node-test-gateway')
            before=Path(result['gateway_config']).read_bytes()
            with self.assertRaises(ValueError):deploy.bootstrap(Path(directory),public_ip='192.0.2.2')
            self.assertEqual(Path(result['gateway_config']).read_bytes(),before)

    def test_bootstrap_requires_valid_explicit_endpoints_and_installed_services(self):
        for arguments in ({'seed_peer':'host:7234\nother=value'},{'gateway_peer':'http://user:pass@host:8080'},{'public_ip':'not-an-ip'},{'enable_services':True}):
            with tempfile.TemporaryDirectory() as directory,patch.object(deploy,'preflight',return_value={'overall_pass':True}):
                with self.subTest(arguments=arguments),self.assertRaises((ValueError,TypeError)):
                    deploy.bootstrap(Path(directory),**({'public_ip':'192.0.2.1'}|arguments))

    def test_exact_revision_checks_reject_failure_pending_and_foreign_runs(self):
        def run(id,workflow,state='completed',conclusion='success',repository='txmu/Ziokt'):
            return {'id':id,'workflow_id':workflow,'status':state,'conclusion':conclusion,'head_sha':'a'*40,'head_repository':{'full_name':repository},'html_url':'https://github.com/run/'+str(id)}
        for values in ([run(1,1),run(2,2,conclusion='failure')],[run(1,1),run(2,2,state='queued',conclusion=None)],[run(1,1,repository='other/repo')]):
            with patch.object(publisher,'api',return_value={'workflow_runs':values}),self.assertRaises(ValueError):
                publisher.verified_commit('txmu/Ziokt','a'*40)
        with patch.object(publisher,'api',return_value={'workflow_runs':[run(1,1,conclusion='failure'),run(2,1),run(3,2)]}):
            self.assertEqual(len(publisher.verified_commit('txmu/Ziokt','a'*40)),2)

    def test_failed_ci_installation_is_not_a_valid_selection(self):
        item={'id':'test/artifact','kind':'github-actions-artifact-zip','source_run_conclusion':'failure'}
        with self.assertRaises(ValueError):deploy.plan({'artifacts':[item]},['test/*'])

    def test_unreviewed_dependency_branches_cannot_replace_release_artifacts(self):
        run={'status':'completed','event':'push','head_repository':{'full_name':'txmu/Ziokt'},'conclusion':'success','head_branch':'dependabot/proposed-change','head_sha':'a'*40}
        with tempfile.TemporaryDirectory() as directory,patch.object(publisher,'api',return_value=run),patch.object(publisher,'verified_commit',side_effect=AssertionError('branch must be rejected before collection')):
            with self.assertRaisesRegex(ValueError,'approved release branches'):publisher.publish_run('txmu/Ziokt',1,Path(directory))

class IndependentNodeInputTests(unittest.TestCase):
    def test_each_node_provisions_its_own_content_infrastructure_without_public_writes(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(deploy,'preflight',return_value={'overall_pass':True}):
            configs=[]
            for name in ('first','second'):
                root=Path(directory)/name
                result=deploy.bootstrap(root,connectivity='outbound',service_prefix='test-'+name)
                config=json.loads(Path(result['mcp_config']).read_text())
                self.assertTrue(config['content_fabric']['enabled'])
                self.assertEqual(Path(config['content_fabric']['root']),root/'state/content')
                self.assertEqual(config['content_fabric']['accounts'],{'ziokt-operator':'owner'})
                self.assertIn('content:read',config['cimd_scopes'])
                self.assertNotIn('content:write',config['cimd_scopes'])
                self.assertFalse(config['writes_enabled'])
                configs.append(config)
            self.assertNotEqual(configs[0]['content_fabric']['root'],configs[1]['content_fabric']['root'])

    def test_root_links_port_collisions_and_unpinned_native_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);target=base/'target';target.mkdir();link=base/'link';link.symlink_to(target,target_is_directory=True)
            with self.assertRaises(ValueError):deploy.bootstrap(link,public_ip='192.0.2.1')
            source=base/'native.sh';source.write_text('#!/bin/bash\nexit 0\n')
            with self.assertRaises(ValueError):deploy.bootstrap(base/'node',public_ip='192.0.2.1',native_entrypoint=source,native_sha256='0'*64)
            with self.assertRaises(ValueError):deploy.bootstrap(base/'node',public_ip='192.0.2.1',gateway_port=7234)
            self.assertFalse((base/'node/config').exists())
    def test_installer_requires_revision_wide_gate_not_one_passing_artifact(self):
        item={'id':'test/artifact','kind':'github-actions-artifact-zip','source_run_conclusion':'success'}
        with self.assertRaises(ValueError):deploy.plan({'artifacts':[item]},['test/*'])

class OutboundNodeTests(unittest.TestCase):
    def test_home_node_requires_no_public_ip_discovery_or_advertisement(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(deploy,'detect_public_ip',side_effect=AssertionError('unnecessary public IP probe')):
            result=deploy.bootstrap(Path(directory),connectivity='outbound')
            self.assertIsNone(result['public_ip']);self.assertEqual(result['connectivity']['mode'],'outbound');self.assertFalse(result['connectivity']['public_ip_advertised'])
            text=Path(result['corix_config']).read_text();self.assertIn('public_ip = \n',text);self.assertIn('stun_servers =\n',text)
    def test_public_mode_does_not_accept_private_address_as_public_reachability(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):deploy.bootstrap(Path(directory),connectivity='public',public_ip='192.168.1.8')

class GatewayProbeTests(unittest.TestCase):
    def test_probe_gateway_tool_unconfigured_without_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / 'empty-node'
            isolated.mkdir()
            with patch.object(Path, 'home', return_value=Path(directory) / 'fake-home'):
                res = deploy.probe_gateway_tool(isolated, 'corium_chain_state')
                self.assertEqual(res['status'], 'unconfigured')

    def test_probe_gateway_tool_dynamic_response(self):
        with tempfile.TemporaryDirectory() as directory:
            node_dir = Path(directory) / 'node'
            cfg_dir = node_dir / 'config'
            cfg_dir.mkdir(parents=True)
            (cfg_dir / 'admin_token.key').write_text('secret-test-token\n')
            (cfg_dir / 'admin_token.key').chmod(0o600)
            (cfg_dir / 'gateway.json').write_text(json.dumps({'port': 9999}))
            fake_response_data = {'structuredContent': {'height': 42, 'hash': 'fakehash'}}
            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self,limit): return json.dumps(fake_response_data).encode()
            with patch.object(deploy,'local_opener') as opener:
                opener.return_value.open.return_value=FakeResponse()
                res = deploy.probe_gateway_tool(node_dir, 'corium_chain_state')
                self.assertEqual(res['status'], 'ok')
                self.assertEqual(res['data']['height'], 42)

    def test_empty_root_never_borrows_another_nodes_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);home=base/'home';existing=home/'.local/share/ziokt-node/config';existing.mkdir(parents=True)
            (existing/'admin_token.key').write_text('other-node-secret')
            (existing/'gateway.json').write_text(json.dumps({'port':9999}))
            with patch.object(Path,'home',return_value=home),patch.object(deploy,'local_opener',side_effect=AssertionError('must not query another node')):
                self.assertEqual(deploy.probe_gateway_tool(base/'empty','corium_chain_state')['status'],'unconfigured')

    def test_external_token_path_and_tool_errors_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);node=base/'node';config=node/'config';config.mkdir(parents=True)
            outside=base/'other.key';outside.write_text('other-node-secret');outside.chmod(0o600)
            (config/'gateway.json').write_text(json.dumps({'port':9999,'admin_token':str(outside)}))
            with patch.object(deploy,'local_opener',side_effect=AssertionError('must not use an external token')):
                self.assertEqual(deploy.probe_gateway_tool(node,'corium_chain_state')['status'],'unconfigured')
            token=config/'admin_token.key';token.write_text('this-node-secret');token.chmod(0o600)
            (config/'gateway.json').write_text(json.dumps({'port':9999}))
            with patch.object(deploy,'local_opener') as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"isError":true,"structuredContent":{}}'
                self.assertEqual(deploy.probe_gateway_tool(node,'corium_chain_state')['status'],'unavailable')

    def test_status_uses_own_service_name_and_preserves_acceptance_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);deploy.write(root/'services.json',{'gateway':{'service':'node-two-gateway'}})
            with patch.object(deploy,'probe_gateway_tool',return_value={'status':'ok','data':{}}),patch.object(deploy.subprocess,'run') as run:
                run.return_value.returncode=0;run.return_value.stdout='active\n'
                value=deploy.status(root)
                self.assertTrue(value['services']['gateway']['process_active'])
                self.assertEqual(run.call_args.args[0][-1],'node-two-gateway')
                self.assertTrue(value['local_tools_responding'])
                self.assertEqual(value['business_operational'],'not_assessed')

    def test_local_tool_probe_does_not_follow_redirects(self):
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        forwarded=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302);self.send_header('Location','/stolen');self.end_headers()
            def do_GET(self):
                forwarded.append(self.headers.get('Authorization'));self.send_response(200);self.end_headers()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);worker=threading.Thread(target=server.serve_forever);worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);config=root/'config';config.mkdir();token=config/'admin_token.key';token.write_text('this-node-secret');token.chmod(0o600)
                (config/'gateway.json').write_text(json.dumps({'port':server.server_port}))
                self.assertEqual(deploy.probe_gateway_tool(root,'corium_chain_state')['status'],'unavailable')
                self.assertEqual(forwarded,[])
        finally:server.shutdown();server.server_close();worker.join()


class ProfileTests(unittest.TestCase):
    def test_gateway_profile_requires_matching_green_compiler(self):
        native={'id':'txmu/Ziokt/ziokt-enabled-native-artifacts','source_revision':'a'*40}
        compiler={'id':'txmu/Ziokt/openci-light-compiler-'+'b'*40}
        with patch.object(deploy,'catalog',return_value={'artifacts':[native,compiler]}):
            with self.assertRaisesRegex(ValueError,'matching green'):deploy.profile_plan()

    def test_one_command_bootstrap_installs_before_native_initialization(self):
        import sys
        calls=[]
        with tempfile.TemporaryDirectory() as directory,patch.object(sys,'argv',['deploy.py','--root',directory,'bootstrap','--install','--runtime','--enable-services','--yes']),patch.object(deploy,'preflight',return_value={'overall_pass':True}),patch.object(deploy,'profile_plan',return_value={'sha256':'test'}),patch.object(deploy,'install',side_effect=lambda *a:calls.append('install')),patch.object(deploy,'runtime',side_effect=lambda *a:calls.append('runtime')),patch.object(deploy,'bootstrap',side_effect=lambda *a:calls.append('bootstrap') or {}):
            deploy.main()
        self.assertEqual(calls,['install','runtime','bootstrap'])
