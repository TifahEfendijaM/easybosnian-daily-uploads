"""Confirmed NSFW scene revision is the sole new provider retry exception."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from easybosnian.http import SafeError
from easybosnian.photo_generation import generate_photo,rewrite_rejected_scene
from easybosnian.photo_quality import quality_gate,safe_quality
from test_project import reviewed_fixture
from test_photo_quality import verdict

P='Photorealistic photograph of a wooden table with a ceramic bowl in a sunlit kitchen. Natural light and realistic textures. No text, no lettering, no logos.'
Q=P.replace('ceramic bowl','small ceramic cup')
def refusal(reason='ai_content_rejected',stage='FLUX generation'):
 return SafeError('Fixed safe reason',stage,409,reason=reason,provider_code=8007,provider_http_status=400)

class PhotoGenerationTests(unittest.TestCase):
 def test_confirmed_refusal_rewrites_once_then_returns_image_and_preserves_copy(self):
  card=reviewed_fixture()['cards'][0];before=copy.deepcopy(card);counts={};events={}
  send=Mock(side_effect=[refusal(),b'image']);rewrite=Mock(return_value=P)
  self.assertEqual(generate_photo(card,send,counts,events,rewrite=rewrite),b'image')
  self.assertEqual(counts,{'quiz':2});self.assertEqual(events,{'quiz':['content_rejected','generated']})
  self.assertEqual(card,{**before,'background_prompt':P});rewrite.assert_called_once_with(card)
 def test_three_total_requests_and_no_rewrite_after_last_refusal(self):
  card=reviewed_fixture()['cards'][0];counts={};events={};send=Mock(side_effect=refusal());rewrite=Mock(side_effect=[P,Q])
  with self.assertRaises(SafeError):generate_photo(card,send,counts,events,rewrite=rewrite)
  self.assertEqual(send.call_count,3);self.assertEqual(rewrite.call_count,2);self.assertEqual(counts['quiz'],3)
 def test_service_unknown_quota_capacity_auth_and_rewriter_failures_never_retry(self):
  for reason in ('ai_call_failed','ai_capacity_exceeded','ai_free_allocation_exhausted',None):
   send=Mock(side_effect=refusal(reason));rewrite=Mock()
   with self.assertRaises(SafeError):generate_photo(reviewed_fixture()['cards'][0],send,{}, {},rewrite=rewrite)
   send.assert_called_once();rewrite.assert_not_called()
  for error in (TimeoutError(),refusal(stage='storage')):
   send=Mock(side_effect=error);rewrite=Mock()
   with self.assertRaises(type(error)):generate_photo(reviewed_fixture()['cards'][0],send,{}, {},rewrite=rewrite)
   send.assert_called_once();rewrite.assert_not_called()
  send=Mock(side_effect=refusal());rewrite=Mock(side_effect=TimeoutError())
  with self.assertRaises(TimeoutError):generate_photo(reviewed_fixture()['cards'][0],send,{}, {},rewrite=rewrite)
  send.assert_called_once();rewrite.assert_called_once()
 def test_unchanged_or_invalid_revision_never_sends_again(self):
  for value in (None,'bad prompt',reviewed_fixture()['cards'][0]['background_prompt']):
   send=Mock(side_effect=refusal());rewrite=Mock(return_value=value)
   with self.assertRaises(ValueError):generate_photo(reviewed_fixture()['cards'][0],send,{}, {},rewrite=rewrite)
   send.assert_called_once()
 def test_shared_budget_with_defect_generation_and_best_candidate_retained(self):
  package=reviewed_fixture();card=package['cards'][1];counts={'lesson':2};events={'lesson':['content_rejected','generated']}
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'lesson.jpg';Image.new('RGB',(1080,1350),'red').save(path);before=path.read_bytes()
   send=Mock(side_effect=refusal());rewrite=Mock()
   def generate(card,path):
    try:generate_photo(card,send,counts,events,rewrite=rewrite)
    except SafeError as e:
     if e.reason=='ai_content_rejected' and counts['lesson']==3:return False
     raise
   result=quality_gate(package,{'lesson':path},generate,inspect=Mock(return_value={'lesson':verdict('regenerate',70)}))['lesson']
   result['generation_attempts']=events['lesson'];safe_quality(result)
   self.assertEqual(result['status'],'best_effort');self.assertEqual(path.read_bytes(),before)
   self.assertEqual(counts['lesson'],3);send.assert_called_once();rewrite.assert_not_called()
 def test_rewriter_is_readonly_scene_only_and_receives_no_private_answer_key(self):
  card=reviewed_fixture()['cards'][0]
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'prompt':P})) as child:
   self.assertEqual(rewrite_rejected_scene(card),P)
  self.assertTrue(child.call_args.kwargs['read_only']);self.assertNotIn('correct_option',child.call_args.args[0])
  self.assertNotIn('images',child.call_args.kwargs)
  for value in ({'prompt':P,'extra':'bad'},{'prompt':card['background_prompt']}):
   with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(value)),self.assertRaises(ValueError):rewrite_rejected_scene(card)
 def test_artwork_revisions_share_budget_and_save_selected_prompt_source_and_report(self):
  import io,contextlib
  from unittest.mock import MagicMock
  from easybosnian.artwork import artwork
  from easybosnian.hybrid import default_plan
  from easybosnian.core import read_json
  package=reviewed_fixture();package['batch_id']='b-'+'a'*32
  stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG');raw=stream.getvalue()
  provider=MagicMock();provider.generate.side_effect=[refusal(),raw,raw,raw,refusal()]
  first={'quiz':verdict('regenerate',70),'lesson':verdict(),'word':verdict()}
  plans={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='burgundy-oat') for c in package['cards']}}
  with tempfile.TemporaryDirectory() as tmp,contextlib.ExitStack() as stack:
   root=Path(tmp);store=MagicMock()
   stack.enter_context(patch('easybosnian.artwork.ROOT',root))
   stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
   rewrite=stack.enter_context(patch('easybosnian.photo_generation.rewrite_rejected_scene',return_value=P))
   inspect=stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',return_value=first))
   stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
   stack.enter_context(patch('easybosnian.visual_placement.review_compositions',return_value=(plans,'reviewed')))
   assets=artwork(store,package,review_images=True)
   self.assertEqual(provider.generate.call_count,5);rewrite.assert_called_once();inspect.assert_called_once()
   calls=provider.generate.call_args_list;quiz_calls=[call for call in calls if call.args[2]=='quiz']
   self.assertEqual(len(quiz_calls),3);self.assertEqual(len({call.kwargs['artwork_id'] for call in quiz_calls}),3)
   self.assertEqual(package['cards'][0]['background_prompt'],P)
   self.assertEqual(package['background_sources']['quiz']['artwork_id'],quiz_calls[1].kwargs['artwork_id'])
   quality=read_json(root/'build'/package['batch_id']/'photo-quality-result.json')['cards']['quiz']
   self.assertEqual(quality['status'],'best_effort');self.assertEqual(quality['generation_attempts'],['content_rejected','generated','content_rejected'])
   safe_quality(quality);store.save_content.assert_not_called();store.expose.assert_not_called()
   self.assertEqual(set(assets),{'quiz','lesson','word'})
 def test_generation_diagnostics_accept_only_fixed_enums_and_consistent_counts(self):
  value={'status':'accepted','selected_attempt':1,'reason':'acceptable','attempts':[{'attempt':1,'status':'accepted','reason':'acceptable','quality':90}]}
  for events in (['generated'],['content_rejected','generated'],['content_rejected','content_rejected','generated']):
   self.assertEqual(safe_quality(dict(value,generation_attempts=events))['generation_attempts'],events)
  for events in ([],['private prose'],['generated','generated'],['content_rejected']):
   with self.assertRaises(ValueError):safe_quality(dict(value,generation_attempts=events))
