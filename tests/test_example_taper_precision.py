"""Approved PRIMJER taper and contrast precision, without colour/position changes."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian import hybrid
from easybosnian.render import font,measure
from test_project import reviewed_fixture

class ExampleTaperPrecisionTests(unittest.TestCase):
 def test_soft_edges_begin_earlier_and_crisp_edges_stay_exact(self):
  face=hybrid.serif(34,True);label=font(21,'SemiBold');rows=['Čuvamo svoju riječ.'];top=1000;bottom=max(1040+measure(rows,face)[0],top+measure(['PRIMJER'],label)[0]);source=Image.new('RGBA',(1080,1350),'#b0b0b0')
  for edge in ('standard','sharp','sharp_top'):
   with self.subTest(edge=edge):
    before=source.copy();after=source.copy()
    for module,image,early in ((hybrid,before,False),(hybrid,after,True)):
     _,score,alpha=module.protect_text(image,(64,1040),rows,face,['#fff5eb'],4.5,(20,950,1060,1280),extra=[((64,top),['PRIMJER'],label)],backings=[('#fff5eb',(132,45,8))],fade_style=edge,bottom_padding=18,shade_levels=(240,),minimum_shade=240,early_taper=early)
     self.assertGreaterEqual(score,4.5);self.assertEqual(alpha,240)
    self.assertEqual(before.crop((20,top,1060,bottom+1)).tobytes(),after.crop((20,top,1060,bottom+1)).tobytes())
    for image in (before,after):
     self.assertEqual(image.getpixel((19,1040)),source.getpixel((19,1040)));self.assertEqual(image.getpixel((1060,1040)),source.getpixel((1060,1040)))
     self.assertEqual(image.crop((0,1280,1080,1350)).tobytes(),source.crop((0,1280,1080,1350)).tobytes())
    if edge in ('standard','sharp_top'):
     self.assertNotEqual(before.getpixel((1000,bottom+12)),after.getpixel((1000,bottom+12)))
     self.assertEqual(after.getpixel((1000,bottom+66)),source.getpixel((1000,bottom+66)))
    if edge=='sharp':
     self.assertNotEqual(before.getpixel((1000,top-12)),after.getpixel((1000,top-12)))
     self.assertEqual(before.getpixel((1000,bottom+18)),after.getpixel((1000,bottom+18)))
     self.assertEqual(after.getpixel((1000,bottom+19)),source.getpixel((1000,bottom+19)))
    if edge=='sharp_top':
     self.assertEqual(before.getpixel((1000,top-12)),after.getpixel((1000,top-12)))
     self.assertEqual(after.getpixel((1000,top-13)),source.getpixel((1000,top-13)))

 def test_fine_steps_keep_selected_strength_floors_and_reduce_contrast_overshoot(self):
  face=hybrid.serif(34,True);label=font(21,'SemiBold');rows=['Čuvamo svoju riječ.'];improved=0
  for edge in ('standard','sharp','sharp_top'):
   for floor in (64,128,192):
    for colour,backing,background in (('#fff5eb',(132,45,8),'#b0b0b0'),('#123a35',(242,255,248),'#202020')):
     with self.subTest(edge=edge,floor=floor,colour=colour):
      alphas=[]
      for levels in ((64,90,128,130,170,192,210,240),tuple(range(64,241,2))):
       image=Image.new('RGBA',(1080,1350),background)
       _,score,alpha=hybrid.protect_text(image,(64,1040),rows,face,[colour],4.5,(20,950,1060,1280),extra=[((64,1000),['PRIMJER'],label)],backings=[(colour,backing)],fade_style=edge,bottom_padding=18,shade_levels=levels,minimum_shade=floor,early_taper=True)
       self.assertGreaterEqual(score,4.5);self.assertGreaterEqual(alpha,floor);self.assertLessEqual(alpha,240);alphas.append(alpha)
      self.assertLessEqual(alphas[1],alphas[0]);improved+=alphas[1]<alphas[0]
  self.assertGreater(improved,0)

 def test_production_uses_fine_example_steps_and_keeps_selected_plan_exact(self):
  card=copy.deepcopy(reviewed_fixture()['cards'][2]);source=copy.deepcopy(card)
  plan=hybrid.default_plan(card);plan['blocks'][-1].update(photo_tone='paper_dark',shade_strength='soft')
  before=copy.deepcopy(plan);calls=[];original=hybrid.protect_text
  def observe(image,*args,**kwargs):
   if kwargs.get('allow_fade',True):calls.append(copy.deepcopy(kwargs))
   return original(image,*args,**kwargs)
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'white').save(photo)
   with patch('easybosnian.hybrid.protect_text',side_effect=observe):metrics=hybrid.render_hybrid(card,'forest-cream',photo,root/'result.jpg',plan)
  example=next(c for c in calls if c.get('extra'))
  self.assertTrue(example['early_taper']);self.assertEqual(example['shade_levels'],tuple(range(64,241,2)))
  self.assertEqual(example['minimum_shade'],64)
  title=next(c for c in calls if c.get('feather')==hybrid.TITLE_FADE_FEATHER)
  self.assertEqual(title['shade_levels'],hybrid.TITLE_SHADE_LEVELS)
  self.assertEqual(metrics['composition'],before);self.assertEqual(plan,before);self.assertEqual(card,source)
  self.assertEqual(metrics['example_colour'],'#ffffff');self.assertGreaterEqual(metrics['example_contrast'],4.5)
  self.assertLess(metrics['example_shading'],170);self.assertGreaterEqual(metrics['heading_contrast'],3)
