"""Two real shade presets, shared example padding/clearance, and honest reports."""
import copy
import unittest
from PIL import Image
from easybosnian.designs import BODY_STYLES, REVIEW_FADE_STYLES
from easybosnian.hybrid import (protect_text,serif,default_plan,editorial_plan,
    measured_plan,render_hybrid,EXAMPLE_FADE_PADDING,EXAMPLE_BLOCK_GAP)
from easybosnian.render import measure
from easybosnian.success_report import report_data,with_rendering,render_report
from easybosnian.visual_history import accepted_choices
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as provenance_harness


class DefinedShadeTests(unittest.TestCase):
    def test_earlier_linear_shade_is_distinct_and_extends_below_text_without_becoming_smooth(self):
        source=Image.new('RGBA',(1080,1350),'#b0b0b0');face=serif(34,True)
        rows=['Čuvamo svoju riječ.'];bottom=1000+measure(rows,face)[0];images={}
        for preset in REVIEW_FADE_STYLES:
            image=source.copy()
            _,score,alpha=protect_text(image,(64,1000),rows,face,['#ffffff'],4.5,
                (0,970,1080,1286),fade_style=preset,bottom_padding=EXAMPLE_FADE_PADDING)
            self.assertGreaterEqual(score,4.5)
            self.assertEqual(image.getpixel((540,bottom+2)),image.getpixel((540,bottom+17)))
            self.assertNotEqual(image.getpixel((540,bottom+17)),source.getpixel((540,bottom+17)))
            self.assertEqual(image.getpixel((540,bottom+18+48)),source.getpixel((540,bottom+18+48)))
            self.assertEqual(image.crop((0,0,1080,970)).tobytes(),source.crop((0,0,1080,970)).tobytes())
            if preset=='defined':
                # An exact linear 50% taper and a defined boundary, not smoothstep.
                self.assertEqual(image.getpixel((540,bottom+18+24))[0],
                                 round(176*(1-round(alpha*.5)/255)))
                self.assertNotEqual(image.getpixel((540,970)),source.getpixel((540,970)))
            else:self.assertEqual(image.getpixel((540,970)),source.getpixel((540,970)))
            images[preset]=image.tobytes()
        self.assertNotEqual(images['standard'],images['defined'])

    def test_breathing_room_applies_to_every_panel_style_with_either_shade(self):
        card=reviewed_fixture()['cards'][2];card.update(body='Ovo je kratko objašnjenje.',example='Ovo je primjer.')
        for style in set(BODY_STYLES)-{'plain'}:
            for preset in REVIEW_FADE_STYLES:
                with self.subTest(style=style,preset=preset):
                    plan=default_plan(card);plan['heading_fade']=preset
                    plan['blocks'][0].update(style=style,y=700,font_size=32)
                    plan['blocks'][1]['fade_style']=preset
                    bottom=measured_plan(card,plan)[0]['bounds'][3]
                    plan['blocks'][1]['y']=round(bottom)+EXAMPLE_BLOCK_GAP-1
                    with self.assertRaisesRegex(ValueError,'breathing room'):measured_plan(card,plan)
                    plan['blocks'][1]['y']+=1
                    measured_plan(card,plan)
        # Editorial footer also retains the same text clearance rule.
        plan=editorial_plan(card);bottom=measured_plan(card,plan)[0]['bounds'][3]
        plan['blocks'][1]['y']=round(bottom)+EXAMPLE_BLOCK_GAP-1
        with self.assertRaisesRegex(ValueError,'breathing room'):measured_plan(card,plan)

    def test_accepted_preset_choices_survive_rendering_and_appear_in_summary_and_recent_context(self):
        h=provenance_harness.VisualProvenanceTests();h.setUp()
        proposal=h.proposal(h.package)
        for plan in proposal['cards'].values():
            if plan['photo_window'] is None:plan['heading_fade']='defined'
            for block in plan['blocks']:
                if block['style']=='italic_photo_fade':block['fade_style']='defined'
        original=copy.deepcopy(h.package['cards'])
        placement,metrics=h.render(h.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['status'],'accepted')
        self.assertEqual(word['provenance']['layout']['source'],'chatgpt')
        self.assertEqual(word['composition']['heading_fade'],'defined')
        self.assertEqual(word['composition']['blocks'][-1]['fade_style'],'sharp')
        self.assertGreaterEqual(metrics['word']['heading_contrast'],3)
        self.assertGreaterEqual(metrics['word']['example_contrast'],4.5)
        self.assertEqual(h.package['cards'],original)
        text,markup=render_report(with_rendering(report_data(h.package,results(),RUN),placement))
        for document in (text,markup):
            self.assertIn('Title fade: defined',document)
            self.assertIn('PRIMJER fade: sharp',document)
        recent=accepted_choices(placement)['word']
        self.assertEqual(recent['heading_fade'],'defined')
        self.assertNotIn('example_fade',recent)  # Random policy is not a ChatGPT choice.

    def test_inactive_and_unsupported_presets_are_rejected_without_adding_shading(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan['blocks'][-1].update(style='italic_photo',fade_style='defined')
        with self.assertRaisesRegex(ValueError,'Only photographic faded examples'):measured_plan(card,plan)
        plan=editorial_plan(card);plan['heading_fade']='defined'
        with self.assertRaisesRegex(ValueError,'Paper headings cannot select'):measured_plan(card,plan)
        plan=default_plan(card);plan['heading_fade']='custom border'
        with self.assertRaisesRegex(ValueError,'Invalid hybrid composition contract'):measured_plan(card,plan)


if __name__=='__main__':unittest.main()
