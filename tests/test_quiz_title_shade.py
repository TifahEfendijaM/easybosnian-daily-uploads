"""Approved quiz emphasis changes real pixels without opening arbitrary styling."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.hybrid import default_plan, editorial_plan, measured_plan, render_hybrid, QUIZ_TITLE_MIN_SHADE
from easybosnian.visual_placement import CARD_SCHEMA, MODEL_CARD_SCHEMA, review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.design_repair import unchanged
from easybosnian.element_recovery import recover_elements
from easybosnian.success_report import with_rendering, report_data, render_report
from test_project import reviewed_fixture
from test_success_report import RUN, results
import test_visual_provenance as provenance_harness


class QuizTitleShadeTests(unittest.TestCase):
    def test_model_selects_only_approved_intents_and_receives_photo_specific_guidance(self):
        package=reviewed_fixture()
        proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette=p)
                  for c,p in zip(package['cards'],('gold-cream','blue-ice','forest-cream'))}}
        proposal['cards']['quiz']['heading_shade']='stronger'
        schema=Draft202012Validator(MODEL_CARD_SCHEMA)
        self.assertFalse(list(schema.iter_errors(proposal['cards']['quiz'])))
        for value in (50,.5,'opaque',{'alpha':90}):
            bad=copy.deepcopy(proposal['cards']['quiz']);bad['heading_shade']=value
            self.assertTrue(list(schema.iter_errors(bad)))
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            actual,status=review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertEqual(actual['cards']['quiz'],proposal['cards']['quiz'])
        prompt=child.call_args.args[0]
        for text in ('Choose heading_shade=gentle or stronger for EACH photographic quiz',
                     'even if the bare text already passes contrast','Neither choice is mandatory',
                     'Lesson/word and paper/treatment-B headings MUST use heading_shade=gentle'):
            self.assertIn(text,prompt)
        child.assert_called_once()

    def test_stronger_quiz_renders_real_shade_for_both_backings_and_edges(self):
        quiz=reviewed_fixture()['cards'][0];quiz.pop('quiz_format',None)
        source=copy.deepcopy(quiz)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for tone,background,backing in (('paper_dark','#202020','#000000'),('ink_light','#eeeeee','#ffffff')):
                photo=root/'photo.png';Image.new('RGB',(1080,1350),background).save(photo)
                for fade in ('standard','defined'):
                    plan=default_plan(quiz);plan.update(confidence='high',heading_tone=tone,heading_fade=fade)
                    weak=render_hybrid(quiz,'gold-cream',photo,root/'gentle.jpg',plan)
                    self.assertEqual(weak['heading_shading'],0)
                    plan['heading_shade']='stronger';before=copy.deepcopy(plan)
                    strong=render_hybrid(quiz,'gold-cream',photo,root/'stronger.jpg',plan)
                    self.assertEqual(strong['heading_shading'],QUIZ_TITLE_MIN_SHADE)
                    self.assertEqual(strong['heading_backing'],backing)
                    self.assertGreaterEqual(strong['heading_contrast'],3)
                    self.assertGreaterEqual(strong['body_contrast'],4.5)
                    self.assertEqual(strong['composition'],before);self.assertEqual(plan,before)
                    with Image.open(root/'gentle.jpg') as a,Image.open(root/'stronger.jpg') as b:
                        self.assertNotEqual(a.crop((0,145,1080,310)).tobytes(),b.crop((0,145,1080,310)).tobytes())
                        self.assertEqual(a.crop((0,0,1080,120)).tobytes(),b.crop((0,0,1080,120)).tobytes())
        self.assertEqual(quiz,source)

    def test_legacy_missing_intent_remains_gentle_and_stronger_escalates_for_contrast(self):
        quiz=reviewed_fixture()['cards'][0];quiz.pop('quiz_format',None)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#eeeeee').save(photo)
            plan=default_plan(quiz);plan['heading_tone']='paper_dark'
            current=render_hybrid(quiz,'gold-cream',photo,root/'current.jpg',plan)
            legacy=copy.deepcopy(plan);del legacy['heading_shade']
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(legacy)))
            self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(legacy)))
            old=render_hybrid(quiz,'gold-cream',photo,root/'old.jpg',legacy)
            self.assertEqual((root/'old.jpg').read_bytes(),(root/'current.jpg').read_bytes())
            self.assertEqual(old['heading_shading'],current['heading_shading'])
            plan['heading_shade']='stronger'
            strong=render_hybrid(quiz,'gold-cream',photo,root/'strong.jpg',plan)
            self.assertGreater(strong['heading_shading'],QUIZ_TITLE_MIN_SHADE)
            self.assertGreaterEqual(strong['heading_contrast'],3)

    def test_nonquiz_and_paper_cannot_request_stronger_and_heading_lock_includes_intent(self):
        cards=reviewed_fixture()['cards']
        candidates=[(c,default_plan(c)) for c in cards[1:]]
        candidates.append((cards[2],editorial_plan(cards[2])))
        visual=copy.deepcopy(cards[0]);visual['quiz_format']='visual_identification'
        candidates.append((visual,default_plan(visual)))
        for card,plan in candidates:
            plan['heading_shade']='stronger'
            with self.assertRaisesRegex(ValueError,'Stronger title shading requires a photographic quiz'):
                measured_plan(card,plan)
        plan=default_plan(cards[0]);changed=copy.deepcopy(plan);changed['heading_shade']='stronger'
        self.assertFalse(unchanged(plan,changed,['heading']))
        self.assertTrue(unchanged(plan,changed,['category']))

    def test_invalid_context_recovers_heading_only_without_changing_other_elements(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan.update(confidence='high',heading_shade='stronger')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.png';Image.new('RGB',(1080,1350),'#728192').save(photo)
            def draw(candidate):return render_hybrid(card,'gold-cream',photo,root/'card.jpg',candidate)
            metrics,recovery=recover_elements(card,plan,photo,draw,required=('heading',))
        self.assertEqual(recovery['fallback'],['heading'])
        self.assertEqual(metrics['composition']['heading_shade'],'gentle')
        self.assertEqual(metrics['composition']['blocks'],plan['blocks'])
        self.assertEqual(metrics['composition']['category_style'],plan['category_style'])

    def test_pipeline_reports_and_history_preserve_choice_without_inventing_legacy_choice(self):
        harness=provenance_harness.VisualProvenanceTests();harness.setUp();proposal=harness.proposal(harness.package)
        proposal['cards']['quiz']['heading_shade']='stronger'
        placement,metrics=harness.render(harness.package,proposal)
        self.assertEqual(placement['cards']['quiz']['status'],'accepted')
        self.assertEqual(metrics['quiz']['composition']['heading_shade'],'stronger')
        self.assertGreaterEqual(metrics['quiz']['heading_shading'],QUIZ_TITLE_MIN_SHADE)
        self.assertEqual(accepted_choices(placement)['quiz']['heading_shade'],'stronger')
        text,markup=render_report(with_rendering(report_data(harness.package,results(),RUN),placement))
        for document in (text,markup):self.assertIn('Title shade intent: stronger',document)
        for card in placement['cards'].values():card['composition'].pop('heading_shade',None)
        self.assertNotIn('heading_shade',accepted_choices(placement)['quiz'])
        text,_=render_report(with_rendering(report_data(harness.package,results(),RUN),placement))
        self.assertNotIn('Title shade intent:',text)
