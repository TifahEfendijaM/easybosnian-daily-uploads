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


if __name__=='__main__': unittest.main()
