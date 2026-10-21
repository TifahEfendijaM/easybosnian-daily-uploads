"""Neutral title backings, separate example colours, and symmetric palette policy."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.designs import PHOTO_TONES,REVIEW_TITLE_TONES
from easybosnian.hybrid import default_plan,photo_colours,title_colours,render_hybrid
from easybosnian.visual_history import palette_policy,palette_policies
from easybosnian.visual_placement import MODEL_CARD_SCHEMA,review_compositions
from easybosnian.success_report import report_data,with_rendering,render_report
from test_project import reviewed_fixture
from test_success_report import RUN,results


class NeutralTitlesPaletteVarietyTests(unittest.TestCase):
    def test_every_title_colour_uses_only_neutral_backing_and_preserves_text_colour(self):
        for palette in read_json(ROOT/'data/design-palettes.json').values():
            for tone in PHOTO_TONES:
                colours,backings=title_colours(palette,tone)
                self.assertEqual(colours,photo_colours(palette,tone)[0])
                if tone!='auto':self.assertIn(backings[0][1],((0,0,0),(255,255,255)))
        palette=read_json(ROOT/'data/design-palettes.json')['terracotta-sand']
        self.assertNotIn(photo_colours(palette,'paper_ink')[1][0][1],((0,0,0),(255,255,255)))
        self.assertEqual(title_colours(palette,'paper_ink')[1][0][1],(0,0,0))
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),palette='gold-cream')
        for tone in PHOTO_TONES:
            plan['heading_tone']=tone
            self.assertEqual(not list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)),tone in REVIEW_TITLE_TONES)
        plan['heading_tone']='#123456'
        self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))

    def test_real_coloured_title_has_neutral_pixels_while_example_colour_choice_and_copy_survive(self):
        card=reviewed_fixture()['cards'][2];original=copy.deepcopy(card)
        plan=dict(default_plan(card),heading_tone='accent_dark')
        plan['blocks'][-1]['photo_tone']='paper_ink'
        palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';output=root/'card.jpg'
            Image.new('RGB',(1080,1350),'white').save(photo)
            result=render_hybrid(card,'gold-cream',photo,output,plan)
            self.assertEqual(result['heading_backing'],'#000000')
            self.assertEqual(result['heading_colour'],palette['accent'])
            self.assertEqual(result['example_tone'],'paper_ink')
            self.assertGreaterEqual(result['heading_contrast'],3)
            self.assertGreaterEqual(result['example_contrast'],4.5)
            with Image.open(output) as image:
                red,green,blue=image.getpixel((1070,200))
                self.assertLess(red,255);self.assertLessEqual(max(red,green,blue)-min(red,green,blue),2)
        self.assertEqual(result['composition'],plan);self.assertEqual(card,original)

    def test_every_palette_has_the_same_window_and_batch_policy_and_exception(self):
        palettes=list(read_json(ROOT/'data/design-palettes.json'))
        for candidate in palettes:
            with self.subTest(palette=candidate):
                other=[p for p in palettes if p!=candidate]
                window=[other[0]]*6+[candidate,candidate]
                policy=palette_policies(window)[candidate]
                self.assertEqual((policy['max_uses'],policy['window_size'],policy['max_per_batch']),(2,9,1))
                self.assertTrue(policy['alternatives_first'])
                self.assertTrue(palette_policy([], [candidate],candidate)['alternatives_first'])
                self.assertFalse(palette_policy([candidate]+other[:7]+[candidate],palette=candidate)['alternatives_first'])
                package=reviewed_fixture();package['design_palette']=other[0]
                plans={c['kind']:dict(default_plan(c),confidence='high',palette=p)
                       for c,p in zip(package['cards'],[candidate,other[1],candidate])}
                candidates={k:{'sheet':k+'.jpg'} for k in plans}
                with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'cards':plans})):
                    rejected,status=review_compositions(package,candidates)
                self.assertEqual(status,'reviewed')
                self.assertEqual(rejected['palette_decisions']['quiz']['source'],'chatgpt')
                self.assertEqual(rejected['palette_decisions']['word']['source'],'fallback')
                plans['word']['palette_exception']='no_other_suitable_palette'
                with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'cards':plans})):
                    accepted,_=review_compositions(package,candidates)
                self.assertEqual(accepted['palette_decisions']['word']['source'],'chatgpt')
                self.assertNotIn('card_failures',accepted)

    def test_prompt_gives_example_presets_equal_consideration_and_reporting_names_actual_title_backing(self):
        package=reviewed_fixture();palettes=['gold-cream','forest-cream','blue-ice']
        plans={c['kind']:dict(default_plan(c),palette=p,confidence='high') for c,p in zip(package['cards'],palettes)}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'cards':plans})) as child:
            reviewed,status=review_compositions(package,{k:{'sheet':k+'.jpg'} for k in plans})
        self.assertEqual(status,'reviewed')
        prompt=child.call_args.args[0]
        self.assertIn('Give BOTH PRIMJER presets equal consideration',prompt)
        self.assertIn('restriction applies EQUALLY to EVERY approved palette',prompt)
        self.assertIn('ONLY neutral black or white',prompt)
        self.assertNotIn('explicit terracotta-sand restriction',prompt)
        from test_success_report import SuccessReportTests
        rendered=SuccessReportTests().rendering(package)
        for card in rendered['cards'].values():card['heading_backing']='#000000'
        report=with_rendering(report_data(package,results(),RUN),rendered)
        for document in render_report(report):self.assertIn('Applied title backing: neutral black',document)
        rendered['cards']['word']['heading_backing']='#123456'
        with self.assertRaisesRegex(ValueError,'title backing'):with_rendering(report_data(package,results(),RUN),rendered)
