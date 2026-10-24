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

class IndependentNodeInputTests(unittest.TestCase):
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
