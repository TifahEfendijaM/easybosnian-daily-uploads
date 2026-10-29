"""Optional paler light surfaces preserve rich defaults, opacity and other roles."""
import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.designs import light_surface_colour
from easybosnian.hybrid import default_plan,measured_plan,render_hybrid,example_colours
from easybosnian.palettes import active,current
from easybosnian.visual_placement import CARD_SCHEMA,MODEL_CARD_SCHEMA
from easybosnian.render import contrast
from jsonschema import Draft202012Validator
from test_project import reviewed_fixture

class SurfaceRichnessTests(unittest.TestCase):
    def test_active_catalogue_and_approved_rich_defaults_keep_archived_palette(self):
        catalogue=read_json(ROOT/'data/design-palettes.json')
        self.assertEqual(len(active()),36);self.assertEqual(len(catalogue),37)
        self.assertNotIn('graphite-chalk',active());self.assertIn('graphite-chalk',catalogue)
        self.assertEqual(current('graphite-chalk'),'mulberry-mint')
        self.assertEqual(catalogue['ochre-parchment']['panel'],'#f1e0ad')
        for name,colour in {'burgundy-oat':'#e8c8b2','indigo-mist':'#ccd8f5','teal-seaglass':'#bde4dc','aubergine-apricot':'#edd0b9'}.items():
            self.assertEqual(catalogue[name]['panel'],colour)
        gold=example_colours(catalogue['ochre-parchment'],'paper_ink','ochre-parchment')[1][0][1]
        self.assertEqual(gold,(116,87,0));self.assertGreaterEqual(contrast('#ffffff','#745700'),4.5)

    def test_paler_is_explicit_bounded_rgb_change_not_transparency(self):
        self.assertEqual(light_surface_colour('#bde4dc'), '#bde4dc')
        self.assertEqual(light_surface_colour('#bde4dc',70),'#d1ece6')
        for bad in (69,101,True,None,'80',float('nan'),float('inf')):
            with self.assertRaises(ValueError):light_surface_colour('#bde4dc',bad)
        card=reviewed_fixture()['cards'][2];plan=default_plan(card);plan['blocks'][0].update(style='rounded_plain',panel_tone='ink_paper')
        source=copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#888888').save(photo)
            render_hybrid(card,'teal-seaglass',photo,root/'default.jpg',plan)
            del plan['blocks'][0]['surface_richness'];render_hybrid(card,'teal-seaglass',photo,root/'old.jpg',plan)
            self.assertEqual((root/'old.jpg').read_bytes(),(root/'default.jpg').read_bytes())
            plan['blocks'][0]['surface_richness']=70
            actual=render_hybrid(card,'teal-seaglass',photo,root/'paler.jpg',plan)
            self.assertEqual(actual['composition'],plan);self.assertGreaterEqual(actual['body_contrast'],4.5)
            self.assertNotEqual((root/'paler.jpg').read_bytes(),(root/'default.jpg').read_bytes())
            with Image.open(root/'paler.jpg') as im:
                body=plan['blocks'][0];pixel=im.getpixel((body['x']+50,body['y']+8))
                self.assertTrue(all(abs(x-y)<=3 for x,y in zip(pixel,(209,236,230))),pixel)
            self.assertEqual(plan['blocks'][1:],source['blocks'][1:]);self.assertEqual(plan['blocks'][0]['panel_opacity'],100)

    def test_dark_unboxed_and_answers_cannot_use_richness_control(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        for tone in ('paper_ink','accent_ink'):
            bad=copy.deepcopy(plan);bad['blocks'][0].update(panel_tone=tone,surface_richness=80)
            with self.assertRaisesRegex(ValueError,'Only light explanation'):measured_plan(card,bad)
        for value in (69,101,True):
            bad=copy.deepcopy(plan);bad['blocks'][0]['surface_richness']=value
            self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(bad)))
        quiz=default_plan(reviewed_fixture()['cards'][0]);quiz['blocks'][0]['surface_richness']=80
        self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(quiz)))
        branches=MODEL_CARD_SCHEMA['properties']['blocks']['items']['anyOf']
        self.assertIn('surface_richness',branches[0]['required'])
        self.assertNotIn('surface_richness',branches[1]['properties']);self.assertNotIn('surface_richness',branches[2]['properties'])

    def test_recovery_of_inactive_richness_preserves_all_other_body_choices(self):
        from easybosnian.element_recovery import recover_elements
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan.update(confidence='high',palette='mulberry-mint')
        plan['blocks'][0].update(style='rounded_plain',panel_tone='paper_ink',surface_richness=80)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#888888').save(photo)
            result=recover_elements(card,plan,photo,lambda p:render_hybrid(card,'mulberry-mint',photo,root/'card.jpg',p),
                reason='Only light explanation panels can reduce surface richness')
        self.assertIsNotNone(result);actual,detail=result
        expected=copy.deepcopy(plan);expected['blocks'][0]['surface_richness']=100
        self.assertEqual(actual['composition'],expected);self.assertEqual(detail['fallback'],['body'])
