"""Role-specific opacity, lighter white titles and freely ordered examples."""
import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.hybrid import (default_plan,measured_plan,render_hybrid,protect_text,serif,
    TITLE_SHADE_LEVELS,TITLE_WHITE_SHADE_LEVELS,TITLE_SURROUND_OPACITY,
    TITLE_WHITE_SURROUND_OPACITY)
from easybosnian.visual_placement import MODEL_CARD_SCHEMA,CARD_SCHEMA
from easybosnian.visual_policy import apply_policy,policy_metadata,safe_policy
from easybosnian.selection import novelty_history
from easybosnian.validate import validate
from test_project import reviewed_fixture


class OctoberVisualRulesTests(unittest.TestCase):
    def test_new_answers_are_opaque_new_bodies_start_at_85_and_prior_random_reports_stay_readable(self):
        package=reviewed_fixture();fresh=Draft202012Validator(MODEL_CARD_SCHEMA)
        word=dict(default_plan(package['cards'][2]),palette='gold-cream')
        quiz=dict(default_plan(package['cards'][0]),palette='gold-cream')
        for opacity in (70,84.9,85,87.5,100):
            word['blocks'][0]['panel_opacity']=opacity
            self.assertEqual(bool(list(fresh.iter_errors(word))),opacity<85)
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(word)))
            for block in quiz['blocks']:block['panel_opacity']=opacity
            self.assertEqual(bool(list(fresh.iter_errors(quiz))),opacity!=100)
            old={'panel_opacity':opacity,'panel_opacity_applied':True,
                 'example_fade':None,'example_fade_applied':False}
            self.assertEqual(safe_policy(old,quiz),old)
            current=dict(old,version=2)
            if opacity==100:self.assertEqual(safe_policy(current,quiz),current)
            else:
                with self.assertRaises(ValueError):safe_policy(current,quiz)
        quiz=default_plan(package['cards'][0])
        with self.assertRaisesRegex(ValueError,'fully opaque'):apply_policy(quiz,panel_opacity=90)

    def test_white_title_backings_are_lighter_outside_letters_and_black_backings_are_unchanged(self):
        for preset in ('standard','defined'):
            for white in (False,True):
                original=Image.new('RGBA',(1080,1350),'#202020' if white else '#b0b0b0')
                old=original.copy();new=original.copy()
                colour='#000000' if white else '#ffffff';backing=(255,255,255) if white else (0,0,0)
                args=((64,200),['Čuvaj svoju riječ.'],serif(74),[colour],3)
                kwargs=dict(backings=[(colour,backing)],fade_style=preset,feather=100,
                            shade_levels=TITLE_SHADE_LEVELS,feather_power=2.5,
                            surround_opacity=TITLE_SURROUND_OPACITY)
                before=protect_text(old,*args,**kwargs)
                after=protect_text(new,*args,**kwargs,light_shade_levels=TITLE_WHITE_SHADE_LEVELS,
                                   light_surround_opacity=TITLE_WHITE_SURROUND_OPACITY)
                self.assertGreaterEqual(after[1],3)
                if white:
                    self.assertLessEqual(after[2],before[2])
                    self.assertLess(new.getpixel((1070,220))[0],old.getpixel((1070,220))[0])
                else:self.assertEqual(new.tobytes(),old.tobytes())

    def test_example_above_explanation_passes_geometry_and_real_pixel_checks(self):
        card=reviewed_fixture()['cards'][2]
        card.update(body='A short explanation.',example='Ovo je naš primjer.')
        source=copy.deepcopy(card);plan=default_plan(card);plan['heading_tone']='paper_dark'
        plan['blocks'][0]['y']=900
        plan['blocks'][1].update(y=520,photo_tone='paper_dark')
        plan=apply_policy(plan,panel_opacity=91)
        body,example=measured_plan(card,plan)
        self.assertLess(example['bounds'][3]+32,body['bounds'][1])
        self.assertEqual([b['role'] for b in plan['blocks']],['body','example'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#202020').save(photo)
            result=render_hybrid(card,'gold-cream',photo,root/'above.jpg',plan)
        self.assertGreaterEqual(result['example_contrast'],4.5)
        self.assertGreaterEqual(result['body_contrast'],4.5)
        self.assertEqual(result['composition'],plan);self.assertEqual(card,source)
        self.assertTrue(policy_metadata(plan,panel_opacity=91)['example_fade_applied'])

    def test_new_theme_checks_all_retained_rows_and_renamed_aliases_but_not_removed_rows(self):
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        package['theme']={'name':'Pljusak na ulici','equivalence_keys':['rainy weather']}
        for date in ('2026-09-27',package['date'],'2026-10-21'):
            with self.subTest(date=date):
                history={'days':[{'batch_id':'b-'+'b'*32,'date':date,'content':{
                    'theme':{'name':'Kišni dan','equivalence_keys':['Rainy weather']},
                    'words':[{'lemma':'other old word','equivalence_keys':[]}]}},
                    {'batch_id':'b-'+'c'*32,'date':package['date'],'content':{
                    'theme':{'name':'Biciklizam','equivalence_keys':['cycling']},
                    'words':[{'lemma':'different old word','equivalence_keys':[]}]}}]}
                original=copy.deepcopy(history)
                checked=novelty_history(history,package['date'],{'choice':'new'})
                self.assertEqual(len(checked['days']),2)
                with self.assertRaisesRegex(ValueError,'repeats history'):
                    validate(package,checked,include_today=True)
                remaining={'days':checked['days'][1:]}
                validate(package,novelty_history(remaining,package['date'],{'choice':'new'}),include_today=True)
                self.assertEqual(history,original)
