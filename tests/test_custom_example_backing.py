"""Exact PRIMJER RGB survives schema, rendering, reporting and recovery."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import default_plan,example_colours,measured_plan,render_hybrid,valid_example_backing
from easybosnian.visual_placement import CARD_SCHEMA,MODEL_CARD_SCHEMA,review_compositions
from easybosnian.visual_history import accepted_choices
from easybosnian.success_report import report_data,with_rendering,render_report
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as harness

class CustomExampleBackingTests(unittest.TestCase):
    def plan(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);plan=dict(default_plan(card),confidence='high',palette='forest-cream')
        plan['blocks'][-1].update(photo_tone='paper_dark',backing_colour='#145638',shade_strength='medium')
        return card,plan

    def test_strict_rgb_schema_and_context_reject_other_roles_styles_and_bright_values(self):
        card,plan=self.plan()
        self.assertFalse(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
        for value in ('#fff','#abcdef\n','#abcdef; secret','rgb(1,2,3)',{'private':'prose'},12):
            bad=copy.deepcopy(plan);bad['blocks'][-1]['backing_colour']=value
            self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(bad)))
        for value in ('#ffffff','#ffff00','#aaddcc'):
            bad=copy.deepcopy(plan);bad['blocks'][-1]['backing_colour']=value
            with self.assertRaisesRegex(ValueError,'must be a dark'):measured_plan(card,bad)
        for change in ({'style':'italic_photo','shade_strength':'soft'},{'photo_tone':'auto'}):
            bad=copy.deepcopy(plan);bad['blocks'][-1].update(change)
            with self.assertRaisesRegex(ValueError,'requires a full-photo fade'):measured_plan(card,bad)
        for target in ('heading','body'):
            bad=copy.deepcopy(plan)
            if target=='heading':bad['backing_colour']='#145638'
            else:bad['blocks'][0]['backing_colour']='#145638'
            self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(bad)))
        self.assertTrue(valid_example_backing('#145638'));self.assertFalse(valid_example_backing('#ffffff'))
        bad=copy.deepcopy(plan);bad['photo_window']={'y':400,'height':400,'fit':'contain'}
        with self.assertRaisesRegex(ValueError,'requires a full-photo fade'):measured_plan(card,bad)

    def test_exact_custom_pixels_preserve_copy_geometry_and_all_legacy_colour_pairs(self):
        card,plan=self.plan();before=copy.deepcopy(plan);source=copy.deepcopy(card)
        palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        colours,backings=example_colours(palette,'paper_dark','forest-cream','#145638')
        self.assertEqual(colours,['#ffffff']);self.assertEqual(backings,[('#ffffff',(20,86,56))])
        self.assertEqual(example_colours(palette,'paper_ink','forest-cream',None),example_colours(palette,'paper_ink','forest-cream'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#969696').save(photo)
            import easybosnian.hybrid as hybrid
            with patch.object(hybrid,'protect_text',wraps=hybrid.protect_text) as protection:
                actual=render_hybrid(card,'forest-cream',photo,root/'card.jpg',plan)
            call=next(c for c in protection.call_args_list if c.kwargs.get('backings')==backings)
            self.assertEqual(call.kwargs['backings'],backings)
            self.assertEqual(actual['composition'],before);self.assertEqual(card,source)
            self.assertGreaterEqual(actual['example_contrast'],4.5);self.assertGreaterEqual(actual['body_contrast'],4.5)
            self.assertGreaterEqual(actual['heading_contrast'],3)
            legacy=copy.deepcopy(plan);legacy['blocks'][-1]['backing_colour']=None
            render_hybrid(card,'forest-cream',photo,root/'legacy.jpg',legacy)
            self.assertNotEqual((root/'legacy.jpg').read_bytes(),(root/'card.jpg').read_bytes())
            bad=copy.deepcopy(plan);bad['blocks'][-1].update(photo_tone='ink_paper',backing_colour='#000000')
            with self.assertRaisesRegex(ValueError,'photographic text contrast fails'):render_hybrid(card,'forest-cream',photo,root/'bad.jpg',bad)

    def test_model_transport_prompt_summary_and_history_keep_exact_hex(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        proposal['cards']['word']['blocks'][-1].update(photo_tone='paper_dark',backing_colour='#145638')
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
            selected,status=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertNotIn('card_failures',selected)
        prompt=model.call_args.args[0]
        for phrase in ('FIRST seek a visibly DIFFERENT HUE','ONLY when NO different-hue candidate',
                       'Strong contrast with that surface is welcome','MILDLY PREFERRED',
                       'NEVER favour or lighten the text-card surface','backing_colour=null',
                       'applies to LIGHT text-card surfaces too',
                       'Do not automatically reuse a darker version of the light surface'):
            self.assertIn(phrase,prompt)
        placement,_=h.render(h.package,proposal)
        word=placement['cards']['word'];self.assertEqual(word['provenance']['layout']['source'],'chatgpt')
        self.assertEqual(word['composition']['blocks'][-1]['backing_colour'],'#145638')
        history=accepted_choices(placement);self.assertEqual(history['word']['example_backing_colour'],'#145638')
        report=with_rendering(report_data(h.package,results(),RUN),placement)
        for text in render_report(report):self.assertIn('ChatGPT-selected exact dark backing #145638',text.replace(chr(92),''))
        bad=copy.deepcopy(placement);bad['cards']['word']['composition']['blocks'][-1]['backing_colour']='#ffffff'
        with self.assertRaisesRegex(ValueError,'must be a dark'):with_rendering(report_data(h.package,results(),RUN),bad)

    def test_invalid_darkness_recovery_keeps_valid_geometry_siblings_and_preset(self):
        from easybosnian.element_recovery import recover_elements
        card,plan=self.plan();plan['blocks'][-1]['backing_colour']='#ffffff'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#969696').save(photo)
            result=recover_elements(card,plan,photo,lambda p:render_hybrid(card,'forest-cream',photo,root/'card.jpg',p),
                 reason='Custom example backing must be a dark six-digit hex colour')
        self.assertIsNotNone(result);actual,detail=result
        expected=copy.deepcopy(plan);expected['blocks'][-1]['backing_colour']=None
        self.assertEqual(actual['composition'],expected);self.assertEqual(detail['fallback'],['example'])
        self.assertIn('body',detail['preserved']);self.assertIn('heading',detail['preserved'])
