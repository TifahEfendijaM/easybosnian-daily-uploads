"""Crisp example bands and defined white titles are actual renderer policies."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import (protect_text,serif,default_plan,render_hybrid,
    photo_colours,EXAMPLE_FADE_PADDING,SHARP_EXAMPLE_TOP_PADDING)
from easybosnian.render import font,measure
from easybosnian.visual_policy import apply_policy,policy_metadata,safe_policy
from easybosnian.visual_placement import CARD_SCHEMA
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import report_data,with_rendering,render_report
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as provenance_harness


class SharpExampleWhiteTitleTests(unittest.TestCase):
    def test_sharp_band_has_exact_straight_edges_and_padding_with_multiple_colour_pairs(self):
        palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        face=serif(34,True);label=font(21,'SemiBold');rows=['Čuvamo svoju riječ.']
        bottom=max(1040+measure(rows,face)[0],1000+measure(['PRIMJER'],label)[0])+EXAMPLE_FADE_PADDING
        for tone in ('paper_dark','ink_light','paper_ink','ink_paper'):
            with self.subTest(tone=tone):
                original=Image.new('RGBA',(1080,1350),'#202020' if tone.startswith('ink') else '#b0b0b0');image=original.copy()
                colours,backings=photo_colours(palette,tone)
                colour,score,alpha=protect_text(image,(64,1040),rows,face,colours,4.5,
                    (20,950,1060,1280),extra=[((64,1000),['PRIMJER'],label)],backings=backings,
                    fade_style='sharp',bottom_padding=EXAMPLE_FADE_PADDING)
                self.assertGreaterEqual(score,4.5);self.assertGreater(alpha,0)
                top=1000-SHARP_EXAMPLE_TOP_PADDING
                pixel=image.getpixel((1000,top))
                self.assertNotEqual(pixel,original.getpixel((1000,top)))
                self.assertEqual(image.getpixel((1000,top-1)),original.getpixel((1000,top-1)))
                self.assertEqual(image.getpixel((1000,bottom)),pixel)
                self.assertEqual(image.getpixel((1000,bottom+1)),original.getpixel((1000,bottom+1)))
                self.assertEqual(image.getpixel((10,1040)),original.getpixel((10,1040)))
                self.assertEqual(image.getpixel((1059,1040)),pixel)

    def test_selected_examples_survive_and_only_white_title_intent_is_overridden(self):
        cards=reviewed_fixture()['cards']
        for tone in ('paper_dark','ink_light','ink_paper','accent_dark','accent_light'):
            for preset in ('standard','defined'):
                plan=default_plan(cards[2]);plan.update(heading_tone=tone,heading_fade=preset)
                original=copy.deepcopy(plan)
                final=apply_policy(plan,panel_opacity=90)
                self.assertEqual(final['blocks'][-1]['fade_style'],plan['blocks'][-1]['fade_style'])
                self.assertEqual(final['heading_fade'],'defined' if tone in ('ink_light','ink_paper','accent_light') else preset)
                self.assertEqual(plan,original)
        final['heading_fade']='sharp'
        self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(final)))

    def test_automatic_white_backing_uses_defined_edges_and_reports_the_effective_preset(self):
        card=reviewed_fixture()['cards'][2];card['heading']='Čuvaj svoju riječ.'
        plan=default_plan(card);plan.update(heading_tone='auto',heading_fade='standard')
        original=copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg'
            image=Image.new('RGB',(1080,1350),'black');ImageDraw.Draw(image).rectangle((160,0,1079,1349),fill='white');image.save(photo)
            result=render_hybrid(card,'gold-cream',photo,root/'title.jpg',plan)
        self.assertEqual(result['heading_backing'],'#ffffff')
        self.assertEqual(result['composition']['heading_fade'],'defined')
        self.assertGreaterEqual(result['heading_contrast'],3)
        self.assertEqual(plan,original)

    def test_pipeline_and_reports_show_model_selected_sharp_and_read_archived_policies(self):
        h=provenance_harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['heading_tone']='ink_light'
        proposal['cards']['word']['blocks'][-1]['fade_style']='sharp'
        placement,_=h.render(h.package,proposal)
        word=placement['cards']['word'];self.assertEqual(word['render_policy']['version'],4)
        self.assertEqual(word['composition']['heading_fade'],'defined')
        self.assertNotIn('heading_fade',accepted_choices(placement)['word'])
        self.assertEqual(word['composition']['blocks'][-1]['fade_style'],'sharp')
        text,markup=render_report(with_rendering(report_data(h.package,results(),RUN),placement))
        for document in (text,markup):
            self.assertIn('ChatGPT',document);self.assertIn('sharp applied',document)
            self.assertNotIn('random 50/50',document)
        for version in (None,2,3):
            plan=default_plan(h.package['cards'][2])
            old={'panel_opacity':100,'panel_opacity_applied':True,'example_fade':'standard','example_fade_applied':True}
            if version is not None:old['version']=version
            if version==3:
                old['example_fade']='sharp';plan['blocks'][-1]['fade_style']='sharp'
            self.assertEqual(safe_policy(old,plan),old)
        bad=copy.deepcopy(placement);bad['cards']['word']['heading_backing']='#ffffff'
        bad['cards']['word']['composition']['heading_fade']='standard'
        with self.assertRaisesRegex(ValueError,'White title edge'):
            with_rendering(report_data(h.package,results(),RUN),bad)
