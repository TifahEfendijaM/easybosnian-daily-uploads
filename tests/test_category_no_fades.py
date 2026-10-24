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

    def test_title_fade_can_reach_category_but_category_is_composited_on_top(self):
        card=reviewed_fixture()['cards'][2]
        palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#b0b0b0').save(photo)
            order=[]
            def shaded(image,*args,**kwargs):
                order.append('shade');return protect_text(image,*args,**kwargs)
            def layered(image,*args,**kwargs):
                result=category_label(image,*args,**kwargs)
                order.append('category')
                if args[2]!='underlined':
                    from PIL import ImageColor
                    self.assertEqual(image.getpixel((80,95))[:3],ImageColor.getrgb(palette['panel']))
                return result
            for style in CATEGORY_STYLES:
                order.clear()
                plan=dict(default_plan(card),confidence='high',category_style=style,
                          category_tone='ink_paper',heading_tone='paper_dark')
                with patch('easybosnian.hybrid.protect_text',side_effect=shaded),patch('easybosnian.hybrid.category_label',side_effect=layered):
                    result=render_hybrid(card,'gold-cream',photo,root/f'{style}.jpg',plan)
                self.assertGreater(result['heading_shading'],0)
                self.assertGreaterEqual(result['category_contrast'],4.5)
                self.assertEqual(order[-1],'category')

    def test_unreadable_model_category_uses_reported_layout_fallback_and_preserves_palette(self):
        harness=provenance_harness.VisualProvenanceTests();harness.setUp()
        proposal=harness.proposal(harness.package)
        proposal['cards']['word'].update(category_style='underlined',category_tone='paper_ink')
        placement,metrics=harness.render(harness.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['provenance']['layout']['source'],'mixed')
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
        for text in ('Category labels NEVER add their own fade','applies to underlined categories',
                     'TITLE fade may extend behind the category area','bounded approved category chip'):
            self.assertIn(text,prompt)
