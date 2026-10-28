"""Opaque text panels and photo-assessed PRIMJER shade choices."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from easybosnian.hybrid import default_plan,editorial_plan,render_hybrid
from easybosnian.visual_policy import panel_opacities,apply_policy,policy_metadata,safe_policy
from easybosnian.success_report import report_data,with_rendering,render_report
from easybosnian.visual_history import accepted_choices
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as provenance_harness


class SharedOpacityRandomShadeTests(unittest.TestCase):
    def test_example_selection_never_draws_and_all_panels_are_opaque(self):
        cards=reviewed_fixture()['cards'];cards[1]['example']='Ovo je primjer.'
        with patch('secrets.choice',side_effect=AssertionError('no example draw allowed')) as draw:
            for preset in ('standard','sharp'):
                plan=default_plan(cards[2]);plan['blocks'][-1]['fade_style']=preset
                self.assertEqual(apply_policy(plan,panel_opacity=100),plan)
        with patch('secrets.randbelow',side_effect=AssertionError('no opacity draw allowed')) as opacity_draw:
            opacities=panel_opacities(cards)
        self.assertEqual(opacities,{'quiz':100,'lesson':100,'word':100})
        opacity_draw.assert_not_called()
        draw.assert_not_called()

    def test_two_three_four_options_share_opaque_surfaces_and_render_with_exact_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#728192').save(photo)
            for count in (2,3,4):
                card=copy.deepcopy(reviewed_fixture()['cards'][0])
                card['options']=[{'label':label,'text':text} for label,text in
                                  zip('ABCD',('Jabuka','Kruška','Šljiva','Dunja'))][:count]
                source=copy.deepcopy(card);plan=default_plan(card)
                for block in plan['blocks']:block['panel_opacity']=100
                original=copy.deepcopy(plan);applied=apply_policy(plan,panel_opacity=100)
                expected=copy.deepcopy(plan)
                for block in expected['blocks']:block['panel_opacity']=100
                self.assertEqual(applied,expected);self.assertEqual(plan,original)
                metrics=render_hybrid(card,'gold-cream',photo,root/f'quiz-{count}.jpg',applied)
                self.assertEqual(metrics['composition'],expected)
                self.assertGreaterEqual(metrics['body_contrast'],4.5)
                self.assertEqual(card,source)
                self.assertEqual(policy_metadata(applied,panel_opacity=100)['panel_opacity'],100)
            # Legacy source values cannot restore transparent fresh panels.
            word=default_plan(reviewed_fixture()['cards'][2]);word['blocks'][0]['panel_opacity']=91
            with self.assertRaisesRegex(ValueError,'opacity'):apply_policy(word,panel_opacity=100)
            with self.assertRaisesRegex(ValueError,'opacity'):apply_policy(word)
            with self.assertRaisesRegex(ValueError,'opacity'):apply_policy(default_plan(card),panel_opacity=91)

    def test_policy_preserves_selected_example_preset_and_changes_only_opacity(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan.update(heading_tone='accent_dark',heading_fade='standard')
        plan['blocks'][0].update(style='soft_corner',panel_opacity=100)
        plan['blocks'][-1]['photo_tone']='paper_ink'
        original=copy.deepcopy(plan)
        expected=copy.deepcopy(plan)
        expected['blocks'][0]['panel_opacity']=100
        self.assertEqual(apply_policy(plan,panel_opacity=100),expected)
        self.assertEqual(plan,original)
        for style in ('italic_photo','italic_footer'):
            inactive=editorial_plan(card) if style=='italic_footer' else default_plan(card)
            inactive['blocks'][-1].update(style=style,fade_style='standard')
            applied=apply_policy(inactive,panel_opacity=100)
            self.assertEqual(applied,inactive)
            self.assertFalse(policy_metadata(applied,panel_opacity=100)['example_fade_applied'])
            accepted={'status':'accepted','palette':'gold-cream','design':applied['design'],
                'block_styles':{b['role']:b['style'] for b in applied['blocks']},
                'composition':applied,'render_policy':policy_metadata(applied,panel_opacity=100)}
            self.assertNotIn('example_fade',accepted_choices({'cards':{'word':accepted}})['word'])
        quiz=default_plan(reviewed_fixture()['cards'][0])
        quiz['blocks'][1]['panel_opacity']=69.9
        with self.assertRaisesRegex(ValueError,'opacity'):apply_policy(quiz,panel_opacity=100)
        plan['blocks'][-1]['fade_style']='custom'
        with self.assertRaisesRegex(ValueError,'Unsupported example shade'):apply_policy(plan,panel_opacity=100)

    def test_real_pipeline_keeps_panels_opaque_on_fallback_and_reports_the_fixed_policy(self):
        h=provenance_harness.VisualProvenanceTests();h.setUp()
        h.package['cards'][1]['example']='Ovo je primjer.'
        proposal=h.proposal(h.package)
        proposal['cards']['quiz']['blocks'][0]['panel_opacity']=100
        proposal['cards']['quiz']['blocks'][1]['panel_opacity']=100
        proposal['cards']['lesson']['blocks'][-1]['fade_style']='sharp'
        proposal['cards']['word']['blocks'][0]['max_lines']=1
        placement,metrics=h.render(h.package,proposal)
        quiz=placement['cards']['quiz'];lesson=placement['cards']['lesson'];word=placement['cards']['word']
        self.assertEqual(quiz['status'],'accepted')
        self.assertTrue(all(b['panel_opacity']==100 for b in quiz['composition']['blocks']))
        self.assertEqual(lesson['provenance']['layout']['source'],'chatgpt')
        self.assertEqual(word['provenance']['layout']['source'],'mixed')
        self.assertEqual(word['composition']['blocks'][0]['panel_opacity'],100)
        for result,preset in ((lesson,'sharp'),(word,'standard')):
            self.assertEqual(result['composition']['blocks'][-1]['fade_style'],preset)
            self.assertEqual(result['render_policy']['example_fade'],preset)
            self.assertTrue(result['render_policy']['example_fade_applied'])
        self.assertEqual(lesson['composition']['heading_fade'],'standard')
        self.assertEqual(accepted_choices(placement)['lesson']['example_fade'],'sharp')
        self.assertNotIn('panel_opacities',accepted_choices(placement)['quiz'])
        text,markup=render_report(with_rendering(report_data(h.package,results(),RUN),placement))
        for document in (text,markup):
            document=document.replace('\\.','.')
            self.assertIn('Panel opacity: fixed at 100%',document)
            self.assertNotIn('uniformly sampled',document)
            self.assertIn('ChatGPT',document)
            self.assertIn('Fallback elements only: body',document)
            self.assertNotIn('deterministic fallback preset',document)
            self.assertIn('sharp applied',document)
        bad=copy.deepcopy(placement);bad['cards']['quiz']['render_policy']['panel_opacity']=70
        with self.assertRaisesRegex(ValueError,'Shared opacity'):
            with_rendering(report_data(h.package,results(),RUN),bad)
        bad=copy.deepcopy(placement);bad['cards']['lesson']['render_policy']['example_fade']='defined'
        with self.assertRaisesRegex(ValueError,'safe rendering policy'):
            with_rendering(report_data(h.package,results(),RUN),bad)
        invalid=dict(lesson['render_policy'],extra='untrusted prose')
        with self.assertRaisesRegex(ValueError,'safe rendering policy'):safe_policy(invalid,lesson['composition'])

    def test_old_opacity_reports_remain_readable_without_changing_their_provenance(self):
        plan=default_plan(reviewed_fixture()['cards'][2]);plan['blocks'][0]['panel_opacity']=87.5
        policy={'version':5,'panel_opacity':87.5,'panel_opacity_applied':True,
                'example_fade':'standard','example_fade_applied':True}
        self.assertEqual(safe_policy(policy,plan),policy)
        plan['blocks'][0]['panel_opacity']=94.5
        variable=dict(policy,version=7,panel_opacity=94.5)
        self.assertEqual(safe_policy(variable,plan),variable)
        from easybosnian.visual_history import panel_theme
        self.assertEqual(panel_theme({'palette':'gold-cream','composition':plan}),'light')
        historic={'status':'accepted','palette':'gold-cream','design':plan['design'],
                  'block_styles':{b['role']:b['style'] for b in plan['blocks']},
                  'composition':plan,'render_policy':variable}
        self.assertEqual(accepted_choices({'cards':{'word':historic}})['word']['panel_opacities'],{'body':94.5})
        with self.assertRaisesRegex(ValueError,'Shared opacity'):safe_policy(dict(variable,version=8),plan)
        plan['blocks'][0]['panel_opacity']=87.5
        with self.assertRaisesRegex(ValueError,'Shared opacity'):safe_policy(dict(policy,version=6),plan)
