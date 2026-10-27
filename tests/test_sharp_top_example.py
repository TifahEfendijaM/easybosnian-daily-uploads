"""The third PRIMJER edge treatment retains real contrast and safe boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import protect_text,serif,photo_colours,EXAMPLE_FADE_PADDING,SHARP_EXAMPLE_TOP_PADDING,measured_plan
from easybosnian.render import font,measure
from easybosnian.visual_placement import RESULT_SCHEMA,review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import report_data,with_rendering,render_report
from test_success_report import RUN,results
import test_visual_provenance as harness


class SharpTopExampleTests(unittest.TestCase):
    def test_crisp_top_and_smooth_bottom_for_neutral_and_palette_backings(self):
        palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        face=serif(34,True);label=font(21,'SemiBold');rows=['Čuvamo svoju riječ.']
        text_bottom=max(1040+measure(rows,face)[0],1000+measure(['PRIMJER'],label)[0])
        for tone in ('paper_dark','ink_light','paper_ink','ink_paper'):
            for lower in (1280,text_bottom+30):
                with self.subTest(tone=tone,lower=lower):
                    original=Image.new('RGBA',(1080,1350),'#202020' if tone.startswith('ink') else '#b0b0b0');image=original.copy()
                    colours,backings=photo_colours(palette,tone)
                    colour,score,alpha=protect_text(image,(64,1040),rows,face,colours,4.5,
                        (20,950,1060,lower),extra=[((64,1000),['PRIMJER'],label)],backings=backings,
                        fade_style='sharp_top',bottom_padding=EXAMPLE_FADE_PADDING)
                    self.assertGreaterEqual(score,4.5);self.assertGreater(alpha,0)
                    top=1000-SHARP_EXAMPLE_TOP_PADDING
                    self.assertEqual(image.getpixel((1000,top-1)),original.getpixel((1000,top-1)))
                    self.assertNotEqual(image.getpixel((1000,top)),original.getpixel((1000,top)))
                    self.assertEqual(image.getpixel((1000,top)),image.getpixel((1000,1040)))
                    end=min(lower-1,text_bottom+EXAMPLE_FADE_PADDING+48)
                    core=min(text_bottom+EXAMPLE_FADE_PADDING,max(text_bottom,end-16))
                    base=original.getpixel((1000,end));delta=lambda y:max(abs(a-b) for a,b in zip(image.getpixel((1000,y)),base))
                    self.assertGreater(delta(core),delta((core+end)//2));self.assertGreater(delta((core+end)//2),0)
                    self.assertEqual(delta(end),0)
                    self.assertEqual(image.crop((0,lower,1080,1350)).tobytes(),original.crop((0,lower,1080,1350)).tobytes())
                    self.assertEqual(image.getpixel((19,1040)),original.getpixel((19,1040)))
                    self.assertEqual(image.getpixel((1060,1040)),original.getpixel((1060,1040)))

    def test_schema_roundtrip_render_history_and_report_preserve_third_preset(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['blocks'][-1]['fade_style']='sharp_top'
        from easybosnian.hybrid import heading
        proposal['cards']['word']['blocks'][-1]['y']=round(heading(h.package['cards'][2])[2]+32)
        proposal['cards']['word']['blocks'][0]['y']=740
        self.assertFalse(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(proposal)))
        before=copy.deepcopy(proposal);placement,_=h.render(h.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['composition']['blocks'][-1]['fade_style'],'sharp_top')
        self.assertEqual(word['render_policy']['example_fade'],'sharp_top')
        self.assertEqual(accepted_choices(placement)['word']['example_fade'],'sharp_top')
        for document in render_report(with_rendering(report_data(h.package,results(),RUN),placement)):
            self.assertIn('sharp_top applied',document.replace('\\_','_'))
        self.assertEqual(proposal,before)
        for kind in proposal['cards']:
            invalid=copy.deepcopy(proposal);invalid['cards'][kind]['heading_fade']='sharp_top'
            self.assertTrue(list(Draft202012Validator(RESULT_SCHEMA).iter_errors(invalid)))
        invalid=copy.deepcopy(proposal['cards']['word']);invalid['blocks'][-1]['style']='italic_photo'
        with self.assertRaisesRegex(ValueError,'Only photographic faded examples'):measured_plan(h.package['cards'][2],invalid)

    def test_live_instructions_compare_normal_edges_without_automatic_reverse_selection(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        with patch('easybosnian.cloud_prepare.run_codex',return_value=__import__('json').dumps(proposal)) as model:
            review_compositions(h.package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']})
        prompt=model.call_args.args[0]
        for text in ('sharp_top has a crisp straight TOP and smoothly blended BOTTOM','with neither preferred or the default','Proximity is eligibility, NEVER an automatic selection'):
            self.assertIn(text,prompt)
        self.assertNotIn('equally considered for the actual photograph without a preferred preset',prompt)
        self.assertIn('wins there only if genuinely better, never automatically',prompt)
        for rule in ('Outside the LOWER photo area', 'STRONGLY PREFER sharp (smooth top/crisp bottom)',
                     'Keep standard available there when it CLEARLY fits', 'Keep colour and shade strength independent'):
            self.assertIn(rule,prompt)
