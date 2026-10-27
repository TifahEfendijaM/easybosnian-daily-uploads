"""Quiz main surfaces are scoped independently from badges and lesson panels."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian.core import ROOT
from easybosnian.designs import PANEL_TONES,dark_panel_surface,panel_colours
from easybosnian.hybrid import validate_current_design,render_hybrid,draw_panel,measured_plan
from easybosnian.design_repair import render_design
from easybosnian.render import luminance,contrast
from easybosnian.visual_placement import review_compositions
import test_title_weight_and_visual_answers as layouts
import test_visual_provenance as harness

class QuizSurfacePolicyTests(unittest.TestCase):
 def plan(self):return layouts.TitleWeightAndVisualAnswersTests().quiz_plan(2)
 def test_surface_classification_matches_actual_colours_for_every_palette(self):
  for palette in json.loads((ROOT/'data/design-palettes.json').read_text()).values():
   for style in ('rounded_plain','overlay_dark','split_panel'):
    for tone in PANEL_TONES:
     text,surface=panel_colours(palette,tone,dark=style=='overlay_dark')
     self.assertEqual(dark_panel_surface({'style':style,'panel_tone':tone}),luminance(surface)<luminance(text))
 def test_fresh_centred_quiz_rejects_only_dark_main_surfaces(self):
  card,plan=self.plan()
  for tone,style in (('paper_ink','rounded'),('accent_ink','rounded'),('auto','overlay_dark')):
   candidate=copy.deepcopy(plan);candidate['blocks'][0].update(panel_tone=tone,style=style)
   with self.assertRaisesRegex(ValueError,'non-dark panel surfaces'):validate_current_design(card,candidate)
   candidate['blocks'][0]['panel_tone']='ink_paper';candidate['blocks'][0]['marker_tone']='paper_ink'
   validate_current_design(card,candidate)
   card['quiz_format']='other';candidate['photo_window']=None;candidate['blocks'][0]['panel_tone']=tone
   validate_current_design(card,candidate)  # Dark full-photo panels remain eligible when clearly better.
   card['quiz_format']='visual_identification'
 def test_recovery_changes_only_bad_panel_pair_and_retains_badge_and_sibling(self):
  card,plan=self.plan();plan['confidence']='high';plan['blocks'][0].update(panel_tone='paper_ink',marker_tone='accent_ink')
  before=copy.deepcopy(plan)
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#888888').save(photo)
   draw=lambda p:render_hybrid(card,'forest-cream',photo,root/'card.jpg',p)
   legacy=draw(plan);self.assertEqual(legacy['composition'],before)
   metrics,detail=render_design(card,plan,photo,draw,model_accepted=True,attempt_limit=1)
  expected=copy.deepcopy(before);expected['blocks'][0]['panel_tone']='ink_paper'
  self.assertEqual(metrics['composition'],expected);self.assertEqual(plan,before)
  self.assertEqual(detail['element_recovery']['fallback'],['A'])
  self.assertIn('B',detail['element_recovery']['preserved'])
 def test_dark_badge_renders_on_light_panel_independently(self):
  card,plan=self.plan();block=plan['blocks'][0];block.update(panel_tone='ink_paper',marker_tone='paper_ink',marker_style='square')
  palette=json.loads((ROOT/'data/design-palettes.json').read_text())['forest-cream']
  measured=measured_plan(card,plan)[0];image=Image.new('RGBA',(1080,1350),'#ffffff')
  draw_panel(image,measured,palette)
  rgb=lambda colour:tuple(bytes.fromhex(colour[1:]))
  self.assertEqual(image.getpixel((block['x']+25,round(block['y']+measured['height']/2)))[:3],rgb(palette['ink']))
  self.assertEqual(image.getpixel((block['x']+400,block['y']+20))[:3],rgb(palette['panel']))
  self.assertGreaterEqual(contrast(*panel_colours(palette,'paper_ink')),4.5)
 def test_live_prompt_scopes_preferences_and_retains_equal_normal_edges(self):
  h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
  with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
   review_compositions(h.package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']})
  prompt=model.call_args.args[0]
  for rule in ('MUST use non-dark surfaces','ONLY when they CLEARLY suit','NOT the A/B/C/D badges',
   'For LESSON/WORD panels only','marker_tone independently','dark bins/shadows and earthy clothing',
   'with neither preferred or the default','Proximity is eligibility, NEVER an automatic selection'):
   self.assertIn(rule,prompt)
  self.assertNotIn('Prefer sharp',prompt)
  self.assertNotIn('Neither dark nor light palettes/panels are preferred',prompt)
