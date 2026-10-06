"""Measured fallback, safe diagnostics and real category/colour/answer treatments."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from PIL import Image

from easybosnian.designs import CATEGORY_STYLES, PHOTO_TONES
from easybosnian.hybrid import default_plan, measured_plan, render_hybrid
from easybosnian.visual_diagnostics import rejection_diagnostic, safe_rejection
from easybosnian.visual_placement import RESULT_SCHEMA, review_compositions
from easybosnian.success_report import report_data, with_rendering, render_report
from test_project import reviewed_fixture
from test_success_report import RUN, results


class VisualRefinementTests(unittest.TestCase):
    def test_fallback_examples_are_lower_and_still_measured_logo_safe_without_changing_copy(self):
        for card in reviewed_fixture()['cards'][1:]:
            card=copy.deepcopy(card);card.setdefault('example','Danas koristim ovu riječ.')
            before=copy.deepcopy(card)
            measured=measured_plan(card,default_plan(card))
            body,example=measured
            self.assertGreaterEqual(example['y'],900)
            self.assertGreater(example['y']-body['bounds'][3],100)
            self.assertLessEqual(example['bounds'][3],1170)
            self.assertEqual(example['rows'].reconstructed(),card['example'])
            self.assertEqual(card,before)

        # Long lower examples move upward only as far as their measured height needs.
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['example']=' '.join(['Čuvamo sva slova i značenja.']*5)
        measured=measured_plan(card,default_plan(card))
        self.assertEqual(measured[-1]['bounds'][3],1150)
        self.assertGreaterEqual(measured[-1]['y'],measured[0]['bounds'][3]+14)

    def test_stories_reuse_category_treatment_without_a_second_model_call(self):
        from easybosnian.story_layouts import tall_story_image
        from easybosnian.core import ROOT,read_json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#78644e').save(photo)
            palette=read_json(ROOT/'data/design-palettes.json')['terracotta-sand']
            for card in reviewed_fixture()['cards']:
                metrics=tall_story_image(card,photo,root/'story.jpg',palette,category_style='ribbon')
                self.assertEqual(metrics['category_style'],'ribbon')
                self.assertEqual(metrics['size'],[1080,1920])

    def test_exact_trusted_error_and_approved_parameters_survive_without_freeform_text(self):
        plan=dict(default_plan(reviewed_fixture()['cards'][2]),palette='terracotta-sand')
        plan['blocks'][0]['y']=200  # Schema-approved parameter, invalid measured geometry.
        reason='Composition intersects the fixed heading, margin or logo strip'
        diagnostic=rejection_diagnostic(ValueError(reason),plan)
        self.assertEqual(diagnostic,{'reason':reason,'proposal':plan})
        self.assertEqual(safe_rejection(diagnostic),diagnostic)
        plan['blocks'][0]['text']='private arbitrary model text'
        safe=rejection_diagnostic(ValueError('secret credential/provider text'),plan)
        self.assertIsNone(safe['proposal'])
        self.assertNotIn('private',str(safe));self.assertNotIn('secret',str(safe))
        for bad in ({'reason':'secret prose','proposal':None},
                    {'reason':reason,'proposal':plan},
                    {'reason':reason,'proposal':None,'extra':'secret'}):
            with self.assertRaises(ValueError):safe_rejection(bad)

    def test_categories_are_six_distinct_renderers_with_original_bosnian_labels(self):
        card=reviewed_fixture()['cards'][1];before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#78644e').save(photo)
            outputs=[]
            for style in CATEGORY_STYLES:
                plan=default_plan(card);plan['category_style']=style
                metrics=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg',plan)
                self.assertEqual(metrics['category_style'],style)
                self.assertGreaterEqual(metrics['category_contrast'],4.5)
                with Image.open(root/'card.jpg') as image:outputs.append(image.crop((50,45,500,145)).tobytes())
            self.assertEqual(len(set(outputs)),6)
            self.assertEqual(card,before)

    def test_explicit_dark_light_and_palette_tones_are_measured_for_title_and_italic_example(self):
        card=reviewed_fixture()['cards'][2];before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#828282').save(photo)
            for tone in PHOTO_TONES:
                plan=default_plan(card);plan['heading_tone']=tone;plan['blocks'][-1]['photo_tone']=tone
                metrics=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg',plan)
                self.assertEqual(metrics['heading_tone'],tone);self.assertEqual(metrics['example_tone'],tone)
                self.assertGreaterEqual(metrics['heading_contrast'],3)
                self.assertGreaterEqual(metrics['example_contrast'],4.5)
                if tone.startswith('ink_'):
                    self.assertEqual(metrics['heading_colour'],'#44271e')
                    self.assertEqual(metrics['example_colour'],'#44271e')
                if tone.startswith('paper_'):self.assertEqual(metrics['example_colour'],'#fff3e4')
                if tone=='accent_ink':self.assertEqual(metrics['example_colour'],'#f0b18f')
            self.assertEqual(card,before)
            # An explicit colour is never permission to invent a fade for italic_photo.
            plan=default_plan(card);plan['blocks'][-1].update(style='italic_photo',photo_tone='paper_dark')
            with self.assertRaisesRegex(ValueError,'contrast'):render_hybrid(card,'terracotta-sand',photo,root/'bad.jpg',plan)

    def test_pill_answer_is_distinct_from_rounded_and_remains_independent_of_badge(self):
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#78644e').save(photo)
            images=[]
            for style in ('rounded','pill'):
                plan=default_plan(quiz)
                for block in plan['blocks']:block.update(style=style,marker_style='triangle')
                metrics=render_hybrid(quiz,'terracotta-sand',photo,root/'card.jpg',plan)
                self.assertEqual(set(metrics['answer_badges'].values()),{'triangle'})
                images.append((root/'card.jpg').read_bytes())
            self.assertNotEqual(*images)
        card=reviewed_fixture()['cards'][2];plan=default_plan(card);plan['blocks'][0]['style']='pill'
        with self.assertRaises(ValueError):measured_plan(card,plan)

    def test_schema_rejects_custom_colours_and_body_tones_and_prompt_prefers_coherent_batch_palette(self):
        package=reviewed_fixture()
        proposal={'cards':{c['kind']:dict(default_plan(c),palette='terracotta-sand') for c in package['cards']}}
        validator=Draft202012Validator(RESULT_SCHEMA)
        self.assertFalse(list(validator.iter_errors(proposal)))
        for scope,field,value in [('card','heading_tone','#112233'),('card','category_style','arbitrary'),
                                  ('body','photo_tone','paper_dark'),('example','photo_tone','custom')]:
            bad=copy.deepcopy(proposal);target=bad['cards']['word']
            if scope!='card':target=next(b for b in target['blocks'] if b['role']==scope)
            target[field]=value
            self.assertTrue(list(validator.iter_errors(bad)))
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in proposal['cards']})
        prompt=child.call_args.args[0]
        self.assertIn('ALL THREE actual photos together',prompt)
        self.assertIn('same best-fitting palette across all three',prompt)
        self.assertIn('differences between the photographs justify',prompt)
        self.assertIn('Category catalogue:',prompt);self.assertIn('Photo-colour catalogue:',prompt)
        self.assertNotIn('private_review',prompt)

    def test_success_report_exposes_safe_rejection_but_refuses_arbitrary_diagnostics(self):
        package=reviewed_fixture();plan=dict(default_plan(package['cards'][2]),palette='terracotta-sand')
        reason='Composition text blocks overlap or have no breathing room'
        placement={'batch':package['date'],'batch_id':package['date'],'cards':{
            k:{'position':'normal','palette':'terracotta-sand','design':'hybrid','block_styles':{}}
            for k in ('quiz','lesson','word')}}
        placement['cards']['word']['rejection']=rejection_diagnostic(ValueError(reason),plan)
        report=with_rendering(report_data(package,results(),RUN),placement)
        text,markup=render_report(report)
        self.assertIn(reason,text);self.assertIn(reason,markup)
        self.assertIn('Rejected approved rendering parameters',text)
        self.assertNotIn('private_review',text)
        placement['cards']['word']['rejection']['reason']='private model reasoning'
        with self.assertRaises(ValueError):with_rendering(report_data(package,results(),RUN),placement)


if __name__=='__main__':unittest.main()
