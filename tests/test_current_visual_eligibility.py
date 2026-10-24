"""Fresh feed restrictions must apply to initial designs and all recovery draws."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.hybrid import default_plan,editorial_plan,validate_current_design,render_hybrid
from easybosnian.design_repair import render_design
from easybosnian.visual_placement import RESULT_SCHEMA,review_compositions
from easybosnian.designs import REVIEW_FADE_STYLES,REVIEW_EXAMPLE_FADE_STYLES
from test_project import reviewed_fixture
import test_visual_provenance as harness


class CurrentVisualEligibilityTests(unittest.TestCase):
    def test_only_picture_identification_quizzes_can_use_a_separate_photo(self):
        for card in reviewed_fixture()['cards']:
            plan=default_plan(card)
            if card['kind']!='quiz':validate_current_design(card,plan)
            candidate=copy.deepcopy(plan);candidate['photo_window']={'y':500,'height':500,'fit':'contain'}
            if card['kind']=='quiz':
                for kind in ('other','visual_identification'):
                    card['quiz_format']=kind
                    if kind=='visual_identification':validate_current_design(card,candidate)
                    else:
                        with self.assertRaisesRegex(ValueError,'picture-identification'):validate_current_design(card,candidate)
            else:
                with self.assertRaisesRegex(ValueError,'picture-identification'):validate_current_design(card,candidate)
                with self.assertRaises(ValueError):validate_current_design(card,editorial_plan(card))

    def test_model_transport_disallows_lesson_word_windows_and_defined_titles(self):
        fields=RESULT_SCHEMA['properties']['cards']['properties']
        for kind in ('lesson','word'):
            schema=fields[kind]['properties']['photo_window']
            self.assertFalse(list(Draft202012Validator(schema).iter_errors(None)))
            self.assertTrue(list(Draft202012Validator(schema).iter_errors({'y':500,'height':500,'fit':'contain'})))
        for kind in fields:
            schema=fields[kind]['properties']['heading_fade']
            self.assertFalse(list(Draft202012Validator(schema).iter_errors('standard')))
            self.assertTrue(list(Draft202012Validator(schema).iter_errors('defined')))
        self.assertEqual(REVIEW_FADE_STYLES,('standard',))
        self.assertEqual(REVIEW_EXAMPLE_FADE_STYLES,('standard','sharp'))

    def test_recovery_cannot_reintroduce_a_forbidden_window_and_keeps_valid_siblings(self):
        card=reviewed_fixture()['cards'][2];card.update(body='Short explanation.',example='Ovo je naš primjer.')
        plan=dict(default_plan(card),confidence='high',palette='copper-linen',photo_window={'y':500,'height':500,'fit':'contain'})
        before=copy.deepcopy(plan);seen=[]
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.jpg';Image.new('RGB',(1080,1350),'#777777').save(photo)
            def draw(p):
                seen.append(copy.deepcopy(p))
                return render_hybrid(card,'copper-linen',photo,Path(temp)/'card.jpg',p)
            metrics,detail=render_design(card,plan,photo,draw,model_accepted=True)
        self.assertTrue(seen);self.assertTrue(all(p['photo_window'] is None for p in seen))
        self.assertIsNone(metrics['composition']['photo_window'])
        self.assertEqual(metrics['composition']['blocks'],before['blocks'])
        self.assertEqual(detail['element_recovery']['fallback'],['photo_window'])
        self.assertEqual(plan,before)

    def test_obsolete_defined_title_recovery_keeps_the_body_and_example(self):
        card=reviewed_fixture()['cards'][2]
        plan=dict(default_plan(card),confidence='high',heading_fade='defined')
        with self.assertRaisesRegex(ValueError,'smooth edges'):validate_current_design(card,plan)
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.jpg';Image.new('RGB',(1080,1350),'#777777').save(photo)
            metrics,detail=render_design(card,plan,photo,lambda p:render_hybrid(card,'copper-linen',photo,Path(temp)/'card.jpg',p),model_accepted=True)
        self.assertEqual(metrics['composition']['heading_fade'],'standard')
        self.assertEqual(metrics['composition']['blocks'],plan['blocks'])
        self.assertEqual(detail['element_recovery']['fallback'],['heading'])

    def test_prompt_has_no_light_dark_preference_or_lesson_window_exception(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        candidates={c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=__import__('json').dumps(proposal)) as model:
            review_compositions(h.package,candidates)
        prompt=model.call_args.args[0]
        for phrase in ('Give EVERY approved palette equal consideration','Neither dark nor light palettes/panels are preferred',
                       'MUST use photo_window=null','NOT a lesson/word last resort','Sharp/crisp/defined title edges are NOT available'):
            self.assertIn(phrase,prompt)
        self.assertNotIn('A separate middle photo window is an EXCEPTIONAL LAST RESORT',prompt)

    def test_panel_theme_reflects_actual_surface_pairing_not_palette_name(self):
        from easybosnian.visual_history import panel_theme,accepted_choices
        card={'status':'accepted','design':'hybrid','palette':'gold-cream','block_styles':{'A':'rounded'},
              'composition':{'blocks':[{'role':'A','style':'rounded','panel_tone':'paper_ink','panel_opacity':100}]}}
        self.assertEqual(panel_theme(card),'dark')
        self.assertEqual(accepted_choices({'cards':{'quiz':card}})['quiz']['panel_theme'],'dark')
        card['composition']['blocks'][0]['panel_tone']='ink_paper'
        self.assertEqual(panel_theme(card),'light')
        card['composition']['blocks'].append({'role':'B','style':'overlay_dark','panel_tone':'auto','panel_opacity':100})
        self.assertEqual(panel_theme(card),'mixed')
        card['composition']['blocks'][0]['panel_opacity']=85
        self.assertEqual(panel_theme(card),'unknown')
        self.assertEqual(panel_theme({'palette':{},'composition':{}}),'unknown')

    def test_title_has_equal_smooth_upper_lower_extent_and_category_can_overlay(self):
        from easybosnian.hybrid import protect_text,serif,TITLE_FADE_PADDING,TITLE_FADE_FEATHER
        from easybosnian.render import measure
        source=Image.new('RGBA',(1080,1350),'#aaaaaa');image=source.copy()
        face=serif(44);rows=['Čuvamo svoju riječ.'];top=174;bottom=top+measure(rows,face)[0]
        protect_text(image,(64,top),rows,face,['#ffffff'],4.5,(0,0,1080,1350),
                     fade_style='standard',feather=TITLE_FADE_FEATHER,feather_power=2.5,
                     top_padding=TITLE_FADE_PADDING,bottom_padding=TITLE_FADE_PADDING,minimum_shade=90)
        for offset in (0,12,24,40,70,100,123,124):
            self.assertEqual(image.getpixel((540,top-offset)),image.getpixel((540,bottom+offset)))
        self.assertNotEqual(image.getpixel((540,100)),source.getpixel((540,100)))
        self.assertEqual(image.getpixel((540,top-124)),source.getpixel((540,top-124)))
        self.assertEqual(image.getpixel((540,bottom+124)),source.getpixel((540,bottom+124)))
