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
