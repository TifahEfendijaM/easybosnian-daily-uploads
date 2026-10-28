"""Public summaries are approved; identity, credentials and private files stay guarded."""
import copy
import io
import json
import os
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock

import yaml
from easybosnian.core import (REPO,PROJECT,ROOT,REPOSITORY_ID,OWNER_ID,RepositoryIdentityError,
                             valid_repository,verify_repository,gh,private_github_outputs)
from easybosnian.run_reports import collect_report,get_report,save_report,validate_report
from easybosnian.http import SafeError


def repository(private=False):
    return dict(full_name=REPO,id=REPOSITORY_ID,owner={'id':OWNER_ID},private=private,default_branch='main')


class PublicRepositoryTests(unittest.TestCase):
    def test_original_repository_accepts_both_visibilities_but_never_another_identity(self):
        for private in (False,True):
            value=repository(private)
            with patch('easybosnian.core.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(value))):
                self.assertEqual(verify_repository(remote=True),value)
        for changes in ({'id':42},{'id':True},{'owner':{'id':42}},{'full_name':'other/repo'},
                        {'default_branch':'develop'},{'private':None}):
            self.assertFalse(valid_repository({**repository(),**changes}))
        for body in ('invalid','null','[]',json.dumps({'full_name':REPO})):
            with patch('easybosnian.core.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=body)),self.assertRaises(RepositoryIdentityError):
                verify_repository(remote=True)

    def test_public_issue_creation_is_blocked_at_the_github_boundary(self):
        with patch('easybosnian.core.verify_repository',return_value=repository()),patch('easybosnian.core.subprocess.run') as process,self.assertRaises(RepositoryIdentityError):
            gh('issue','create','--repo',REPO)
        process.assert_not_called()

    def test_runner_visibility_is_fail_closed(self):
        for visibility,expected in (('private',True),('public',False),('',False)):
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_VISIBILITY':visibility}):
                self.assertEqual(private_github_outputs(),expected)

    def test_public_failure_is_visible_redacted_and_never_opens_an_issue(self):
        from easybosnian.notify import failure
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.notify.ROOT',Path(temp)),patch('easybosnian.notify.gh') as github,patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_VISIBILITY':'public','TEST_API_KEY':'credential-value'}):
            text=failure('2026-10-24','repository verification',ValueError('Actual fixed diagnostic; credential-value '+('safe '*300)+'END_OF_ERROR'),'nothing published')
            github.assert_not_called();self.assertIn('Actual fixed diagnostic',text)
            self.assertIn('Failed stage: repository verification',text)
            self.assertIn('END_OF_ERROR',text)
            self.assertNotIn('credential-value',text)
            self.assertEqual(text,(Path(temp)/'build/failure.txt').read_text())

    def test_bootstrap_identity_failure_is_not_mislabeled_as_chatgpt_auth(self):
        from easybosnian.cloud_prepare import main
        with patch('sys.argv',['cloud_prepare','bootstrap']),patch('easybosnian.cloud_prepare.bootstrap',side_effect=RepositoryIdentityError('mismatch')),patch('easybosnian.cloud_prepare.failure',return_value='safe') as failure,redirect_stdout(io.StringIO()),self.assertRaisesRegex(RuntimeError,'repository verification'):
            main()
        self.assertEqual(failure.call_args.args[1],'repository verification')

    def test_public_summary_includes_approved_prompts_without_private_drafts(self):
        from easybosnian.success_report import content_data
        from test_project import reviewed_fixture
        package=reviewed_fixture();run='https://github.com/'+REPO+'/actions/runs/123'
        source=content_data(package,run)
        source['private_review']='private answer key'
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_RUN_URL':run,'GITHUB_REPOSITORY_VISIBILITY':'public','GITHUB_STEP_SUMMARY':str(Path(temp)/'summary.md')}):
            previous=Path.cwd()
            try:
                os.chdir(temp);directory=Path('build')/package['date'];directory.mkdir(parents=True)
                (directory/'report-source.json').write_text(json.dumps(source))
                Path('build/failure.txt').write_text('Failed stage: FLUX generation\nError: provider code 8007; content-safety rejection\nPublication: nothing published\nNext step: inspect the prompt\n')
                Path('build/reviewed-content.secret').write_text('private draft example')
                output=io.StringIO()
                with redirect_stdout(output):runpy.run_path(str(ROOT/'scripts/action_summary.py'))
                summary=Path('summary.md').read_text()
                for card in package['cards']:self.assertIn(card['background_prompt'],summary)
                self.assertIn('Visual decisions not available',summary)
                self.assertIn('### Failure details',summary)
                self.assertIn('provider code 8007; content-safety rejection',summary)
                self.assertIn('Publication: nothing published',summary)
                for private in ('private draft example','private answer key'):
                    self.assertNotIn(private,summary);self.assertNotIn(private,output.getvalue())
                self.assertEqual(summary,Path('build/run-summary.md').read_text())
            finally:os.chdir(previous)

    def test_public_failure_summary_preserves_the_entire_report_and_redacts_credentials(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_VISIBILITY':'public','GITHUB_STEP_SUMMARY':str(Path(temp)/'summary.md'),'TEST_API_KEY':'credential-value'}):
            previous=Path.cwd()
            try:
                os.chdir(temp);Path('build').mkdir()
                Path('build/failure.txt').write_text('Failed stage: cloud ChatGPT research/review\nError: '+('safe detail '*150)+'credential-value\nPublication: nothing published\nNext step: END_OF_COMPLETE_REPORT\n')
                output=io.StringIO()
                with redirect_stdout(output):runpy.run_path(str(ROOT/'scripts/action_summary.py'))
                summary=Path('summary.md').read_text()
                self.assertIn('END_OF_COMPLETE_REPORT',summary)
                self.assertIn('Failed stage: cloud ChatGPT research/review',summary)
                self.assertGreater(len(summary),1500)
                self.assertIn('[REDACTED]',summary)
                self.assertNotIn('credential-value',summary);self.assertNotIn('credential-value',output.getvalue())
            finally:os.chdir(previous)

    def test_public_success_report_appends_approved_details(self):
        from easybosnian.success_report import write_report,report_data
        from test_project import reviewed_fixture
        from test_success_report import results
        package=reviewed_fixture();package['private_review']='private answer key'
        data=report_data(package,results(),'https://github.com/'+REPO+'/actions/runs/123')
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.success_report.ROOT',Path(temp)),patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_VISIBILITY':'public','GITHUB_STEP_SUMMARY':str(Path(temp)/'summary.md')}):
            directory=write_report(data)
            summary=(Path(temp)/'summary.md').read_text()
            self.assertIn((directory/'success-report.md').read_text(),summary)
            self.assertIn('successful-run report',summary)
            for card in package['cards']:self.assertIn(card['background_prompt'],summary)
            self.assertNotIn('private answer key',summary)

    def test_workflow_requires_owner_dispatch_on_original_main_and_never_uploads_public_artifacts(self):
        workflow=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
        job=workflow['jobs']['run'];gate=job['if']
        for value in ('1401814933','50710040',"'workflow_dispatch'","'refs/heads/main'"):self.assertIn(value,gate)
        self.assertIn('github.event.repository.visibility',job['env']['GITHUB_REPOSITORY_VISIBILITY'])
        artifact=next(s for s in job['steps'] if s.get('uses')=='actions/upload-artifact@v4')
        self.assertIn('github.event.repository.private == true',artifact['if'])
        archive=next(s for s in job['steps'] if s.get('run')=='python -m easybosnian.run_reports save')
        self.assertIn('always()',archive['if']);self.assertNotIn('pull_request_target',str(workflow))


