"""Explicit PRIMJER intent has real pixels, preserves legacy plans and stays safe."""
import copy
import colorsys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import default_plan,render_hybrid,measured_plan,EXAMPLE_SHADE_MINIMUMS
from easybosnian.visual_placement import MODEL_CARD_SCHEMA,CARD_SCHEMA,review_compositions
from easybosnian.visual_policy import apply_policy
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import report_data,with_rendering,render_report
from easybosnian.render import contrast
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as harness_module

SATURATED=('royal-blue-sun','emerald-lime','ruby-cream','violet-citrus','ocean-tangerine',
    'magenta-porcelain','scarlet-vanilla','peacock-coral','sapphire-lime',
    'grape-lemon','paprika-aqua','ultramarine-orchid','cherry-lime','petrol-cyan')

class ExampleStrengthChoicesTests(unittest.TestCase):
    def test_each_strength_has_distinct_pixels_for_both_edges_and_neutral_backings(self):
        card=reviewed_fixture()['cards'][2];source=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.png'
            for tone,background in (('paper_dark','#101010'),('ink_light','#eeeeee')):
                Image.new('RGB',(1080,1350),background).save(photo)
                for edge in ('standard','sharp'):
                    outputs=[]
                    for strength,alpha in EXAMPLE_SHADE_MINIMUMS.items():
                        plan=default_plan(card);plan['blocks'][-1].update(photo_tone=tone,fade_style=edge,shade_strength=strength)
                        requested=copy.deepcopy(plan)
                        metrics=render_hybrid(card,'forest-cream',photo,root/'card.jpg',plan)
                        self.assertEqual(metrics['example_shading'],alpha)
                        self.assertGreaterEqual(metrics['example_contrast'],4.5)
                        self.assertEqual(metrics['composition'],requested);self.assertEqual(plan,requested)
                        outputs.append((root/'card.jpg').read_bytes())
                    self.assertEqual(len(set(outputs)),3)
        self.assertEqual(card,source)

    def test_soft_escalates_only_for_readability_and_old_missing_field_stays_readable(self):
        card=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'white').save(photo)
            plan=default_plan(card);plan['blocks'][-1].update(photo_tone='paper_dark',shade_strength='soft')
            metrics=render_hybrid(card,'forest-cream',photo,root/'new.jpg',plan)
            self.assertGreater(metrics['example_shading'],64);self.assertGreaterEqual(metrics['example_contrast'],4.5)
            legacy=copy.deepcopy(plan);del legacy['blocks'][-1]['shade_strength']
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(legacy)))
            fresh=dict(legacy,palette='forest-cream')
            self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(fresh)))
            old=render_hybrid(card,'forest-cream',photo,root/'old.jpg',legacy)
            self.assertIn(old['example_shading'],(90,130,170,210,240))
            self.assertNotIn('shade_strength',old['composition']['blocks'][-1])
            for value in (.5,75,'untrusted',{'alpha':64}):
                bad=copy.deepcopy(plan);bad['blocks'][-1]['shade_strength']=value
                self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(bad)))
            plan['blocks'][-1].update(style='italic_photo',shade_strength='strong')
            with self.assertRaisesRegex(ValueError,'Only photographic faded examples can select shade strength'):measured_plan(card,plan)

    def test_model_instructions_and_pipeline_preserve_requested_strength_in_reports_and_history(self):
        h=harness_module.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['blocks'][-1].update(photo_tone='paper_dark',shade_strength='medium')
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            result,status=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed')
        prompt=child.call_args.args[0]
        for text in ('Give ALL THREE equal consideration','neither softer nor stronger is preferred',
                     'dark palette-ink surfaces with bright paper/accent text on equal footing',
                     'independently of shape/style','Neither light nor dark LESSON/WORD panels are preferred'):
            self.assertIn(text,prompt)
        for text in ('FIRST seek a visibly DIFFERENT HUE', 'ONLY when NO different-hue candidate',
                     'try a related dark hue with enough visual separation',
                     'Mere cohesion, convenience or a subtle near-match is not enough',
                     'Judge final blended appearance, not tone IDs or hex distance alone',
                     'Rich/saturated DARK colours are welcome and MILDLY PREFERRED'):
            self.assertIn(text,prompt)
        placement,metrics=h.render(h.package,proposal)
        word=placement['cards']['word'];self.assertEqual(word['status'],'accepted')
        self.assertEqual(word['composition']['blocks'][-1]['shade_strength'],'medium')
        self.assertGreaterEqual(metrics['word']['example_shading'],128)
        self.assertEqual(accepted_choices(placement)['word']['example_shade_strength'],'medium')
        report=with_rendering(report_data(h.package,results(),RUN),placement)
        for text in render_report(report):
            self.assertIn('PRIMJER shade strength: medium requested',text)
            self.assertIn('PRIMJER applied backing opacity:',text)
        for value in (-1,256,1.5,True,'private prose'):
            bad=copy.deepcopy(placement);bad['cards']['word']['example_shading']=value
            with self.assertRaisesRegex(ValueError,'example shading metadata'):with_rendering(report_data(h.package,results(),RUN),bad)

    def test_saturated_palettes_have_safe_bright_and_dark_surfaces_for_body_and_answers(self):
        palette_map=read_json(ROOT/'data/design-palettes.json');cards=reviewed_fixture()['cards']
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#898989').save(photo)
            for name in SATURATED:
                palette=palette_map[name]
                for key in ('ink','accent'):
                    rgb=tuple(int(palette[key][i:i+2],16)/255 for i in (1,3,5))
                    self.assertGreaterEqual(colorsys.rgb_to_hsv(*rgb)[1],.4,(name,key))
                for tone in ('ink_paper','paper_ink','accent_ink'):
                    for card in (cards[0],cards[2]):
                        plan=default_plan(card)
                        for block in plan['blocks']:
                            if block['role']!='example':block.update(panel_tone=tone,style='rounded')
                        metrics=render_hybrid(card,name,photo,root/'card.jpg',plan)
                        self.assertGreaterEqual(metrics['body_contrast'],4.5,(name,tone))
                        self.assertEqual(metrics['composition'],plan)
                        if tone in ('paper_ink','accent_ink'):
                            x,y,right,bottom=metrics['panel_bounds'][0]
                            with Image.open(root/'card.jpg') as im:
                                actual=im.getpixel((right-12,y+34))
                                expected=tuple(int(palette['ink'][i:i+2],16) for i in (1,3,5))
                                self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),4)
                self.assertGreaterEqual(contrast(palette['ink'],palette['accent']),4.5)
