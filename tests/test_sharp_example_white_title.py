"""Soft-top/crisp-bottom examples, title choices and honest archived policies."""
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
    def test_defined_example_blends_top_only_and_keeps_bottom_padding_for_multiple_colour_pairs(self):
        palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        face=serif(34,True);label=font(21,'SemiBold');rows=['Čuvamo svoju riječ.']
        bottom=max(1040+measure(rows,face)[0],1000+measure(['PRIMJER'],label)[0])+EXAMPLE_FADE_PADDING
        for tone,limit_top in ((t,y) for t in ('paper_dark','ink_light','paper_ink','ink_paper') for y in (950,995)):
            with self.subTest(tone=tone,limit_top=limit_top):
                original=Image.new('RGBA',(1080,1350),'#202020' if tone.startswith('ink') else '#b0b0b0');image=original.copy()
                colours,backings=photo_colours(palette,tone)
                colour,score,alpha=protect_text(image,(64,1040),rows,face,colours,4.5,
                    (20,limit_top,1060,1280),extra=[((64,1000),['PRIMJER'],label)],backings=backings,
                    fade_style='sharp',bottom_padding=EXAMPLE_FADE_PADDING)
                self.assertGreaterEqual(score,4.5);self.assertGreater(alpha,0)
                pixel=image.getpixel((1000,1000))
                base=original.getpixel((1000,1000))
                # A real gradual upper blend, including when the protected
                # photo edge leaves less space than the normal upper padding.
                changes=[max(abs(a-b) for a,b in zip(image.getpixel((1000,y)),base))
                         for y in (limit_top,(limit_top+1000)//2,1000)]
                self.assertEqual(changes[0],0)
                self.assertGreater(changes[1],0);self.assertLess(changes[1],changes[2])
                self.assertEqual(image.crop((0,0,1080,limit_top)).tobytes(),
                                 original.crop((0,0,1080,limit_top)).tobytes())
                if limit_top==950:
                    self.assertEqual(image.getpixel((1000,1000-SHARP_EXAMPLE_TOP_PADDING)),pixel)
                # The lower edge remains a distinct, crisp boundary, rather
                # than turning this into the fully smooth standard preset.
                self.assertEqual(image.getpixel((1000,bottom)),pixel)
                self.assertEqual(image.getpixel((1000,bottom+1)),original.getpixel((1000,bottom+1)))
                self.assertEqual(image.getpixel((10,1040)),original.getpixel((10,1040)))
                self.assertEqual(image.getpixel((1059,1040)),pixel)
                smooth=original.copy()
                protect_text(smooth,(64,1040),rows,face,colours,4.5,
                    (20,limit_top,1060,1280),extra=[((64,1000),['PRIMJER'],label)],backings=backings,
                    fade_style='standard',bottom_padding=EXAMPLE_FADE_PADDING)
                self.assertNotEqual(smooth.getpixel((1000,bottom+1)),original.getpixel((1000,bottom+1)))

    def test_selected_example_and_title_presets_survive_for_both_neutral_backings(self):
        cards=reviewed_fixture()['cards']
        for tone in ('paper_dark','ink_light','ink_paper','accent_dark','accent_light'):
            for preset in ('standard','defined'):
                plan=default_plan(cards[2]);plan.update(heading_tone=tone,heading_fade=preset)
                original=copy.deepcopy(plan)
                final=apply_policy(plan,panel_opacity=100)
                self.assertEqual(final['blocks'][-1]['fade_style'],plan['blocks'][-1]['fade_style'])
                self.assertEqual(final['heading_fade'],preset)
                self.assertEqual(plan,original)
        final['heading_fade']='sharp'
        self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(final)))

    def test_automatic_white_backing_preserves_both_edge_choices_with_real_pixel_checks(self):
        card=reviewed_fixture()['cards'][2];card['heading']='Čuvaj svoju riječ.'
        pixels=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg'
            image=Image.new('RGB',(1080,1350),'black');ImageDraw.Draw(image).rectangle((160,0,1079,1349),fill='white');image.save(photo)
            for preset in ('standard','defined'):
                plan=default_plan(card);plan.update(heading_tone='auto',heading_fade=preset)
                original=copy.deepcopy(plan);output=root/f'{preset}.jpg'
                result=render_hybrid(card,'gold-cream',photo,output,plan)
                self.assertEqual(result['heading_backing'],'#ffffff')
                self.assertEqual(result['composition']['heading_fade'],preset)
                self.assertGreaterEqual(result['heading_contrast'],3)
                self.assertEqual(plan,original)
                with Image.open(output) as rendered:pixels.append(rendered.crop((0,145,1080,285)).tobytes())
        self.assertNotEqual(*pixels)

    def test_pipeline_and_reports_show_model_selected_sharp_and_read_archived_policies(self):
        h=provenance_harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['heading_tone']='ink_light'
        proposal['cards']['word']['blocks'][-1]['fade_style']='sharp'
        placement,_=h.render(h.package,proposal)
        word=placement['cards']['word'];self.assertEqual(word['render_policy']['version'],7)
        self.assertEqual(word['composition']['heading_fade'],'standard')
        self.assertEqual(accepted_choices(placement)['word']['heading_fade'],'standard')
        self.assertEqual(word['composition']['blocks'][-1]['fade_style'],'sharp')
        text,markup=render_report(with_rendering(report_data(h.package,results(),RUN),placement))
        for document in (text,markup):
            self.assertIn('ChatGPT',document);self.assertIn('sharp applied',document)
            self.assertNotIn('random 50/50',document)
            self.assertIn('Title fade: standard',document)
            self.assertNotIn('White title edge: fixed',document)
        for version in (None,2,3,4):
            plan=default_plan(h.package['cards'][2])
            old={'panel_opacity':100,'panel_opacity_applied':True,'example_fade':'standard','example_fade_applied':True}
            if version is not None:old['version']=version
            if version==3:
                old['example_fade']='sharp';plan['blocks'][-1]['fade_style']='sharp'
            self.assertEqual(safe_policy(old,plan),old)
        bad=copy.deepcopy(placement);bad['cards']['word']['heading_backing']='#ffffff'
        bad['cards']['word']['render_policy']['version']=4
        bad['cards']['word']['composition']['heading_fade']='standard'
        with self.assertRaisesRegex(ValueError,'White title edge'):
            with_rendering(report_data(h.package,results(),RUN),bad)
