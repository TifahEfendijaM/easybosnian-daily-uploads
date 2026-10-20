"""Original title strength and candidate-inclusive palette suitability limits."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from easybosnian.core import ROOT, read_json
from easybosnian.hybrid import (default_plan, render_hybrid, photo_colours,
                                protect_text, serif)
from easybosnian.visual_history import palette_policy, REPEATED_PALETTE
from easybosnian.visual_placement import review_compositions
from test_project import reviewed_fixture


class TitlePaletteLimitsTests(unittest.TestCase):
    def review(self, palettes, recent=(), exceptions=(), fallback='forest-cream'):
        package=reviewed_fixture();package['design_palette']=fallback
        plans={c['kind']:dict(default_plan(c),confidence='high',palette=p)
               for c,p in zip(package['cards'],palettes)}
        for kind in exceptions:plans[kind]['palette_exception']='no_other_suitable_palette'
        before=copy.deepcopy(plans)
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps({'cards':plans})) as child:
            result,status=review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in plans},recent)
        self.assertEqual(status,'reviewed');child.assert_called_once()
        self.assertNotIn('card_failures',result)
        # Palette policy must never discard accepted geometry/styles/copy intent.
        for kind,plan in result['cards'].items():
            self.assertEqual({k:v for k,v in plan.items() if k!='palette'},
                             {k:v for k,v in before[kind].items() if k!='palette'})
        return result

    def test_candidate_is_ninth_card_and_oldest_observation_really_ages_out(self):
        t=REPEATED_PALETTE;other='forest-cream'
        self.assertFalse(palette_policy([t]+[other]*7+[t])['alternatives_first'])
        self.assertTrue(palette_policy([other]*7+[t,t])['alternatives_first'])
        self.assertFalse(palette_policy([t]+[other]*8)['alternatives_first'])
        policy=palette_policy([other]*7+[t,t])
        self.assertEqual((policy['known_images'],policy['recent_uses'],policy['max_uses']),(8,2,2))
        # The same-batch rule still applies with missing older context.
        self.assertTrue(palette_policy([], [t])['alternatives_first'])

    def test_second_same_batch_use_needs_exception_even_with_no_recent_history(self):
        t=REPEATED_PALETTE
        result=self.review([t,'forest-cream',t])
        self.assertEqual(result['palette_decisions']['quiz']['source'],'chatgpt')
        self.assertEqual(result['palette_decisions']['word'],
                         {'source':'fallback','reason':'Repeated palette lacks required suitability exception'})
        allowed=self.review([t,'forest-cream',t],exceptions=('word',))
        self.assertEqual(allowed['palette_decisions']['word']['source'],'chatgpt')

    def test_third_consecutive_nine_use_needs_exception_across_batch_boundary(self):
        t=REPEATED_PALETTE
        recent=[{'palette_observations':['forest-cream']*7+[t,t]}]
        result=self.review([t,'forest-cream','blue-ice'],recent)
        self.assertEqual(result['palette_decisions']['quiz']['source'],'fallback')
        allowed=self.review([t,'forest-cream','blue-ice'],recent,exceptions=('quiz',))
        self.assertEqual(allowed['palette_decisions']['quiz']['source'],'chatgpt')
        # Keeping a ninth-old observation would incorrectly require an exception.
        aged=[{'palette_observations':[t]+['forest-cream']*7+[t]}]
        self.assertEqual(self.review([t,'forest-cream','blue-ice'],aged)
                         ['palette_decisions']['quiz']['source'],'chatgpt')

    def test_fallback_palette_counts_for_later_cards_but_is_not_recoloured(self):
        t=REPEATED_PALETTE
        result=self.review(['unsupported',t,'blue-ice'],fallback=t)
        self.assertEqual(result['palette_decisions']['quiz']['source'],'fallback')
        self.assertEqual(result['cards']['quiz']['palette'],t)
        self.assertEqual(result['palette_decisions']['lesson']['reason'],
                         'Repeated palette lacks required suitability exception')
        self.assertEqual(result['cards']['lesson']['palette'],t)

    def test_titles_match_strengths_measured_from_pre_expansion_renderer(self):
        # Golden values independently obtained from cb8c171's protect_text,
        # before the October 19/20 expansion; new palette-role pairs also work.
        palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        face=serif(74);xy=(64,155);rows=['Čuvaj svoju riječ.']
        cases=[('paper_dark','#979797',90),('ink_light','#555555',90),
               ('paper_ink','#b0b0b0',90),('ink_paper','#303030',90),
               ('paper_dark','#ffffff',130),('ink_light','#000000',90),
               ('paper_ink','#ffffff',130),('ink_paper','#000000',130),
               ('accent_dark','#ffffff',170),('ink_accent','#000000',130)]
        for tone,background,expected_alpha in cases:
            with self.subTest(tone=tone,background=background):
                image=Image.new('RGBA',(1080,1350),background)
                colours,backings=photo_colours(palette,tone)
                colour,score,alpha=protect_text(image,xy,rows,face,colours,3,backings=backings)
                self.assertEqual(alpha,expected_alpha)
                self.assertEqual(colour,colours[0]);self.assertGreaterEqual(score,3)
        readable=Image.new('RGBA',(1080,1350),'#000000');before=readable.tobytes()
        self.assertEqual(protect_text(readable,xy,rows,face,['#ffffff'],3)[2],0)
        self.assertEqual(readable.tobytes(),before)

    def test_real_title_restores_original_strength_with_colour_choices_and_copy_preserved(self):
        card=reviewed_fixture()['cards'][2];source=copy.deepcopy(card)
        palette=read_json(ROOT/'data/design-palettes.json')['gold-cream']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg'
            Image.new('RGB',(1080,1350),'#ffffff').save(photo)
            for tone,expected_alpha in [('paper_dark',130),('paper_ink',130),('accent_dark',170)]:
                plan=dict(default_plan(card),confidence='high',heading_tone=tone)
                plan['blocks'][-1]['photo_tone']='paper_dark'
                result=render_hybrid(card,'gold-cream',photo,root/(tone+'.jpg'),plan)
                self.assertEqual(result['heading_shading'],expected_alpha)
                self.assertEqual(result['heading_tone'],tone)
                self.assertEqual(result['heading_colour'],photo_colours(palette,tone)[0][0])
                self.assertGreaterEqual(result['heading_contrast'],3)
                self.assertEqual(result['example_colour'],'#ffffff')
                self.assertEqual(result['example_shading'],170)
                self.assertGreaterEqual(result['example_contrast'],4.5)
                self.assertEqual(result['composition'],plan);self.assertEqual(card,source)


if __name__=='__main__':unittest.main()
