import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
from easybosnian.hybrid import (default_plan,declared_block,heading,render_hybrid,validate_current_design,
 NONQUIZ_TITLE_MAX_SHADE,NEAR_EXAMPLE_TITLE_MAX_SHADE,TITLE_EXAMPLE_NEAR_GAP)
from easybosnian.design_repair import render_design
from test_project import reviewed_fixture

class TitleWeightAndVisualAnswersTests(unittest.TestCase):
 def test_nonquiz_cap_and_lower_nearby_cap_keep_unshaded_readable_titles(self):
  card=reviewed_fixture()['cards'][2]
  self.assertEqual(NONQUIZ_TITLE_MAX_SHADE,126)
  self.assertLess(NEAR_EXAMPLE_TITLE_MAX_SHADE,NONQUIZ_TITLE_MAX_SHADE)
  card.update(heading='Primjer',body='A short definition.',example='Jedan prirodan primjer.')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#ffffff').save(photo)
   plan=default_plan(card);plan['heading_tone']='ink_light'
   plan['blocks'][0]['y']=700;plan['blocks'][1]['y']=round(heading(card)[2]+32)
   m=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
   self.assertEqual(m['heading_shading'],0);self.assertGreaterEqual(m['heading_contrast'],3)
 def test_busy_photo_cannot_exceed_nearby_limit_and_recovery_keeps_other_elements(self):
  card=reviewed_fixture()['cards'][2];card.update(heading='Primjer',body='A short definition.',example='Jedan prirodan primjer.')
  plan=dict(default_plan(card),confidence='high');plan['blocks'][0]['y']=760;plan['blocks'][1]['y']=round(heading(card)[2]+32)
  original=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';im=Image.new('RGB',(1080,1350),'white');d=ImageDraw.Draw(im)
   for x in range(0,1080,32):d.rectangle((x,0,x+15,1349),fill='black')
   im.save(photo)
   draw=lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p)
   with self.assertRaisesRegex(ValueError,'shade limit'):draw(plan)
   m,detail=render_design(card,plan,photo,draw,model_accepted=True,attempt_limit=1)
   self.assertLessEqual(m['heading_shading'],126);self.assertGreaterEqual(m['heading_contrast'],3)
   self.assertEqual(m['composition']['blocks'][0],original['blocks'][0])
   self.assertGreaterEqual(m['composition']['blocks'][1]['y'],heading(card)[2]+TITLE_EXAMPLE_NEAR_GAP)
   self.assertEqual(detail['status'],'partial');self.assertEqual(detail['element_recovery']['fallback'],['example'])
 def quiz_plan(self,count):
  card=reviewed_fixture()['cards'][0];card['quiz_format']='visual_identification'
  card['options']=(card['options']+[{'label':'D','text':'Kaput'}])[:count]
  plan=default_plan(card);plan['photo_window']={'y':round(heading(card)[2]+28),'height':400,'fit':'contain'}
  start=plan['photo_window']['y']+428
  locations=[(64,start),(576,start),(320,start+155)] if count==3 else [(64,start),(576,start),(64,start+155),(576,start+155)][:count]
  plan['blocks']=[declared_block(card,o['label'],width=440,style='rounded',font_size=36,x=x,y=y) for o,(x,y) in zip(card['options'],locations)]
  return card,plan
 def test_two_three_four_options_and_centred_third_remain_available(self):
  for count in (2,3,4):
   card,plan=self.quiz_plan(count);before=copy.deepcopy(plan)
   validate_current_design(card,plan)
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1024,1024),'#888888').save(photo)
    m=render_hybrid(card,'teal-seaglass',photo,root/'card.jpg',plan)
    self.assertEqual(m['composition'],before);self.assertEqual(len(m['panel_bounds']),count)
    self.assertGreaterEqual(m['body_contrast'],4.5)
    import json
    from easybosnian.core import ROOT
    surface=json.loads((ROOT/'data/design-palettes.json').read_text())['teal-seaglass']['panel']
    image=Image.open(root/'card.jpg').convert('RGB')
    for box in m['panel_bounds']:
     crop=image.crop(tuple(box));diff=ImageChops.difference(crop,Image.new('RGB',crop.size,surface)).convert('L').point(lambda p:255 if p>20 else 0)
     bbox=diff.getbbox();self.assertIsNotNone(bbox)
     # Actual visible badge + glyphs, rather than the invisible panel rectangle,
     # stays centred even when its surface equals the page background.
     self.assertLess(abs((bbox[0]+bbox[2])/2-crop.width/2),7)
 def test_accidental_offsets_and_unequal_clear_gaps_are_rejected(self):
  card,plan=self.quiz_plan(3);plan['blocks'][2]['x']+=35
  with self.assertRaisesRegex(ValueError,'aligned groups'):validate_current_design(card,plan)
  card,plan=self.quiz_plan(4);plan['blocks'][1]['font_size']=40
  with self.assertRaisesRegex(ValueError,'consistent widths and typography'):validate_current_design(card,plan)
  card,plan=self.quiz_plan(3)
  for n,b in enumerate(plan['blocks']):b.update(x=64,width=952,y=700+n*155+(10 if n==2 else 0))
  with self.assertRaisesRegex(ValueError,'consistent spacing'):validate_current_design(card,plan)
 def test_full_photo_quiz_staggering_is_unchanged(self):
  card,plan=self.quiz_plan(3);card['quiz_format']='other';plan['photo_window']=None;plan['blocks'][2]['x']+=35
  validate_current_design(card,plan)