class ProtectedRunReportTests(unittest.TestCase):
    def test_report_collects_only_allowed_files_and_not_credential_symlinks(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.run_reports.ROOT',Path(temp)):
            build=Path(temp)/'build';batch=build/('b-'+'a'*32);batch.mkdir(parents=True)
            (batch/'image-placement-result.json').write_text('{"cards":{}}')
            (build/'run-summary.md').write_text('approved report')
            (build/'reviewed-content.secret').write_text('private answer key')
            (build/'preparation-context.json').write_text('private context')
            (batch/'result.json').symlink_to(build/'reviewed-content.secret')
            value=collect_report('123','daily')
            self.assertEqual(set(value['files']),{'run-summary.md',batch.name+'/image-placement-result.json'})
            self.assertNotIn('answer key',str(value))
            store=MagicMock();store.call.return_value={'stored':True};save_report(store,'123','daily')
            self.assertEqual(store.call.call_args.args[:2],('PUT','/v1/run-reports/123'))
            store.call.assert_called_once()

    def test_wrong_identity_traversal_secret_paths_and_oversize_are_rejected(self):
        base={'project':PROJECT,'run_id':'123','mode':'daily','files':{}}
        for changes in ({'project':'other'},{'run_id':'124'},{'files':{'../auth.json':'secret'}},
                        {'files':{'reviewed-content.secret':'secret'}},{'files':{'run-summary.md':'x'*2_000_001}}):
            with self.subTest(changes=list(changes)),self.assertRaises(ValueError):validate_report({**base,**changes},'123')

    def test_missing_report_is_legacy_but_other_failures_never_retry(self):
        store=MagicMock();store.call.side_effect=SafeError('missing',http_status=404)
        self.assertIsNone(get_report(store,'123'));store.call.assert_called_once()
        store.reset_mock();store.call.side_effect=SafeError('unavailable',http_status=503)
        with self.assertRaises(SafeError):get_report(store,'123')
        store.call.assert_called_once()

    def test_recent_design_context_uses_private_metadata_without_artifact_reads(self):
        from easybosnian.visual_history import recent_choices
        from test_retained_visual_history import fixture,run
        row,placement,files=fixture(palette='cherry-lime')
        report={'mode':'daily','files':files};store=MagicMock()
        store.history.return_value={'project':PROJECT,'days':[row]}
        with patch('easybosnian.store.Store',return_value=store),patch('easybosnian.visual_history.gh',return_value=json.dumps({'workflow_runs':[run(123)]})) as github,patch('easybosnian.run_reports.get_report',return_value=report),patch('easybosnian.visual_history.gh_binary') as archive:
            recent,status=recent_choices()
        self.assertEqual(status,'available');self.assertEqual(recent[0]['palette_observations'],['cherry-lime']*3);github.assert_called_once()
        archive.assert_not_called()
