"""Fresh catalogue cleanup without changing saved renderers or colour freedom."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT,read_json
from easybosnian.designs import (BODY_STYLES,ANSWER_STYLES,REVIEW_BODY_STYLES,REVIEW_ANSWER_STYLES,
 CATEGORY_STYLES,style_label)
from easybosnian.hybrid import default_plan,draw_panel,render_hybrid,validate_current_design
from easybosnian.visual_placement import MODEL_CARD_SCHEMA,CARD_SCHEMA,review_compositions
from easybosnian.design_repair import render_design
from easybosnian.visual_measurements import block_measurements
from easybosnian.success_report import decision_lines
from test_project import reviewed_fixture

class CatalogueCleanupTests(unittest.TestCase):
 def test_fresh_body_and_answer_choices_hide_retired_underline_but_saved_plans_accept_it(self):
  for card in (reviewed_fixture()['cards'][2],reviewed_fixture()['cards'][0]):
   plan=dict(default_plan(card),palette='gold-cream')
   plan['blocks'][0]['style']='overlay_light'
   self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
   self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
   with self.assertRaisesRegex(ValueError,'archive-only'):validate_current_design(card,plan)
   for style in ('minimal_rule','rounded_plain','overlay_dark'):
    plan['blocks'][0]['style']=style
    self.assertFalse(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
    validate_current_design(card,plan)
  self.assertEqual(len(REVIEW_BODY_STYLES),13);self.assertEqual(len(REVIEW_ANSWER_STYLES),15)
  self.assertEqual(CATEGORY_STYLES,('rounded','pill','ribbon','underlined','outlined','tab'))
 def test_every_fresh_quiz_style_has_clean_badges_and_keeps_panel_edge_options(self):
  palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
  block={'role':'A','x':64,'y':80,'width':400,'height':144,'bounds':[64,80,464,224],
         'padding':30,'panel_opacity':100,'panel_tone':'ink_paper','marker_style':'circle'}
  edge_samples={'top_ribbon':(200,82),'minimal_rule':(200,222),'outlined':(64,152),'double_frame':(64,152)}
  accent=Image.new('RGBA',(1,1),palette['accent']).getpixel((0,0))
  self.assertTrue(set(edge_samples)<=set(REVIEW_ANSWER_STYLES))
  for style in REVIEW_ANSWER_STYLES:
   with self.subTest(style=style):
    image=Image.new('RGBA',(540,320),'#808080')
    draw_panel(image,{**block,'style':style},palette)
    self.assertEqual(image.getpixel((80,152)),image.getpixel((82,152)))
    if style in edge_samples:self.assertEqual(image.getpixel(edge_samples[style]),accent)
  old=Image.new('RGBA',(540,320),'#808080')
  draw_panel(old,{**block,'style':'soft_corner'},palette)
  self.assertNotEqual(old.getpixel((80,152)),old.getpixel((82,152)))
  quiz=reviewed_fixture()['cards'][0];plan=dict(default_plan(quiz),palette='gold-cream')
  plan['blocks'][0]['style']='soft_corner'
  self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
  self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
  with self.assertRaisesRegex(ValueError,'soft_corner_plain'):validate_current_design(quiz,plan)
  plan['blocks'][0]['style']='soft_corner_plain'
  self.assertFalse(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
  validate_current_design(quiz,plan)
 def test_plain_rounded_has_smooth_corners_and_no_accent_stripe_in_either_tone(self):
  palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
  for tone,surface in (('ink_paper',palette['panel']),('paper_ink',palette['dark_surface'])):
   block={'role':'body','style':'rounded_plain','x':64,'y':100,'width':952,'height':180,
          'bounds':[64,100,1016,280],'padding':30,'panel_opacity':100,'panel_tone':tone}
   image=Image.new('RGBA',(1080,400),'#808080');draw_panel(image,block,palette)
   expected=Image.new('RGBA',(1,1),surface).getpixel((0,0))
   self.assertEqual(image.getpixel((82,190)),expected)
   self.assertEqual(image.getpixel((540,101)),expected)
   self.assertEqual(image.getpixel((65,101)),(128,128,128,255))
   decorated=Image.new('RGBA',image.size,'#808080');draw_panel(decorated,{**block,'style':'rounded'},palette)
   self.assertNotEqual(image.getpixel((82,190)),decorated.getpixel((82,190)))
 def test_archived_inset_underline_retains_exact_original_alpha_and_drawing(self):
  palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
  block={'role':'body','style':'overlay_light','x':64,'y':100,'width':952,'height':180,
         'bounds':[64,100,1016,280],'padding':30}
  actual=Image.new('RGBA',(1080,400),'#808080');draw_panel(actual,block,palette)
  overlay=Image.new('RGBA',actual.size);rgb=tuple(int(palette['panel'][i:i+2],16) for i in (1,3,5))
  ImageDraw.Draw(overlay).rectangle((64,100,1016,280),fill=(*rgb,235))
  expected=Image.alpha_composite(Image.new('RGBA',actual.size,'#808080'),overlay)
  ImageDraw.Draw(expected).line((94,268,986,268),fill=palette['accent'],width=2)
  self.assertEqual(actual.tobytes(),expected.tobytes())
 def test_retired_underline_recovery_changes_only_that_style_not_siblings_or_copy(self):
  card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high')
  plan['blocks'][0]['style']='overlay_light';before=copy.deepcopy(plan);source=copy.deepcopy(card)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#808080').save(photo)
   metrics,detail=render_design(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p),model_accepted=True,attempt_limit=1)
  self.assertEqual(metrics['composition']['blocks'][0],{**before['blocks'][0],'style':'minimal_rule'})
  self.assertEqual(metrics['composition']['blocks'][1:],before['blocks'][1:])
  self.assertEqual(detail['status'],'partial');self.assertEqual(detail['element_recovery']['fallback'],['body'])
  self.assertEqual(card,source);self.assertEqual(plan,before)
 def test_fit_profiles_and_model_prompt_expose_only_current_panel_choices(self):
  package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='gold-cream') for c in package['cards']}}
  for c in package['cards']:
   for role in ('body',) if c['kind']!='quiz' else ('A',):
    styles=block_measurements(c,role)['measurements_by_style']
    self.assertIn('rounded_plain',styles);self.assertNotIn('overlay_light',styles)
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
   review_compositions(package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in package['cards']})
  prompt=model.call_args.args[0];catalogue=prompt.split(' Design catalogue:',1)[1].split(' Category catalogue:',1)[0]
  parsed=json.loads(catalogue)
  self.assertNotIn('overlay_light',parsed);self.assertIn('rounded_plain',parsed)
  self.assertTrue(parsed['overlay_dark'].startswith('Plain panel:'))
 def test_report_displays_plain_panel_without_renaming_saved_identifier(self):
  self.assertEqual(style_label('overlay_dark'),'Plain panel');self.assertIn('overlay_dark',BODY_STYLES)
  lines=decision_lines({'palette':'gold-cream','design':'hybrid','block_styles':{'body':'overlay_dark'},'answer_badges':{}})
  self.assertTrue(any(line.startswith('Explanation: Plain panel.') for line in lines))
