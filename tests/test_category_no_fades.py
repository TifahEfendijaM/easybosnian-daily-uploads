"""Category labels never shade the photograph, including bare underlined labels."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageChops
from easybosnian.core import ROOT,read_json
from easybosnian.designs import CATEGORY_STYLES
from easybosnian.hybrid import (category_label,default_plan,protect_text,render_hybrid,
                                CATEGORY_TOP,CATEGORY_HEIGHT)
from easybosnian.visual_placement import review_compositions
from test_project import reviewed_fixture
import test_visual_provenance as provenance_harness


class CategoryNoFadeTests(unittest.TestCase):
    def test_readable_underlined_labels_draw_only_their_glyphs_and_rule(self):
        palette=read_json(ROOT/'data/design-palettes.json')['slate-silver']
        for background,tone in [('#101010','auto'),('#f8f8f8','ink_paper')]:
            with self.subTest(background=background):
                before=Image.new('RGBA',(1080,1350),background);image=before.copy()
                result=category_label(image,'ZNAŠ LI?',palette,'underlined',tone=tone)
                self.assertEqual(result['shading'],0);self.assertGreaterEqual(result['contrast'],4.5)
                changed=ImageChops.difference(image.convert('RGB'),before.convert('RGB')).getbbox()
                self.assertGreaterEqual(changed[0],64);self.assertLess(changed[2],400)
                self.assertGreaterEqual(changed[1],CATEGORY_TOP)
                self.assertLessEqual(changed[3],CATEGORY_TOP+CATEGORY_HEIGHT+1)
                self.assertEqual(image.getpixel((900,100)),before.getpixel((900,100)))

    def test_unreadable_bare_label_is_rejected_without_adding_a_fade(self):
        palette=read_json(ROOT/'data/design-palettes.json')['slate-silver']
        image=Image.new('RGBA',(1080,1350),'#808080');before=image.tobytes()
        with self.assertRaisesRegex(ValueError,'Category text fails measured contrast'):
            category_label(image,'ZNAŠ LI?',palette,'underlined',tone='paper_ink')
        self.assertEqual(image.tobytes(),before)
        for style in CATEGORY_STYLES:
            if style=='underlined':continue
            image=Image.new('RGBA',(1080,1350),'#808080')
            with patch('easybosnian.hybrid.protect_text',side_effect=AssertionError('No chip fade call')):
                result=category_label(image,'RIJEČ DANA',palette,style)
            self.assertEqual(result['shading'],0)
            self.assertEqual(image.getpixel((900,100)),(128,128,128,255))

    def test_title_and_example_fades_never_modify_the_category_strip(self):
        card=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg'
            Image.new('RGB',(1080,1350),'#b0b0b0').save(photo)
            protected=(0,0,1080,CATEGORY_TOP+CATEGORY_HEIGHT+1)
            calls=[]
            def checked(image,*args,**kwargs):
                before=image.crop(protected).tobytes()
                result=protect_text(image,*args,**kwargs)
                self.assertEqual(image.crop(protected).tobytes(),before)
                calls.append(kwargs.get('allow_fade',True))
                return result
            for style in CATEGORY_STYLES:
                plan=dict(default_plan(card),confidence='high',palette='gold-cream',
                          category_style=style,heading_tone='paper_dark')
                plan['blocks'][-1]['photo_tone']='paper_dark'
                with patch('easybosnian.hybrid.protect_text',side_effect=checked):
                    result=render_hybrid(card,'gold-cream',photo,root/f'{style}.jpg',plan)
                self.assertGreater(result['heading_shading'],0)
                self.assertEqual(result['composition'],plan)
                self.assertGreaterEqual(result['category_contrast'],4.5)
            self.assertTrue(any(calls))

    def test_unreadable_model_category_uses_reported_layout_fallback_and_preserves_palette(self):
        harness=provenance_harness.VisualProvenanceTests();harness.setUp()
        proposal=harness.proposal(harness.package)
        proposal['cards']['word'].update(category_style='underlined',category_tone='paper_ink')
        placement,metrics=harness.render(harness.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['provenance']['layout']['source'],'fallback')
        self.assertEqual(word['provenance']['palette']['source'],'chatgpt')
        self.assertEqual(word['rejection']['reason'],'Category text fails measured contrast')
        self.assertEqual(metrics['word']['category_style'],'rounded')
        self.assertEqual(word['rejection']['proposal']['category_style'],'underlined')
        self.assertTrue(all(placement['cards'][k]['status']=='accepted' for k in ('quiz','lesson')))

    def test_review_instructions_explicitly_prohibit_all_category_fades(self):
        package=reviewed_fixture()
        base={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(base)) as child:
            review,status=review_compositions(package,{k:{'sheet':k+'.jpg'} for k in base['cards']})
        self.assertEqual(status,'reviewed');self.assertNotIn('card_failures',review)
        child.assert_called_once()
        prompt=child.call_args.args[0]
        for text in ('Category labels NEVER have a fade','applies to underlined categories',
                     'title fade cannot extend into the category','bounded approved category chip'):
            self.assertIn(text,prompt)
