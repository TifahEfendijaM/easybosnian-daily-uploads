"""Reverse-edge eligibility does not pick a style or move accepted elements."""
import copy,tempfile,unittest
from pathlib import Path
from PIL import Image
from easybosnian.hybrid import default_plan,heading,validate_current_design,render_hybrid
from easybosnian.design_repair import render_design
from test_project import reviewed_fixture

class ExampleEdgePreferenceTests(unittest.TestCase):
 def plan(self):
  card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high',heading_tone='ink_light')
  plan['blocks'][0]['y']=740;plan['blocks'][-1].update(y=round(heading(card)[2]+32),fade_style='sharp_top')
  return card,plan
 def test_nearby_above_body_allows_all_styles_without_selecting_one(self):
  card,plan=self.plan()
  for edge in ('sharp','standard','sharp_top'):
   candidate=copy.deepcopy(plan);candidate['blocks'][-1]['fade_style']=edge;before=copy.deepcopy(candidate)
   validate_current_design(card,candidate);self.assertEqual(candidate,before)
 def test_reverse_requires_both_nearby_title_and_above_body(self):
  card,plan=self.plan();boundary=round(heading(card)[2])
  for example_y,body_y in ((boundary+100,740),(1000,500),(boundary+99,boundary+20)):
   candidate=copy.deepcopy(plan);candidate['blocks'][-1]['y']=example_y;candidate['blocks'][0]['y']=body_y
   with self.subTest(example_y=example_y,body_y=body_y),self.assertRaisesRegex(ValueError,'Crisp-top PRIMJER shade requires'):validate_current_design(card,candidate)
   for edge in ('standard','sharp'):
    candidate['blocks'][-1]['fade_style']=edge;validate_current_design(card,candidate)
 def test_recovery_changes_only_invalid_orientation_and_legacy_draw_stays_available(self):
  card,plan=self.plan();plan['blocks'][-1]['y']=1080;before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#888888').save(photo)
   draw=lambda p:render_hybrid(card,'forest-cream',photo,root/'card.jpg',p)
   legacy=draw(plan);self.assertEqual(legacy['composition'],before)
   metrics,detail=render_design(card,plan,photo,draw,model_accepted=True,attempt_limit=1)
  expected=copy.deepcopy(before);expected['blocks'][-1]['fade_style']='sharp'
  self.assertEqual(metrics['composition'],expected);self.assertEqual(plan,before)
  self.assertEqual(detail['status'],'partial');self.assertEqual(detail['element_recovery']['fallback'],['example'])
