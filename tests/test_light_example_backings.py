"""Approved light-surface candidates reach both reviewers without automatic recolouring."""
import colorsys,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.palettes import active,LIGHT_SURFACE_BACKING_GUIDANCE
from easybosnian.hybrid import default_plan,render_hybrid,valid_example_backing
from easybosnian.render import contrast
from easybosnian.rendered_harmony import inspect,improve
from easybosnian.visual_placement import review_compositions
from test_project import reviewed_fixture
import test_visual_provenance as harness

ACCEPT={'verdict':'accept','reason':'harmonious','backing_colour':None,'shade_strength':None}

class LightExampleBackingTests(unittest.TestCase):
    def test_all_active_candidates_are_dark_rich_and_related_to_the_light_surface(self):
        palettes=active();self.assertEqual(len(palettes),36)
        self.assertNotIn('light_example_backing',read_json(ROOT/'data/design-palettes.json')['graphite-chalk'])
        for name,p in palettes.items():
            with self.subTest(palette=name):
                colour=p['light_example_backing'];self.assertTrue(valid_example_backing(colour))
                def hsv(c):return colorsys.rgb_to_hsv(*(int(c[i:i+2],16)/255 for i in (1,3,5)))
                h,s,v=hsv(colour);surface_h=hsv(p['panel'])[0]
                self.assertGreater(s,.5);self.assertLess(min(abs(h-surface_h),1-abs(h-surface_h))*360,15)
                self.assertGreaterEqual(contrast('#ffffff',colour),4.5)
        # Reviewed richer warm refinements, plus the retained special ochre.
        for name,colour in {'terracotta-sand':'#963e0c','coral-cream':'#9b3622','copper-linen':'#93500b',
            'aubergine-apricot':'#985015','burgundy-oat':'#8e4322','espresso-almond':'#855018',
            'scarlet-vanilla':'#8b5a08','paprika-aqua':'#a2490d','ochre-parchment':'#745700'}.items():
            self.assertEqual(palettes[name]['light_example_backing'],colour)

    def test_initial_review_and_final_inspector_receive_same_guidance_and_actual_candidates(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            result,status=review_compositions(h.package,{k:{'sheet':k+'.jpg'} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');prompt=child.call_args.args[0]
        self.assertIn(LIGHT_SURFACE_BACKING_GUIDANCE,prompt)
        for p in active().values():self.assertIn(p['light_example_backing'],prompt)
        self.assertNotIn(json.dumps(read_json(ROOT/'data/example-backings.json')),prompt)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);card=reviewed_fixture()['cards'][2];photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#999999').save(photo)
            plan=dict(default_plan(card),palette='forest-cream');plan['blocks'][-1].update(photo_tone='paper_dark',backing_colour='#145638')
            path=root/'card.jpg';metrics=render_hybrid(card,'forest-cream',photo,path,plan)
            with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(ACCEPT)) as child:
                self.assertEqual(inspect(card,path,metrics,can_revise=True),ACCEPT)
            prompt=child.call_args.args[0];self.assertIn(LIGHT_SURFACE_BACKING_GUIDANCE,prompt)
            self.assertIn(active()['forest-cream']['light_example_backing'],prompt)
            self.assertIn('not to reopen a fitting accepted pairing',prompt)
            self.assertEqual(child.call_args.kwargs['images'],[path])
            # A real defect may switch to the curated colour; only colour/strength change.
            responses=iter([{'verdict':'revise','reason':'poor_palette_harmony','backing_colour':active()['forest-cream']['light_example_backing'],'shade_strength':'medium'},ACCEPT])
            actual,detail=improve(card,path,metrics,lambda p:render_hybrid(card,'forest-cream',photo,path,p),review=lambda *a,**kw:next(responses))
            expected=copy.deepcopy(plan);expected['blocks'][-1].update(backing_colour=active()['forest-cream']['light_example_backing'],shade_strength='medium')
            self.assertEqual(actual['composition'],expected);self.assertEqual(detail['status'],'refined')
            self.assertGreaterEqual(actual['example_contrast'],4.5)

    def test_metadata_does_not_automatically_change_saved_light_or_dark_render_pixels(self):
        card=reviewed_fixture()['cards'][2];catalogue=read_json(ROOT/'data/design-palettes.json')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'assets').symlink_to(ROOT/'assets',target_is_directory=True)
            (root/'data').mkdir();bare={name:{k:v for k,v in p.items() if k!='light_example_backing'} for name,p in catalogue.items()}
            (root/'data/design-palettes.json').write_text(json.dumps(bare))
            photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#999999').save(photo)
            for name in ('gold-cream','terracotta-sand','ochre-parchment','mulberry-mint'):
                for tone in ('ink_paper','paper_ink'):
                    with self.subTest(palette=name,panel_tone=tone):
                        plan=dict(default_plan(card),palette=name);plan['blocks'][0]['panel_tone']=tone
                        plan['blocks'][-1].update(photo_tone='paper_ink',backing_colour=None)
                        a=root/'current.jpg';b=root/'old.jpg';now=render_hybrid(card,name,photo,a,plan)
                        with patch('easybosnian.hybrid.ROOT',root):old=render_hybrid(card,name,photo,b,plan)
                        self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual(now,old)
