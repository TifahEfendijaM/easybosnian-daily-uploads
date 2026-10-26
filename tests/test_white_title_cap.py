"""White title protection has its own cap, never leaking into black/quiz/PRIMJER."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from easybosnian.hybrid import default_plan,heading,render_hybrid,NONQUIZ_WHITE_TITLE_MAX_SHADE
from easybosnian.design_repair import render_design
from test_project import reviewed_fixture

PALETTE={'gold-cream':{'ink':'#303030','panel':'#ffffff','accent':'#ffd60a'}}

class WhiteTitleCapTests(unittest.TestCase):
 def word(self):
  card=copy.deepcopy(reviewed_fixture()['cards'][2]);card.update(heading='Primjer',body='A short explanation.',example='Jedan prirodan primjer.')
  plan=dict(default_plan(card),confidence='high',heading_tone='ink_paper')
  plan['blocks'][0]['y']=760;plan['blocks'][1].update(y=1080,photo_tone='paper_dark')
  return card,plan
 def test_white_cap_stops_unreadable_palette_text_but_allows_faint_readable_protection(self):
  self.assertEqual(NONQUIZ_WHITE_TITLE_MAX_SHADE,90)
  card,plan=self.word()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'black').save(photo)
   with patch('easybosnian.hybrid.json.loads',return_value=PALETTE):
    with self.assertRaisesRegex(ValueError,'shade limit'):render_hybrid(card,'gold-cream',photo,root/'bad.jpg',plan)
   self.assertFalse((root/'bad.jpg').exists())
   plan['heading_tone']='ink_light';Image.new('RGB',(1080,1350),'#505050').save(photo)
   m=render_hybrid(card,'gold-cream',photo,root/'good.jpg',plan)
   self.assertGreater(m['heading_shading'],0);self.assertLessEqual(m['heading_shading'],90)
   self.assertEqual(m['heading_backing'],'#ffffff');self.assertGreaterEqual(m['heading_contrast'],3)
 def test_exhausted_white_cap_recovers_heading_without_changing_body_or_example(self):
  card,plan=self.word();before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'black').save(photo)
   with patch('easybosnian.hybrid.json.loads',return_value=PALETTE):
    m,detail=render_design(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'word.jpg',p),model_accepted=True,attempt_limit=1)
   self.assertEqual(detail['element_recovery']['fallback'],['heading'])
   self.assertEqual(m['composition']['blocks'],before['blocks']);self.assertGreaterEqual(m['heading_contrast'],3)
 def test_black_numeric_cap_and_white_quiz_strength_remain_independent(self):
  card,plan=self.word();plan.update(heading_tone='paper_dark',heading_shade='emphasis',heading_opacity=126)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'black').save(photo)
   m=render_hybrid(card,'gold-cream',photo,root/'black.jpg',plan)
   self.assertEqual(m['heading_shading'],126);self.assertEqual(m['heading_backing'],'#000000')
   quiz=copy.deepcopy(reviewed_fixture()['cards'][0]);quiz.update(question='Primjer',quiz_format='other')
   q=dict(default_plan(quiz),heading_tone='ink_paper',heading_shade='stronger')
   with patch('easybosnian.hybrid.json.loads',return_value=PALETTE):m=render_hybrid(quiz,'gold-cream',photo,root/'quiz.jpg',q)
   self.assertEqual(m['heading_backing'],'#ffffff');self.assertGreater(m['heading_shading'],90)
   self.assertGreaterEqual(m['heading_contrast'],3)
 def test_nearby_white_title_keeps_stricter_78_cap(self):
  card,plan=self.word();plan['heading_tone']='ink_light';plan['blocks'][1]['y']=round(heading(card)[2]+32)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';image=Image.new('RGB',(1080,1350),'white');d=ImageDraw.Draw(image)
   for x in range(0,1080,12):d.rectangle((x,0,x+5,1349),fill='black')
   image.save(photo)
   with self.assertRaisesRegex(ValueError,'shade limit'):render_hybrid(card,'gold-cream',photo,root/'near.jpg',plan)
