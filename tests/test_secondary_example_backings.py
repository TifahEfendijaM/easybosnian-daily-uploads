"""Curated secondary shades stay dark, legible and example-only."""
import colorsys
import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import default_plan,example_colours,photo_colours,render_hybrid,measured_plan
from easybosnian.render import contrast,luminance
from easybosnian.visual_placement import CARD_SCHEMA,MODEL_CARD_SCHEMA,review_compositions
from easybosnian.visual_history import accepted_choices
from test_project import reviewed_fixture
import test_visual_provenance as harness

class SecondaryExampleBackingTests(unittest.TestCase):
    def test_every_palette_has_one_rich_dark_secondary_with_readable_light_lettering(self):
        palettes=read_json(ROOT/'data/design-palettes.json');shades=read_json(ROOT/'data/example-backings.json')
        self.assertEqual(set(shades),set(palettes)-{'mulberry-mint'})
        for name,shade in shades.items():
            with self.subTest(palette=name):
                self.assertRegex(shade,r'^#[0-9a-f]{6}$');self.assertNotEqual(shade,palettes[name]['ink'])
                self.assertLess(luminance(shade),.13)
                saturation=colorsys.rgb_to_hsv(*(int(shade[i:i+2],16)/255 for i in (1,3,5)))[1]
                self.assertGreaterEqual(saturation,.4)
                for tone,text in (('white_secondary','#ffffff'),('paper_secondary',palettes[name]['panel'])):
                    colours,backings=example_colours(palettes[name],tone,name)
                    self.assertEqual(colours,[text]);self.assertGreaterEqual(contrast(text,shade),4.5)
                    self.assertEqual(backings,[(text,tuple(int(shade[i:i+2],16) for i in (1,3,5)))])

    def test_render_keeps_proposal_copy_other_elements_and_readability_for_both_new_pairs(self):
        source=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#a0a0a0').save(photo)
            for palette in ('forest-cream','gold-cream','plum-blush','espresso-almond'):
                for tone in ('white_secondary','paper_secondary'):
                    card=copy.deepcopy(source);plan=default_plan(card)
                    plan['blocks'][-1].update(photo_tone=tone,shade_strength='medium',fade_style='sharp')
                    requested=copy.deepcopy(plan)
                    result=render_hybrid(card,palette,photo,root/'card.jpg',plan)
                    self.assertEqual(result['composition'],requested);self.assertEqual(card,source)
                    self.assertEqual(result['example_tone'],tone);self.assertGreaterEqual(result['example_contrast'],4.5)
                    self.assertGreaterEqual(result['heading_contrast'],3)
                    accepted={**result,'status':'accepted','palette_outcome':{'source':'chatgpt'}}
                    self.assertNotIn('example_tone',accepted_choices({'cards':{'word':accepted}})['word'])  # Retired pairing is never a fresh recommendation.

    def test_new_tokens_are_not_title_or_unshaded_controls_and_legacy_pairs_are_unchanged(self):
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),palette='forest-cream')
        for tone in ('white_secondary','paper_secondary'):
            plan['blocks'][-1]['photo_tone']=tone
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
            self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
            bad=copy.deepcopy(plan);bad['heading_tone']=tone
            self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(bad)))
            bad=copy.deepcopy(plan);bad['blocks'][-1].update(style='italic_photo',shade_strength='soft')
            with self.assertRaisesRegex(ValueError,'requires a photographic fade'):measured_plan(card,bad)
        palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        for tone in ('auto','paper_dark','ink_light','paper_ink','paper_accent'):
            self.assertEqual(example_colours(palette,tone,'forest-cream'),photo_colours(palette,tone))

    def test_fresh_model_uses_free_backings_and_keeps_brightness_independent(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['blocks'][-1].update(photo_tone='paper_dark',backing_colour='#145638')
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            result,status=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertEqual(result['cards']['word']['blocks'][-1]['backing_colour'],'#145638')
        prompt=child.call_args.args[0]
        self.assertIn('whole-image HARMONY',prompt)
        self.assertIn('ONLY when the light and dark alternatives work EQUALLY WELL',prompt)
        self.assertIn('No predefined secondary-backing registry',prompt)
        self.assertNotIn(json.dumps(read_json(ROOT/'data/example-backings.json')),prompt)
        brightness=next(line for line in prompt.splitlines() if line.startswith('For LESSON/WORD brightness,'))
        self.assertNotIn('slightly',brightness)

    def test_public_summary_accepts_new_example_tones_but_never_as_title_tones(self):
        from easybosnian.success_report import report_data,with_rendering,render_report
        from test_success_report import RUN,results
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        placement,_=h.render(h.package,proposal)
        placement['cards']['word']['composition']['blocks'][-1]['photo_tone']='white_secondary'
        placement['cards']['word']['example_tone']='white_secondary'
        report=with_rendering(report_data(h.package,results(),RUN),placement)
        for text in render_report(report):self.assertIn('curated second dark backing',text)
        bad=copy.deepcopy(placement);bad['cards']['word']['heading_tone']='white_secondary'
        with self.assertRaisesRegex(ValueError,'Invalid safe colour/category metadata'):
            with_rendering(report_data(h.package,results(),RUN),bad)
