import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.core import ROOT, PROJECT, REPO

spec = importlib.util.spec_from_file_location('cloudflare_setup', ROOT/'scripts/cloudflare_deploy.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class WorkerSecretBoundaries(unittest.TestCase):
    def fixtures(self, root, project=PROJECT):
        directory=root/'cloudflare'; directory.mkdir()
        (directory/'deployment.json').write_text(json.dumps({
            'project':project,'worker_deployed':True,'free_workers_verified':True,
            'account_id':'account','database_id':'database','kv_id':'images'
        }))
        (directory/'wrangler.toml').write_text(
            f'name = "{setup.NAME}"\naccount_id = "account"\n'
            f'[vars]\nPROJECT_ID = "{PROJECT}"\nGITHUB_REPOSITORY = "{REPO}"\n'
        )

    def test_foreign_deployment_never_reads_auth_or_writes_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); self.fixtures(root,'foreign-project')
            with patch.object(setup,'ROOT',root), patch.object(setup,'verify_repository'), patch.object(setup,'auth_token') as auth, patch.object(setup,'wrangler') as put:
                with self.assertRaises(ValueError): setup.put_worker_secret('GITHUB_DISPATCH_TOKEN','github_pat_test')
                auth.assert_not_called(); put.assert_not_called()

    def test_foreign_worker_bindings_never_receive_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); self.fixtures(root)
            with patch.object(setup,'ROOT',root), patch.object(setup,'verify_repository'), patch.object(setup,'auth_token',return_value='test-auth'), patch.object(setup,'cf',return_value={'bindings':[{'name':'DB','id':'foreign-database'}]}), patch.object(setup,'wrangler') as put:
                with self.assertRaises(ValueError): setup.put_worker_secret('GITHUB_DISPATCH_TOKEN','github_pat_test')
                put.assert_not_called()

    def test_success_requires_provider_read_back_without_printing_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); self.fixtures(root)
            bindings=[{'name':'DB','id':'database'},{'name':'IMAGES','namespace_id':'images'}]
            value='github_pat_test_private_value'; output=io.StringIO()
            with patch.object(setup,'ROOT',root), patch.object(setup,'verify_repository'), patch.object(setup,'auth_token',return_value='test-auth'), patch.object(setup,'cf',side_effect=[{'bindings':bindings},{'bindings':bindings+[{'name':'GITHUB_DISPATCH_TOKEN','type':'secret_text'}]}]), patch.object(setup,'wrangler') as put, contextlib.redirect_stdout(output):
                setup.put_worker_secret('GITHUB_DISPATCH_TOKEN',value)
                put.assert_called_once_with('secret','put','GITHUB_DISPATCH_TOKEN','--config','wrangler.toml',input_text=value)
            self.assertIn('saved privately',output.getvalue())
            self.assertNotIn(value,output.getvalue())


class ScheduleConsistency(unittest.TestCase):
    def test_committed_example_matches_actual_worker(self):
        self.assertEqual(setup.validate_schedule(ROOT/'cloudflare/wrangler.example.toml'),'30 11,12 * * *')

    def fixture(self,directory):
        root=Path(directory);(root/'cloudflare').mkdir()
        (root/'cloudflare/worker.mjs').write_text("if(f.hour!=='13' || f.minute!=='30') return;")
        for name in ('wrangler.toml','wrangler.example.toml'):
            (root/'cloudflare'/name).write_text('[triggers]\ncrons = ["30 11,12 * * *"]\n')
        return root

    def test_real_and_example_must_both_match_dst_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory)
            with patch.object(setup,'ROOT',root):
                self.assertEqual(setup.validate_schedule(),'30 11,12 * * *')
                for name in ('wrangler.toml','wrangler.example.toml'):
                    path=root/'cloudflare'/name;original=path.read_text()
                    path.write_text(original.replace('11,12','10,11'))
                    with self.assertRaisesRegex(ValueError,'clock mismatch'):setup.validate_schedule()
                    path.write_text(original)

    def test_deploy_refuses_mismatch_before_any_provider_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=self.fixture(directory)
            (root/'cloudflare/worker.mjs').write_text("if(f.hour!=='13' || f.minute!=='07') return;")
            with patch.object(setup,'ROOT',root),patch.object(setup.subprocess,'run') as command:
                with self.assertRaisesRegex(ValueError,'clock mismatch'):setup.wrangler('deploy')
                command.assert_not_called()


if __name__=='__main__': unittest.main()
