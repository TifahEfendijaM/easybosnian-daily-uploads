"""Saved source previews stay isolated and never request replacement inference."""
import base64,contextlib,copy,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from PIL import Image
from easybosnian.core import PROJECT,read_json
from easybosnian.cloud_prepare import cloud_run
from easybosnian.preview_sources import stage_saved_preview
from easybosnian.http import SafeError
from easybosnian.photo_reuse import loaded_photos
from easybosnian.hybrid import default_plan
from easybosnian.artwork import artwork
from test_project import reviewed_fixture,accepted_photo_review
from test_success_report import RUN
A='b-'+'a'*32
SOURCE={'batch_id':A,'artwork_id':'r-'+'1'*32}

class SavedPreviewSourcesTests(unittest.TestCase):
 def fixture(self):
  old=reviewed_fixture();old.update(batch_id=A,background_source=SOURCE)
  old['rendered_sources']={'word':{'unused':'stale finished-card cache'}}
  history={'project':PROJECT,'days':[{'batch_id':A,'date':old['date'],'content':old}]}
  raw=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(raw,'JPEG');data=raw.getvalue()
  store=MagicMock();store.history.return_value=history
  store.call.side_effect=lambda method,path:{'image':base64.b64encode(data).decode(),'source':SOURCE,'prompt':next(c['background_prompt'] for c in old['cards'] if path.endswith('/'+c['kind']))}
  return old,history,store,data
 def roots(self,stack,root):
  for module in ('preview_sources','photo_reuse','cli','cloud_prepare'):
   stack.enter_context(patch('easybosnian.'+module+'.ROOT',root))
  stack.enter_context(patch.dict(os.environ,GITHUB_RUN_URL=RUN,MODE='preview',PREVIEW_SOURCE_BATCH_ID=A))
 def test_new_private_identity_preserves_copy_and_original_bytes_without_history_or_research(self):
  old,history,store,data=self.fixture();before=copy.deepcopy(history)
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);self.roots(stack,root)
   stack.enter_context(patch('easybosnian.cli.fit_check'))
   agent=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=AssertionError('no content research')))
   provider=stack.enter_context(patch('easybosnian.artwork.provider',side_effect=AssertionError('no inference')))
   stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
   result=stage_saved_preview(store,history,A,'2026-10-26')
   staged=read_json(root/'build/reviewed-content.secret')['content'];paths=loaded_photos(staged)
   self.assertNotEqual(result['batch_id'],A);self.assertEqual(result['cleanup_batch_id'],None)
   self.assertEqual(result['batch_target'],'none');self.assertEqual(result['source_batch_id'],A)
   for key in ('cards','words','caption','private_review'):self.assertEqual(staged[key],old[key])
   self.assertEqual(staged['date'],'2026-10-26');self.assertNotIn('rendered_sources',staged)
   self.assertEqual(history,before);self.assertEqual({p.read_bytes() for p in paths.values()},{data})
   self.assertTrue(all(c.args[0]=='GET' for c in store.call.call_args_list));self.assertEqual(store.call.call_count,3)
   store.save_content.assert_not_called();store.delete_content.assert_not_called();store.expose.assert_not_called()
   agent.assert_not_called();provider.assert_not_called()
 def test_missing_or_expired_originals_stop_before_staging_without_inference_fallback(self):
  old,history,store,data=self.fixture();store.call.side_effect=SafeError('expired',http_status=404)
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);self.roots(stack,root)
   with self.assertRaisesRegex(ValueError,'No FLUX request'):stage_saved_preview(store,history,A,'2026-10-26')
   self.assertFalse((root/'build/reviewed-content.secret').exists())
   store.put_file.assert_not_called();store.save_content.assert_not_called()
 def test_invalid_missing_duplicate_and_future_sources_are_rejected_before_photo_reads(self):
  old,history,store,data=self.fixture()
  for source,rows in (('garbage',history['days']),('b-'+'c'*32,history['days']),(A,history['days']*2),(A,[dict(history['days'][0],date='2026-10-27')])):
   with self.assertRaisesRegex(ValueError,'Saved preview source'):stage_saved_preview(store,dict(history,days=rows),source,'2026-10-26')
  bad=copy.deepcopy(history);bad['days'][0]['content']['batch_id']='b-'+'d'*32
  with self.assertRaisesRegex(ValueError,'identity differs'):stage_saved_preview(store,bad,A,'2026-10-26')
  store.call.assert_not_called()
 def test_source_selector_is_preview_only_and_routes_without_research_or_live_gate(self):
  old,history,store,data=self.fixture()
  with patch.dict(os.environ,PREVIEW_SOURCE_BATCH_ID=A):
   for mode in ('daily','verify'):
    with self.assertRaisesRegex(ValueError,'preview-only'):cloud_run(mode)
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);self.roots(stack,root)
   stack.enter_context(patch('easybosnian.cloud_prepare.Store',return_value=store))
   stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value='2026-10-26'))
   stack.enter_context(patch('easybosnian.cloud_prepare.check_infrastructure'))
   stack.enter_context(patch('easybosnian.cli.fit_check'))
   agent=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex'))
   live=stack.enter_context(patch('easybosnian.cloud_prepare.require_publishing'))
   stack.enter_context(contextlib.redirect_stdout(io.StringIO()));result=cloud_run('preview',batch_target='all_today')
   self.assertEqual(result['batch_target'],'none');self.assertEqual(result['source_batch_id'],A)
   agent.assert_not_called();live.assert_not_called();store.publications_for_date.assert_not_called()
 def test_source_preview_runs_fresh_design_review_and_stories_without_any_flux_calls(self):
  old,history,store,data=self.fixture()
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);self.roots(stack,root)
   stack.enter_context(patch('easybosnian.cli.fit_check'))
   stack.enter_context(contextlib.redirect_stdout(io.StringIO()));stage_saved_preview(store,history,A,'2026-10-26')
   package=read_json(root/'build/reviewed-content.secret')['content'];paths=loaded_photos(package)
   proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette=p) for c,p in zip(package['cards'],('gold-cream','blue-ice','forest-cream'))}}
   for b in proposal['cards']['quiz']['blocks']:b['panel_opacity']=100
   stack.enter_context(patch('easybosnian.artwork.ROOT',root))
   stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
   stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
   agent=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)))
   provider=stack.enter_context(patch('easybosnian.artwork.provider',side_effect=AssertionError('no FLUX')))
   assets=artwork(store,package,review_images=True,reused_backgrounds=paths,design_attempt_limit=1)
   provider.assert_not_called();agent.assert_called_once();self.assertEqual(len(assets),3)
   self.assertEqual({b['panel_opacity'] for b in assets['quiz']['metrics']['composition']['blocks']},{100})
   self.assertEqual(store.put_file.call_count,6);store.expose.assert_not_called();store.save_content.assert_not_called()
   self.assertTrue(all(item['story_path'].is_file() for item in assets.values()))
 def test_workflow_exposes_one_preview_only_source_field_without_new_jobs_or_credentials(self):
  from easybosnian.core import ROOT
  import yaml
  workflow=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
  self.assertEqual(set(workflow['jobs']),{'run'})
  field=workflow['on']['workflow_dispatch']['inputs']['preview_source_batch_id']
  self.assertEqual(field['type'],'string');self.assertEqual(field['default'],'');self.assertTrue(field['description'].startswith('PREVIEW ONLY'))
  self.assertEqual(workflow['jobs']['run']['env']['PREVIEW_SOURCE_BATCH_ID'],'${{ inputs.preview_source_batch_id }}')
