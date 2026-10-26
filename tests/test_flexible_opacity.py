"""Bounded model opacity survives rendering; geometry and contrast remain trusted."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.hybrid import default_plan,render_hybrid,measured_plan,heading
from easybosnian.visual_placement import RESULT_SCHEMA,review_compositions
from easybosnian.visual_policy import apply_policy,policy_metadata,safe_policy
from easybosnian.design_repair import render_design,unchanged
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import decision_lines
from test_project import reviewed_fixture

class FlexibleOpacityTests(unittest.TestCase):
 def word(self):
  card=copy.deepcopy(reviewed_fixture()['cards'][2]);card.update(heading='Primjer',body='A short explanation.',example='Jedan prirodan primjer.')
  plan=dict(default_plan(card),confidence='high',heading_tone='paper_dark',heading_shade='emphasis')
  plan['blocks'][0]['y']=760;plan['blocks'][1].update(y=1080,photo_tone='paper_dark')
  return card,plan
 def test_arbitrary_black_alpha_is_not_snapped_to_the_previous_three_presets(self):
  card,plan=self.word();before=copy.deepcopy(card)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
   for alpha in (0,1,25,53,89,117,126):
    selected=dict(plan,heading_opacity=alpha);m=render_hybrid(card,'gold-cream',photo,root/f'{alpha}.jpg',selected)
    self.assertEqual(m['heading_shading'],alpha);self.assertGreaterEqual(m['heading_contrast'],3)
    self.assertEqual(m['composition'],selected);self.assertEqual(card,before)
 def test_selected_black_opacity_can_only_increase_for_contrast_within_the_existing_cap(self):
  card,plan=self.word();plan['heading_opacity']=53
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'white').save(photo)
   m=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
  self.assertGreater(m['heading_shading'],53);self.assertLessEqual(m['heading_shading'],126)
  self.assertGreaterEqual(m['heading_contrast'],3);self.assertEqual(m['composition']['heading_opacity'],53)
 def test_numeric_title_choice_is_black_only_distant_only_and_emphasis_only(self):
  card,plan=self.word();plan['heading_opacity']=53
  for tone in ('auto','ink_light','ink_paper','accent_light'):
   bad=dict(plan,heading_tone=tone)
   with self.assertRaisesRegex(ValueError,'Selected title opacity'):measured_plan(card,bad)
  with self.assertRaisesRegex(ValueError,'Selected title opacity'):measured_plan(card,dict(plan,heading_shade='gentle'))
  plan['blocks'][1]['y']=round(heading(card)[2]+99)
  with self.assertRaisesRegex(ValueError,'distant PRIMJER'):measured_plan(card,plan)
  plan['blocks'][1]['y']=round(heading(card)[2]+100);measured_plan(card,plan)
  quiz=reviewed_fixture()['cards'][0];q=dict(default_plan(quiz),heading_tone='paper_dark',heading_opacity=53)
  with self.assertRaisesRegex(ValueError,'Selected title opacity'):measured_plan(quiz,q)
 def test_fresh_schema_accepts_continuous_bounded_choices_but_not_legacy_fixed_presets(self):
  package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
  word=proposal['cards']['word'];word.update(heading_tone='paper_dark',heading_shade='emphasis',heading_opacity=53)
  word['blocks'][0]['panel_opacity']=93.75
  self.assertFalse(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
  for alpha in (-1,127,53.2,True,'53',{'alpha':53}):
   word['heading_opacity']=alpha;self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
  word['heading_opacity']=53
  for preset in ('emphasis_medium','emphasis_strong'):
   word['heading_shade']=preset;self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
  word['heading_shade']='emphasis';proposal['cards']['quiz']['heading_opacity']=53
  self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
 def test_quiz_options_share_a_reviewer_chosen_opacity_and_keep_exact_source_copy(self):
  for count in (2,3,4):
   quiz=copy.deepcopy(reviewed_fixture()['cards'][0]);quiz['options']=[{'label':l,'text':t} for l,t in zip('ABCD',('Jabuka','Kruška','Šljiva','Dunja'))][:count]
   source=copy.deepcopy(quiz);plan=default_plan(quiz)
   for b in plan['blocks']:b['panel_opacity']=93.75
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#728192').save(photo)
    m=render_hybrid(quiz,'gold-cream',photo,root/'quiz.jpg',apply_policy(plan))
   self.assertEqual({b['panel_opacity'] for b in m['composition']['blocks']},{93.75})
   self.assertEqual(quiz,source);self.assertGreaterEqual(m['body_contrast'],4.5)
   self.assertEqual(policy_metadata(m['composition'])['panel_opacity'],93.75)
 def test_invalid_or_inconsistent_panel_opacity_is_rejected_instead_of_overriding_siblings(self):
  quiz=reviewed_fixture()['cards'][0];plan=default_plan(quiz)
  for value in (89.99,100.01,True,float('nan'),'soft'):
   bad=copy.deepcopy(plan);bad['blocks'][0]['panel_opacity']=value
   with self.assertRaisesRegex(ValueError,'opacity'):apply_policy(bad)
  plan['blocks'][0]['panel_opacity']=95
  with self.assertRaisesRegex(ValueError,'share one opacity'):apply_policy(plan)
 def test_repaired_option_inherits_shared_opacity_without_altering_accepted_siblings(self):
  quiz=copy.deepcopy(reviewed_fixture()['cards'][0]);quiz['options']=[{'label':l,'text':t} for l,t in zip('ABC',('Jabuka','Kruška','Šljiva'))]
  plan=dict(default_plan(quiz),confidence='high')
  for b in plan['blocks']:b['panel_opacity']=95
  plan['blocks'][1]['panel_opacity']=96;before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#728192').save(photo)
   m,detail=render_design(quiz,plan,photo,lambda p:render_hybrid(quiz,'gold-cream',photo,root/'quiz.jpg',apply_policy(p)),model_accepted=True,attempt_limit=1)
  self.assertEqual(detail['element_recovery']['fallback'],['B'])
  self.assertEqual(m['composition']['blocks'][0],before['blocks'][0]);self.assertEqual(m['composition']['blocks'][2],before['blocks'][2])
  self.assertEqual(m['composition']['blocks'][1]['panel_opacity'],95)
 def test_reports_history_and_heading_locks_include_requested_opacity(self):
  card,plan=self.word();plan['heading_opacity']=53;plan['blocks'][0]['panel_opacity']=94.5
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#202020').save(photo)
   m=render_hybrid(card,'gold-cream',photo,root/'word.jpg',apply_policy(plan))
  record=dict(m,status='accepted',render_policy=policy_metadata(m['composition']))
  text='\n'.join(decision_lines(record));self.assertIn('53/255 requested; 53/255 applied',text);self.assertIn('Shared panel opacity: 94.5%',text)
  safe=accepted_choices({'cards':{'word':record}})['word'];self.assertEqual(safe['heading_opacity'],53);self.assertEqual(safe['panel_opacities'],{'body':94.5})
  bad=copy.deepcopy(plan);bad['heading_opacity']=54;self.assertFalse(unchanged(plan,bad,['heading']))
  bad_policy=dict(record['render_policy'],panel_opacity=90)
  with self.assertRaisesRegex(ValueError,'Shared opacity'):safe_policy(bad_policy,m['composition'])
 def test_live_prompt_gives_per_image_shared_panel_and_independent_black_alpha_controls(self):
  package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
  for kind,value,palette in (('quiz',92,'gold-cream'),('lesson',96,'blue-ice'),('word',99,'forest-cream')):
   proposal['cards'][kind].update(palette=palette,confidence='high')
   for b in proposal['cards'][kind]['blocks']:
    if b['role']!='example':b['panel_opacity']=value
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
   actual,status=review_compositions(package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in package['cards']})
  self.assertEqual(status,'reviewed');self.assertEqual(actual['cards'],proposal['cards'])
  prompt=model.call_args.args[0]
  for text in ('heading_opacity from 0 through 126','without snapping to the old three presets','Choose ONE panel_opacity percentage from 90 through 100','exactly the SAME value','not just readability'):
   self.assertIn(text,prompt)
