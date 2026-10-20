"""Real catalogue pixels, approved colour roles, rolling palette rules and faithful placement."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from jsonschema import Draft202012Validator
from easybosnian.core import ROOT, read_json
from easybosnian.designs import BODY_STYLES, ANSWER_STYLES, PANEL_TONES
from easybosnian.hybrid import default_plan, block_spec, draw_panel, measured_plan, render_hybrid, category_label
from easybosnian.visual_adjustment import nearest_valid_plan, adjustable_proposal, safe_adjustment
from easybosnian.visual_history import palette_window, palette_policy, accepted_choices
from easybosnian.visual_placement import CARD_SCHEMA, review_compositions
from easybosnian.visual_diagnostics import rendering_outcome
from easybosnian.success_report import with_rendering, report_data, render_report
from test_project import reviewed_fixture
from test_success_report import RUN, results
import test_visual_provenance as harness_module


class CatalogueExpansionTests(unittest.TestCase):
    def test_new_shapes_are_distinct_and_role_restrictions_remain(self):
        package=reviewed_fixture();palette=read_json(ROOT/'data/design-palettes.json')['forest-cream']
        outputs=[]
        for style,role in [('rounded','body'),('soft_corner','body'),('folded_corner','A')]:
            card=package['cards'][0 if role=='A' else 2]
            spec=block_spec(card,role,952,style,font_size=36)
            block={**spec,'role':role,'x':64,'y':750,'width':952,'bounds':[64,750,1016,750+spec['height']]}
            image=Image.new('RGBA',(1080,1350),'#808080');draw_panel(image,block,palette)
            outputs.append(image.tobytes())
            if style=='soft_corner':
                self.assertEqual(image.getpixel((65,751))[:3],(128,128,128))
                self.assertNotEqual(image.getpixel((65,round(block['bounds'][3]-1)))[:3],(128,128,128))
            if style=='folded_corner':self.assertEqual(image.getpixel((1015,751))[:3],(128,128,128))
        self.assertEqual(len(set(outputs)),3)
        self.assertIn('soft_corner',BODY_STYLES);self.assertIn('folded_corner',ANSWER_STYLES)
        self.assertNotIn('folded_corner',BODY_STYLES)
        with self.assertRaises(ValueError):block_spec(package['cards'][2],'body',952,'folded_corner')

    def test_colours_use_only_approved_roles_and_remain_independent_of_style_and_alpha(self):
        card=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#78634a').save(photo)
            outputs=[]
            for tone in PANEL_TONES:
                plan=default_plan(card);plan['blocks'][0].update(style='soft_corner',panel_tone=tone,panel_opacity='soft')
                plan['category_tone']=tone
                metrics=render_hybrid(card,'forest-cream',photo,root/'card.jpg',plan)
                self.assertEqual(metrics['composition'],plan)
                self.assertGreaterEqual(metrics['body_contrast'],4.5)
                outputs.append((root/'card.jpg').read_bytes())
            self.assertGreaterEqual(len(set(outputs)),4)
            for field,value in [('panel_tone','#0055ff'),('panel_tone','custom'),('fade_style','css blur')]:
                plan=default_plan(card);plan['blocks'][0][field]=value
                self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))

    def test_historical_soft_fade_remains_readable_with_contrast_checks(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['body']='Ovo je kratko objašnjenje.'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#828282').save(photo)
            outputs=[]
            for fade in ('standard','soft'):
                plan=default_plan(card);plan['heading_tone']='paper_ink';plan['heading_fade']=fade
                plan['blocks'][-1].update(photo_tone='accent_dark',fade_style=fade)
                metrics=render_hybrid(card,'forest-cream',photo,root/f'{fade}.jpg',plan)
                self.assertGreaterEqual(metrics['heading_contrast'],3)
                self.assertGreaterEqual(metrics['example_contrast'],4.5)
                outputs.append((root/f'{fade}.jpg').read_bytes())
            self.assertNotEqual(*outputs)
            plan['blocks'][-1]['style']='italic_photo'
            with self.assertRaisesRegex(ValueError,'contrast'):render_hybrid(card,'forest-cream',photo,root/'bad.jpg',plan)

    def test_rolling_last_nine_counts_actual_palettes_including_fallback_observations(self):
        recent=[{'palette_observations':['blue-ice','terracotta-sand','forest-cream']},
                {'palette_observations':['terracotta-sand','rose-ivory','terracotta-sand']},
                {'palette_observations':['blue-ice','rose-ivory','blue-ice']},
                {'palette_observations':['terracotta-sand']*3}]
        window=palette_window(recent)
        self.assertEqual(window,['blue-ice','rose-ivory','blue-ice','terracotta-sand','rose-ivory',
                                 'terracotta-sand','blue-ice','terracotta-sand','forest-cream'])
        self.assertTrue(palette_policy(window)['alternatives_first'])
        self.assertFalse(palette_policy(window[-3:])['alternatives_first'])
        self.assertEqual(palette_window([{'palette_observations':['secret model prose',7,{}]}]),[])
        legacy={'cards':{'word':{'status':'accepted','palette':'terracotta-sand',
                               'design':'hybrid','block_styles':{'body':'rounded'}}}}
        self.assertNotIn('palette',accepted_choices(legacy)['word'])

    def test_repetition_exception_is_required_and_prior_batch_choices_update_window(self):
        package=reviewed_fixture();base={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='terracotta-sand') for c in package['cards']}}
        candidates={k:{'sheet':Path(k+'.jpg')} for k in base['cards']}
        recent=[{'palette_observations':['terracotta-sand']*2+['forest-cream']*7}]
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(base)) as child:
            result,status=review_compositions(package,candidates,recent)
        self.assertEqual(status,'reviewed')
        self.assertEqual(result['palette_decisions']['quiz']['source'],'chatgpt')
        # Quiz enters the rolling window; one old terracotta leaves, so it is
        # still not at three. Use a full window with its old uses at the end.
        recent=[{'palette_observations':['forest-cream']*7+['terracotta-sand']*2}]
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(base)):
            result,_=review_compositions(package,candidates,recent)
        self.assertEqual(result['palette_decisions']['quiz']['source'],'chatgpt')
        self.assertEqual(result['palette_decisions']['lesson']['source'],'fallback')
        allowed=copy.deepcopy(base)
        for plan in allowed['cards'].values():plan['palette_exception']='no_other_suitable_palette'
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(allowed)):
            result,_=review_compositions(package,candidates,recent)
        self.assertTrue(all(v['source']=='chatgpt' for v in result['palette_decisions'].values()))
        self.assertIn('THREE OR MORE',child.call_args.args[0])

    def test_nearby_geometry_translation_preserves_all_non_position_choices(self):
        card=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#78634a').save(photo)
            plan=dict(default_plan(card),confidence='high',palette='forest-cream')
            plan['blocks'][0].update(style='soft_corner',panel_tone='paper_ink',panel_opacity='soft',x=30,y=100)
            before=copy.deepcopy(plan)
            self.assertIsNotNone(adjustable_proposal(plan))
            adjusted,detail=nearest_valid_plan(card,plan,photo)
            measured_plan(card,adjusted)
            self.assertEqual(adjusted['blocks'][0]['x'],64)
            for old,new in zip(plan['blocks'],adjusted['blocks']):
                self.assertEqual({k:v for k,v in old.items() if k not in ('x','y')},
                                 {k:v for k,v in new.items() if k not in ('x','y')})
            self.assertEqual(plan,before);self.assertEqual(safe_adjustment(detail),detail)
            metrics=render_hybrid(card,'forest-cream',photo,root/'adjusted.jpg',adjusted)
            self.assertGreaterEqual(metrics['body_contrast'],4.5)
            self.assertIsNone(nearest_valid_plan(card,adjusted,photo))
            for bad in ({'reason':'secret','moves':detail['moves']},
                        {**detail,'extra':'private'}, {'reason':detail['reason'],'moves':[]}):
                with self.assertRaises(ValueError):safe_adjustment(bad)

    def test_overlapping_answers_are_translated_while_reading_order_and_photo_remain_protected(self):
        card=reviewed_fixture()['cards'][0]
        with tempfile.TemporaryDirectory() as tmp:
            photo=Path(tmp)/'photo.jpg';Image.new('RGB',(1024,1024),'#78634a').save(photo)
            plan=dict(default_plan(card),confidence='high')
            for block in plan['blocks']:block.update(x=64,y=450,width=440,style='folded_corner')
            adjusted,detail=nearest_valid_plan(card,plan,photo)
            blocks=measured_plan(card,adjusted)
            self.assertEqual([(b['y'],b['x']) for b in blocks],sorted((b['y'],b['x']) for b in blocks))
            self.assertLessEqual(len(detail['moves']),len(plan['blocks']))
            bad=copy.deepcopy(plan);bad['blocks'][0]['style']='draw arbitrary code'
            self.assertIsNone(nearest_valid_plan(card,bad,photo))
            bad=copy.deepcopy(plan);bad['blocks'][0]['font_size']=1
            self.assertIsNone(nearest_valid_plan(card,bad,photo))

    def test_pipeline_records_adjustment_as_model_design_and_report_shows_coordinates(self):
        harness=harness_module.VisualProvenanceTests();harness.setUp();package=harness.package;proposal=harness.proposal(package)
        proposal['cards']['word']['blocks'][0].update(y=100,x=30,style='soft_corner')
        placement,metrics=harness.render(package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['status'],'adjusted')
        self.assertEqual(word['block_styles']['body'],'soft_corner')
        self.assertEqual(word['provenance']['layout']['source'],'chatgpt')
        self.assertIn('adjustments',word['provenance']['layout']['reason'])
        self.assertIn('word',accepted_choices(placement))
        report=with_rendering(report_data(package,results(),RUN),placement)
        text,markup=render_report(report)
        self.assertIn('Pillow placement adjustment',text);self.assertIn('Pillow placement adjustment',markup)
        self.assertIn('Placement validation before adjustment',text)
        self.assertNotIn('**Layout fallback:**',text)
        bad=copy.deepcopy(placement)
        bad['cards']['word']['layout_adjustment']['moves'][0]['to']['y']+=1
        with self.assertRaisesRegex(ValueError,'differs from rendered composition'):
            with_rendering(report_data(package,results(),RUN),bad)
