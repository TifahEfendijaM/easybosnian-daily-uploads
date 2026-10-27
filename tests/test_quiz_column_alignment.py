"""Explicit column anchors align; other chosen arrangements remain exact."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian import hybrid
from easybosnian.visual_placement import review_compositions
from test_title_weight_and_visual_answers import TitleWeightAndVisualAnswersTests
import test_visual_provenance as harness


def old_centering(blocks):
 for b in blocks:
  if b['role'] in ('body','example') or b['style']=='split_panel':continue
  right=b['text_inset']+max(b['face'].getlength(row) for row in b['rows']);left=14 if b.get('marker_style')=='triangle' else 20
  b['content_offset']=(b['width']-(right-left))/2-left

class QuizColumnAlignmentTests(unittest.TestCase):
 def sample(self,count):return TitleWeightAndVisualAnswersTests().quiz_plan(count)

 def test_only_identical_x_and_width_on_distinct_rows_share_an_inset(self):
  card,plan=self.sample(4)
  measured=hybrid.measured_plan(card,plan);old_centering(measured);old=[b['content_offset'] for b in measured]
  hybrid.align_visual_answer_content(measured)
  self.assertEqual(measured[0]['content_offset'],measured[2]['content_offset']);self.assertEqual(measured[1]['content_offset'],measured[3]['content_offset'])
  self.assertEqual(measured[0]['content_offset'],min(old[0],old[2]));self.assertEqual(measured[1]['content_offset'],min(old[1],old[3]))
  for change in ('x','width','same_row'):
   blocks=hybrid.measured_plan(card,plan)
   if change=='same_row':
    blocks[2]['y']=blocks[0]['y'];blocks[3]['y']=blocks[1]['y']
   else:
    blocks[2][change]+=1;blocks[3][change]+=1
   expected=copy.deepcopy(blocks);old_centering(expected);hybrid.align_visual_answer_content(blocks)
   self.assertEqual([b['content_offset'] for b in blocks],[b['content_offset'] for b in expected])

 def test_rows_and_two_above_centred_third_render_byte_for_byte_as_before(self):
  for count in (2,3):
   card,plan=self.sample(count);before=copy.deepcopy(plan)
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);photo=root/'photo.png';Image.new('RGB',(1024,1024),'#888888').save(photo)
    with patch('easybosnian.hybrid.align_visual_answer_content',side_effect=old_centering):hybrid.render_hybrid(card,'teal-seaglass',photo,root/'old.jpg',plan)
    result=hybrid.render_hybrid(card,'teal-seaglass',photo,root/'new.jpg',plan)
    self.assertEqual((root/'old.jpg').read_bytes(),(root/'new.jpg').read_bytes());self.assertEqual(result['composition'],before);self.assertEqual(plan,before)

 def test_full_photo_staggered_positions_are_untouched(self):
  card,plan=self.sample(3);card['quiz_format']='other';plan['photo_window']=None
  for b,(x,y) in zip(plan['blocks'],((64,440),(576,720),(320,1000))):b.update(x=x,y=y)
  before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#888888').save(photo)
   with patch('easybosnian.hybrid.align_visual_answer_content',side_effect=AssertionError('Full-photo placement must not be aligned')):
    result=hybrid.render_hybrid(card,'teal-seaglass',photo,root/'card.jpg',plan)
  self.assertEqual(result['composition'],before);self.assertEqual(plan,before)

 def test_prompt_makes_column_intent_and_no_snapping_explicit(self):
  h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
   review_compositions(h.package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']})
  prompt=model.call_args.args[0]
  for rule in ('Exactly matching x/width anchors on distinct rows','deliberately staggered anchors retain their exact proposed cells','Never infer a column from nearly matching coordinates or snap a layout into a grid','Full-background quizzes retain their independent/staggered placement freedom'):
   self.assertIn(rule,prompt)
