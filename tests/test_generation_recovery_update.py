"""Failures from October 30 recover without exceeding the shared photo budget."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from easybosnian.http import SafeError
from easybosnian.photo_generation import generate_photo
from easybosnian.photo_quality import repair_prompt,inspect_photos,quality_gate,safe_quality
from test_project import reviewed_fixture
from test_photo_quality import verdict
from test_photo_generation import P

class GenerationRecoveryUpdateTests(unittest.TestCase):
 def conflict(self,**change):
  values={'reason':'ai_call_failed','provider_code':8007,'provider_http_status':409};values.update(change)
  return SafeError('fixed','FLUX generation',409,**values)
 def test_specific_conflict_shares_three_requests_and_never_rewrites_or_changes_copy(self):
  card=reviewed_fixture()['cards'][0];before=copy.deepcopy(card);counts={};events={}
  send=Mock(side_effect=[self.conflict(),self.conflict(),b'image']);rewrite=Mock()
  self.assertEqual(generate_photo(card,send,counts,events,rewrite=rewrite),b'image')
  self.assertEqual(send.call_count,3);rewrite.assert_not_called();self.assertEqual(card,before)
  self.assertEqual(events['quiz'],['upstream_conflict','upstream_conflict','generated'])
  record={'status':'accepted','selected_attempt':1,'reason':'acceptable','attempts':[{'attempt':1,'status':'accepted','reason':'acceptable','quality':90}],'generation_attempts':events['quiz']}
  safe_quality(record)
  send=Mock(side_effect=self.conflict())
  with self.assertRaises(SafeError):generate_photo(card,send,{}, {},rewrite=rewrite)
  self.assertEqual(send.call_count,3)
  for error in (self.conflict(provider_code=9999),self.conflict(reason='ai_free_allocation_exhausted'),self.conflict(provider_http_status=400)):
   send=Mock(side_effect=error)
   with self.assertRaises(SafeError):generate_photo(card,send,{}, {},rewrite=rewrite)
   send.assert_called_once()
 def test_malformed_replacement_is_corrected_without_repeating_photo_inspection(self):
  package=reviewed_fixture();choice=verdict('regenerate');choice['replacement_prompt']='invalid scene'
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'word.jpg';Image.new('RGB',(30,30),'grey').save(path)
   inspector=Mock(side_effect=[{'word':choice},{'word':verdict()}]);generate=Mock()
   with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'prompt':P})) as repair:
    result=quality_gate(package,{'word':path},generate,inspect=inspector)
   self.assertEqual(result['word']['selected_attempt'],2);generate.assert_called_once();repair.assert_called_once()
   self.assertEqual(generate.call_args.args[0]['background_prompt'],P);self.assertTrue(repair.call_args.kwargs['read_only'])
   self.assertNotIn('correct_option',repair.call_args.args[0]);self.assertEqual(inspector.call_count,2)
 def test_prompt_correction_exhaustion_keeps_approved_scene_and_service_error_does_not_retry(self):
  card=reviewed_fixture()['cards'][0]
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'prompt':'invalid'})) as repair:
   self.assertEqual(repair_prompt(card,'invalid'),card['background_prompt']);self.assertEqual(repair.call_count,2)
  with patch('easybosnian.cloud_prepare.run_codex',side_effect=TimeoutError()) as repair:
   with self.assertRaises(TimeoutError):repair_prompt(card,'invalid')
   repair.assert_called_once()
 def test_unused_invalid_replacements_never_abort_accepted_pinned_or_final_photos(self):
  package=reviewed_fixture();choice=verdict();choice['replacement_prompt']='bad'
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'word.jpg';Image.new('RGB',(30,30),'grey').save(path)
   with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'photos':{'word':choice}})):
    self.assertIsNone(inspect_photos(package,{'word':path})['word']['replacement_prompt'])
   choice['status']='regenerate';choice['reason']='major_anatomy_defect'
   with patch('easybosnian.photo_quality.repair_prompt',side_effect=AssertionError('unused repair')):
    for kwargs in ({'pinned':('word',)}, {'attempt_limit':1}):
     generate=Mock();quality_gate(package,{'word':path},generate,inspect=Mock(return_value={'word':choice}),**kwargs)
     generate.assert_not_called()
