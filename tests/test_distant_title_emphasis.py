"""Distance-scoped decorative title intent, without relaxing shade safety."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.hybrid import (default_plan,editorial_plan,heading,measured_plan,render_hybrid,
 title_example_proximity,TITLE_EXAMPLE_NEAR_GAP,TITLE_SHADE_LEVELS,NONQUIZ_TITLE_MAX_SHADE)
from easybosnian.visual_placement import RESULT_SCHEMA,review_compositions
from easybosnian.design_repair import render_design
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import decision_lines
from test_project import reviewed_fixture

class DistantTitleEmphasisTests(unittest.TestCase):
 def card_plan(self,kind='word',near=False,intent='gentle'):
  card=copy.deepcopy(next(c for c in reviewed_fixture()['cards'] if c['kind']==kind))
  card.update(heading='Primjer',body='A short explanation.',example='Jedan prirodan primjer.')
  plan=dict(default_plan(card),confidence='high',heading_shade=intent,heading_tone='paper_dark')
  plan['blocks'][0]['y']=760;plan['blocks'][1]['y']=round(heading(card)[2]+32) if near else 1080
  plan['blocks'][1]['photo_tone']='paper_dark'
  return card,plan
 def test_distant_can_request_real_shading_on_readable_text_in_both_neutral_directions(self):
  for kind in ('lesson','word'):
   for tone,bg in (('paper_dark','#202020'),('ink_light','#eeeeee')):
    card,plan=self.card_plan(kind);plan['heading_tone']=tone;plan['blocks'][1]['photo_tone']=tone
    original=copy.deepcopy(plan);source=copy.deepcopy(card)
    with tempfile.TemporaryDirectory() as tmp:
     root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),bg).save(photo)
     plain=render_hybrid(card,'gold-cream',photo,root/'plain.jpg',plan)
     plan['heading_shade']='emphasis'
     shaded=render_hybrid(card,'gold-cream',photo,root/'shaded.jpg',plan)
     self.assertEqual(plain['heading_shading'],0)
     self.assertEqual(shaded['heading_shading'],TITLE_SHADE_LEVELS[0])
     self.assertGreaterEqual(shaded['heading_contrast'],3);self.assertLessEqual(shaded['heading_shading'],126)
     self.assertNotEqual((root/'plain.jpg').read_bytes(),(root/'shaded.jpg').read_bytes())
     self.assertEqual(shaded['example_shading'],plain['example_shading'])
     self.assertEqual(shaded['composition']['blocks'],original['blocks']);self.assertEqual(card,source)
 def test_existing_proximity_boundary_is_unchanged(self):
  card,plan=self.card_plan();boundary=heading(card)[2]
  for gap,expected in ((99,'near'),(100,'far'),(101,'far')):
   plan['blocks'][1]['y']=round(boundary+gap)
   self.assertEqual(title_example_proximity(plan['blocks'],boundary),expected)
   plan['heading_shade']='emphasis'
   if expected=='near':
    with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
   else:measured_plan(card,plan)
 def test_nearby_keeps_unshaded_first_and_rejects_decorative_emphasis(self):
  card,plan=self.card_plan(near=True)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
   result=render_hybrid(card,'gold-cream',photo,root/'near.jpg',plan)
   self.assertEqual(result['heading_shading'],0)
   plan['heading_shade']='emphasis'
   with self.assertRaisesRegex(ValueError,'distant PRIMJER'):render_hybrid(card,'gold-cream',photo,root/'bad.jpg',plan)
 def test_regular_nonquiz_cap_still_applies_to_emphasis_and_legacy_gentle_stays_identical(self):
  card,plan=self.card_plan(intent='emphasis')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'white').save(photo)
   result=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
   self.assertGreaterEqual(result['heading_contrast'],3);self.assertLessEqual(result['heading_shading'],NONQUIZ_TITLE_MAX_SHADE)
   plan['heading_shade']='gentle';render_hybrid(card,'gold-cream',photo,root/'gentle.jpg',plan)
   del plan['heading_shade'];render_hybrid(card,'gold-cream',photo,root/'legacy.jpg',plan)
   self.assertEqual((root/'gentle.jpg').read_bytes(),(root/'legacy.jpg').read_bytes())
 def test_quiz_schema_and_stronger_intent_stay_separate_and_paper_or_absent_example_cannot_emphasise(self):
  fields=RESULT_SCHEMA['properties']['cards']['properties']
  self.assertEqual(fields['quiz']['properties']['heading_shade']['enum'],['gentle','stronger'])
  for kind in ('lesson','word'):self.assertEqual(fields[kind]['properties']['heading_shade']['enum'],['gentle','emphasis'])
  card,plan=self.card_plan();card.pop('example');plan=default_plan(card);plan['heading_shade']='emphasis'
  with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
  card,plan=self.card_plan();plan=editorial_plan(card);plan['heading_shade']='emphasis'
  with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
  quiz=reviewed_fixture()['cards'][0];plan=default_plan(quiz);plan['heading_shade']='emphasis'
  with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(quiz,plan)
 def test_invalid_nearby_emphasis_recovers_heading_only(self):
  card,plan=self.card_plan(near=True,intent='emphasis');before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
   m,detail=render_design(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p),model_accepted=True,attempt_limit=1)
  self.assertEqual(m['composition']['heading_shade'],'gentle');self.assertEqual(m['composition']['blocks'],before['blocks'])
  self.assertEqual(detail['status'],'partial');self.assertEqual(detail['element_recovery']['fallback'],['heading'])
 def test_emphasis_is_reported_and_recorded_in_recent_choices(self):
  card,plan=self.card_plan(intent='emphasis')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
   m=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
  self.assertEqual(accepted_choices({'cards':{'word':dict(m,status='accepted')}})['word']['heading_shade'],'emphasis')
  self.assertIn('Title shade intent: emphasis.',decision_lines(m))
 def test_live_prompt_contains_both_distance_cases_and_keeps_black_preference_and_global_weight_priority(self):
  package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
  proposal['cards']['word']['heading_shade']='emphasis'
  self.assertFalse(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
   review_compositions(package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in package['cards']})
  prompt=model.call_args.args[0]
  for text in ('less than 100px is nearby','100px or more is farther away','heading_shade=gentle or emphasis','even if the bare title is already readable','Nearby titles require heading_shade=gentle','Regardless of distance','reducing or removing the TITLE shade','PRIORITISE the PRIMJER backing','STRONGLY PREFER BLACK backing with LIGHT'):
   self.assertIn(text,prompt)
  for text in ('For BLACK backing only','heading_opacity from 0 through 126','not just readability',
               'White retains its existing faint/readability-driven behaviour',
               'do not reduce or remove it merely because both shades are present'):
   self.assertIn(text,prompt)
 def test_black_strength_choice_survives_even_when_bare_title_already_passes(self):
  for kind in ('word','lesson'):
   for tone in ('paper_dark','paper_ink','accent_dark'):
    card,base=self.card_plan(kind);base['heading_tone']=tone;source=copy.deepcopy(card)
    with tempfile.TemporaryDirectory() as tmp:
     root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
     plain=render_hybrid(card,'gold-cream',photo,root/'gentle.jpg',base)
     self.assertEqual(plain['heading_shading'],0)
     for intent,alpha in (('emphasis',12),('emphasis_medium',66),('emphasis_strong',126)):
      plan=dict(base,heading_shade=intent);before=copy.deepcopy(plan)
      result=render_hybrid(card,'gold-cream',photo,root/f'{intent}.jpg',plan)
      self.assertEqual(result['heading_shading'],alpha);self.assertEqual(result['heading_backing'],'#000000')
      self.assertGreaterEqual(result['heading_contrast'],3);self.assertEqual(result['composition'],before)
      self.assertEqual(result['example_shading'],plain['example_shading']);self.assertEqual(card,source)
      with Image.open(root/'gentle.jpg') as a,Image.open(root/f'{intent}.jpg') as b:
       self.assertEqual(a.crop((0,700,1080,1350)).tobytes(),b.crop((0,700,1080,1350)).tobytes())
 def test_increased_strength_requires_black_and_never_silently_darkens_white_or_auto(self):
  card,plan=self.card_plan()
  for intent in ('emphasis_medium','emphasis_strong'):
   for tone in ('auto','ink_light','ink_paper','accent_light','ink_accent'):
    plan.update(heading_shade=intent,heading_tone=tone)
    with self.assertRaisesRegex(ValueError,'explicit black backing'):measured_plan(card,plan)
 def test_increased_black_strength_keeps_existing_near_boundary_and_quiz_paper_restrictions(self):
  for intent in ('emphasis_medium','emphasis_strong'):
   card,plan=self.card_plan(intent=intent);boundary=heading(card)[2]
   plan['blocks'][1]['y']=round(boundary+99)
   with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
   plan['blocks'][1]['y']=round(boundary+100);measured_plan(card,plan)
   card.pop('example');plan=default_plan(card);plan['heading_shade']=intent
   with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
   card,plan=self.card_plan();plan=editorial_plan(card);plan['heading_shade']=intent
   with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
   card=reviewed_fixture()['cards'][0];plan=default_plan(card);plan['heading_shade']=intent
   with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
 def test_medium_black_can_escalate_for_contrast_but_stays_inside_existing_cap(self):
  card,plan=self.card_plan(intent='emphasis_medium')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'white').save(photo)
   result=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
  self.assertGreater(result['heading_shading'],66)
  self.assertLessEqual(result['heading_shading'],126);self.assertGreaterEqual(result['heading_contrast'],3)
 def test_white_increased_strength_recovers_only_the_heading_with_safe_reason(self):
  card,plan=self.card_plan(intent='emphasis_medium');plan['heading_tone']='ink_light';before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#eeeeee').save(photo)
   m,detail=render_design(card,plan,photo,lambda p:render_hybrid(card,'gold-cream',photo,root/'card.jpg',p),model_accepted=True,attempt_limit=1)
  self.assertEqual(m['composition']['blocks'],before['blocks']);self.assertEqual(detail['status'],'partial')
  self.assertEqual(detail['element_recovery']['fallback'],['heading'])
  self.assertEqual(detail['rejection']['reason'],'Increased decorative title strength requires an explicit black backing')
 def test_new_strength_choices_are_strictly_typed_reported_and_retained_for_nonquiz_history(self):
  package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
  fields=RESULT_SCHEMA['properties']['cards']['properties']
  self.assertEqual(fields['quiz']['properties']['heading_shade']['enum'],['gentle','stronger'])
  for intent in ('emphasis_medium','emphasis_strong'):
   proposal['cards']['word']['heading_shade']=intent
   self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
   card,plan=self.card_plan(intent=intent)
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
    m=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
   self.assertEqual(accepted_choices({'cards':{'word':dict(m,status='accepted')}})['word']['heading_shade'],intent)
   self.assertIn('Title shade intent: '+intent+'.',decision_lines(m))
   proposal['cards']['quiz']['heading_shade']=intent
   self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
   proposal['cards']['quiz']['heading_shade']='gentle'
  for invalid in (100,0.3,{'opacity':66},'emphasis_unlimited'):
   proposal['cards']['word']['heading_shade']=invalid
   self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
