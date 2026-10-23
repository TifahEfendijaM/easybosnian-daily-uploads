"""Opacity changes actual surfaces, never source copy, typography or safety."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from PIL import Image

from easybosnian.core import ROOT, read_json
from easybosnian.designs import PANEL_OPACITIES, PANEL_STYLES, panel_alpha, valid_panel_opacity
from easybosnian.hybrid import block_spec, default_plan, draw_panel, editorial_plan, measured_plan, render_hybrid
from easybosnian.success_report import decision_lines
from easybosnian.visual_diagnostics import rejection_diagnostic
from easybosnian.visual_history import accepted_choices
from easybosnian.visual_placement import CARD_SCHEMA, MODEL_CARD_SCHEMA, review_compositions
from test_project import reviewed_fixture
import test_visual_provenance as provenance_harness


class PanelOpacityTests(unittest.TestCase):
    def test_percentage_range_is_panel_only_and_old_presets_remain_readable(self):
        self.assertEqual(PANEL_OPACITIES['translucent'],191)
        self.assertEqual(round(PANEL_OPACITIES['translucent']/255*100),75)
        card=reviewed_fixture()['cards'][2]
        for preset in [70,72.5,75,99.9,100,*PANEL_OPACITIES]:
            plan=default_plan(card);plan['blocks'][0]['panel_opacity']=preset
            self.assertEqual(measured_plan(card,plan)[0]['panel_opacity'],preset)
        for value in (49.99,100.01,0.8,True,None,'50%','invisible'):
            plan=default_plan(card);plan['blocks'][0]['panel_opacity']=value
            self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)),value)
            self.assertFalse(valid_panel_opacity(value),value)
            with self.assertRaises(ValueError):panel_alpha(value)
        for value in (float('nan'),float('inf'),float('-inf')):
            self.assertFalse(valid_panel_opacity(value))
            with self.assertRaises(ValueError):panel_alpha(value)
        for value in (50,70,84.99,85,87.5,100):
            plan=dict(default_plan(card),palette='gold-cream');plan['blocks'][0]['panel_opacity']=value
            self.assertEqual(bool(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan))),value!=100)
            self.assertEqual(valid_panel_opacity(value,legacy=False),value>=85)
            self.assertFalse(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
        for value in PANEL_OPACITIES:
            plan=dict(default_plan(card),palette='gold-cream');plan['blocks'][0]['panel_opacity']=value
            self.assertTrue(list(Draft202012Validator(MODEL_CARD_SCHEMA).iter_errors(plan)))
        for role,field,value in [('body','panel_opacity',.8),('body','panel_opacity','invisible'),
                                 ('body','opacity',.8),('example','panel_opacity','soft')]:
            plan=default_plan(card)
            next(b for b in plan['blocks'] if b['role']==role)[field]=value
            self.assertTrue(list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)))
        for value in (70,99.9,'soft'):
            plan=editorial_plan(card);plan['blocks'][0]['panel_opacity']=value
            with self.assertRaisesRegex(ValueError,'Unboxed editorial body'):measured_plan(card,plan)
        self.assertEqual([panel_alpha(v) for v in (70,72.5,75,100)],[178,185,191,255])

    def test_every_panel_style_composites_surface_but_keeps_rules_and_badges_opaque(self):
        package=reviewed_fixture();palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        for style in PANEL_STYLES:
            card=package['cards'][0 if style in ('pill','folded_corner') else 2];role='A' if style in ('pill','folded_corner') else 'body'
            for preset,alpha in [*PANEL_OPACITIES.items(),(70,178),(73.5,187),(87,222),(100,255)]:
                with self.subTest(style=style,preset=preset):
                    spec=block_spec(card,role,952,style,font_size=36)
                    block={**spec,'role':role,'x':64,'y':750,'width':952,'panel_opacity':preset,
                           'bounds':[64,750,1016,750+spec['height']]}
                    image=Image.new('RGBA',(1080,1350),'#808080')
                    draw_panel(image,block,palette)
                    surface=palette['ink'] if style=='overlay_dark' else palette['panel']
                    expected=Image.alpha_composite(Image.new('RGBA',(1,1),'#808080'),
                        Image.new('RGBA',(1,1),(*tuple(int(surface[i:i+2],16) for i in (1,3,5)),alpha)))
                    self.assertEqual(image.getpixel((540,round(750+spec['height']/2))),expected.getpixel((0,0)))
                    if style=='side_rule':self.assertEqual(image.getpixel((65,780))[:3],(255,207,53))
                    if role=='A':
                        # Circle's centre-left is inside the badge and outside its letter.
                        self.assertEqual(image.getpixel((90,round(750+spec['height']/2)))[:3],(255,207,53))

    def test_legacy_omissions_keep_previous_surfaces_and_geometry(self):
        card=reviewed_fixture()['cards'][2]
        for style in PANEL_STYLES:
            if style in ('pill','folded_corner'):continue
            block={**block_spec(card,'body',952,style,font_size=36),'role':'body',
                   'x':64,'y':750,'width':952}
            block['bounds']=[64,750,1016,750+block['height']]
            palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
            legacy=Image.new('RGBA',(1080,1350),'#808080');draw_panel(legacy,block,palette)
            if style=='overlay_light':
                expected=Image.alpha_composite(Image.new('RGBA',(1,1),'#808080'),Image.new('RGBA',(1,1),(255,249,233,235)))
                self.assertEqual(legacy.getpixel((540,round(750+block['height']/2))),expected.getpixel((0,0)))
            else:
                explicit=Image.new('RGBA',(1080,1350),'#808080')
                draw_panel(explicit,{**block,'panel_opacity':'solid'},palette)
                self.assertEqual(legacy.tobytes(),explicit.tobytes())

    def test_rendering_preserves_copy_geometry_and_reads_final_photo_pixels(self):
        card=reviewed_fixture()['cards'][2];before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#808080').save(photo)
            outputs=[];bounds=[]
            for preset in (70,72.5,87,100):
                plan=default_plan(card);plan['blocks'][0]['panel_opacity']=preset
                metrics=render_hybrid(card,'gold-cream',photo,root/f'{preset}.jpg',plan)
                self.assertEqual(metrics['composition'],plan)
                self.assertGreaterEqual(metrics['body_contrast'],4.5)
                self.assertEqual(measured_plan(card,plan)[0]['rows'].reconstructed(),card['body'])
                outputs.append((root/f'{preset}.jpg').read_bytes());bounds.append(metrics['panel_bounds'])
            self.assertEqual(len(set(outputs)),4)
            self.assertEqual(bounds,[bounds[0]]*4)
            self.assertEqual(card,before)
            plan=default_plan(card);plan['blocks'][0]['panel_opacity']=70
            Image.new('RGB',(1080,1350),'#000000').save(photo)
            # A synthetic palette with valid opaque contrast exposes unreadable
            # compositing; model-supplied custom colours remain forbidden above.
            palette={'gold-cream':{'ink':'#666666','panel':'#ffffff','accent':'#ffffff'}}
            with patch('easybosnian.hybrid.json.loads',return_value=palette):
                with self.assertRaisesRegex(ValueError,'Actual panel text contrast fails') as failed:
                    render_hybrid(card,'gold-cream',photo,root/'bad.jpg',plan)
            self.assertFalse((root/'bad.jpg').exists())
            self.assertEqual(plan['blocks'][0]['panel_opacity'],70)
            self.assertEqual(rejection_diagnostic(failed.exception,plan)['reason'],str(failed.exception))

    def test_prompt_and_safe_report_include_opacity_and_recent_metadata_stays_whitelisted(self):
        package=reviewed_fixture()
        proposal={'cards':{c['kind']:dict(default_plan(c),palette='gold-cream') for c in package['cards']}}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            result,status=review_compositions(package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertNotIn('card_failures',result)
        self.assertIn('panels are ALWAYS fully opaque: panel_opacity=100 percent',child.call_args.args[0])
        self.assertIn('You do NOT choose the opacity',child.call_args.args[0])
        self.assertIn('assigned_panel_opacity',child.call_args.args[0])
        self.assertNotIn('Prefer the lower suitable opacity',child.call_args.args[0])
        self.assertIn('Never request transparency',child.call_args.args[0])
        plan=proposal['cards']['word'];plan['blocks'][0]['panel_opacity']=87.5
        rendering={'palette':'gold-cream','design':'hybrid','block_styles':{'body':'rounded','example':'italic_photo_fade'},
                   'answer_badges':{},'composition':plan,'status':'accepted'}
        self.assertIn('Explanation surface opacity: 87.5%.',decision_lines(rendering))
        recent=accepted_choices({'cards':{'word':rendering}})
        self.assertNotIn('panel_opacities',recent['word'])
        plan['blocks'][0]['panel_opacity']=60
        self.assertIn('Explanation surface opacity: 60%.',decision_lines(rendering))
        self.assertNotIn('panel_opacities',accepted_choices({'cards':{'word':rendering}})['word'])
        plan['blocks'][0]['panel_opacity']='secret model prose'
        self.assertNotIn('panel_opacities',accepted_choices({'cards':{'word':rendering}})['word'])

    def test_opaque_surfaces_and_colour_choices_survive_review_render_and_report(self):
        harness=provenance_harness.VisualProvenanceTests();harness.setUp()
        proposal=harness.proposal(harness.package)
        proposal['cards']['word']['blocks'][0]['panel_opacity']=100
        proposal['cards']['word']['heading_tone']='paper_ink'
        proposal['cards']['word']['blocks'][-1]['photo_tone']='paper_ink'
        placement,metrics=harness.render(harness.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['status'],'accepted')
        from easybosnian.visual_policy import apply_policy
        self.assertEqual(metrics['word']['composition'],apply_policy(proposal['cards']['word'],panel_opacity=100))
        self.assertEqual(word['provenance']['layout']['source'],'chatgpt')
        self.assertGreaterEqual(metrics['word']['body_contrast'],4.5)
        self.assertIn('Explanation surface opacity: 100%.',decision_lines(word))
        self.assertNotIn('panel_opacities',accepted_choices(placement)['word'])

    def test_out_of_range_opacity_cannot_be_repaired_or_invalidate_sibling_layouts(self):
        harness=provenance_harness.VisualProvenanceTests();harness.setUp()
        proposal=harness.proposal(harness.package)
        proposal['cards']['word']['blocks'][0].update(panel_opacity=69.9,x=30)
        placement,metrics=harness.render(harness.package,proposal)
        self.assertEqual(placement['cards']['word']['provenance']['layout']['source'],'mixed')
        self.assertEqual(placement['cards']['word']['provenance']['palette']['source'],'chatgpt')
        self.assertEqual(placement['cards']['word']['review_failure'],'review violated the declarative schema')
        self.assertEqual(metrics['word']['composition']['blocks'][0]['panel_opacity'],100)
        self.assertTrue(all(placement['cards'][k]['status']=='accepted' for k in ('quiz','lesson')))
