"""Richer dark panels preserve every independent palette role and archive path."""
import copy,tempfile,unittest
from pathlib import Path
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.designs import panel_colours
from easybosnian.render import contrast,luminance
from easybosnian.hybrid import default_plan,render_hybrid
from easybosnian.visual_policy import policy_metadata,safe_policy
from easybosnian.success_report import decision_lines
from test_project import reviewed_fixture

class MiddleDarkSurfaceTests(unittest.TestCase):
 def test_every_curated_surface_is_richer_lighter_and_readable_with_both_lettering_roles(self):
  for name,p in read_json(ROOT/'data/design-palettes.json').items():
   with self.subTest(palette=name):
    self.assertGreater(luminance(p['dark_surface']),luminance(p['ink']))
    for foreground in ('panel','accent'):
     self.assertGreaterEqual(contrast(p[foreground],p['dark_surface']),4.5)
    self.assertEqual(panel_colours(p,'paper_ink',bounded=True),(p['panel'],p['dark_surface']))
    self.assertEqual(panel_colours(p,'accent_ink',bounded=True),(p['accent'],p['dark_surface']))
    for tone in ('auto','ink_paper','ink_accent'):
     self.assertEqual(panel_colours(p,tone,bounded=True),panel_colours(p,tone))
    self.assertEqual(panel_colours(p,'paper_ink'),(p['panel'],p['ink']))
    self.assertEqual(panel_colours(p,'accent_ink'),(p['accent'],p['ink']))
 def test_refinement_changes_only_the_dark_main_panel_and_retains_historical_rendering(self):
  card=copy.deepcopy(reviewed_fixture()['cards'][2]);card.update(heading='Primjer',body='A short explanation.',example='Jedan prirodan primjer.')
  plan=dict(default_plan(card),palette='burgundy-oat',heading_tone='paper_dark')
  plan['blocks'][0].update(y=760,panel_tone='paper_ink',style='corner_brackets');plan['blocks'][-1].update(y=1080,photo_tone='paper_dark')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#808080').save(photo)
   current=render_hybrid(card,'burgundy-oat',photo,root/'new.jpg',plan)
   legacy=render_hybrid(card,'burgundy-oat',photo,root/'old.jpg',plan,refined_panels=False)
   self.assertNotEqual((root/'new.jpg').read_bytes(),(root/'old.jpg').read_bytes())
   self.assertEqual(current['composition'],legacy['composition'])
   self.assertEqual(current['dark_panel_surface'],'#632b40');self.assertEqual(legacy['dark_panel_surface'],'#3b1520')
   for field in ('heading_colour','heading_shading','example_colour','example_shading','panel_bounds','category_style'):
    self.assertEqual(current[field],legacy[field],field)
   self.assertGreaterEqual(current['body_contrast'],4.5)
   # Light surfaces are byte-identical, including category/title/example colours.
   plan['blocks'][0]['panel_tone']='ink_paper'
   render_hybrid(card,'burgundy-oat',photo,root/'light-new.jpg',plan)
   render_hybrid(card,'burgundy-oat',photo,root/'light-old.jpg',plan,refined_panels=False)
   self.assertEqual((root/'light-new.jpg').read_bytes(),(root/'light-old.jpg').read_bytes())
  policy=policy_metadata(plan);self.assertEqual(policy['version'],9)
  self.assertEqual(safe_policy(dict(policy,version=8),plan)['version'],8)
 def test_report_names_applied_surface_without_claiming_quieter_accents(self):
  from test_visual_provenance import VisualProvenanceTests
  from test_success_report import RUN,results
  from easybosnian.success_report import report_data,with_rendering
  h=VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
  proposal['cards']['word']['palette']='burgundy-oat'
  proposal['cards']['word']['blocks'][0]['panel_tone']='paper_ink'
  placement,metrics=h.render(h.package,proposal)
  result=with_rendering(report_data(h.package,results(),RUN),placement)['cards'][2]['rendering']
  self.assertEqual(result['dark_panel_surface'],'#632b40')
  text='\n'.join(decision_lines(result))
  self.assertIn('#632b40; original decorative accent retained',text)
  bad=copy.deepcopy(placement);bad['cards']['word']['dark_panel_surface']='#aabbcc'
  with self.assertRaisesRegex(ValueError,'dark-panel surface'):with_rendering(report_data(h.package,results(),RUN),bad)
