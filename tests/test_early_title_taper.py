"""Earlier title falloff preserves glyph protection, reach and example presets."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian.hybrid import (protect_text,serif,render_hybrid,default_plan,
    TITLE_FADE_FEATHER,TITLE_FADE_PADDING,TITLE_FADE_POWER)
from easybosnian.render import measure
from easybosnian.visual_placement import review_compositions
from test_project import reviewed_fixture
import test_visual_provenance as harness


class EarlyTitleTaperTests(unittest.TestCase):
    def test_both_sides_start_fading_earlier_without_losing_glyph_contrast_or_reach(self):
        face=serif(44);top=174
        for rows in (['Čuvamo svoju riječ.'],['Čuvamo svoju riječ.', 'I poštujemo prijatelje.']):
            bottom=top+measure(rows,face)[0]
            for foreground,backing,background in (('#ffffff',(0,0,0),'#aaaaaa'),('#111111',(255,255,255),'#222222')):
                with self.subTest(rows=rows,foreground=foreground):
                    original=Image.new('RGBA',(1080,1350),background);old=original.copy();new=original.copy();results=[]
                    for image,early in ((old,False),(new,True)):
                        results.append(protect_text(image,(64,top),rows,face,[foreground],3,(0,0,1080,1350),
                            backings=[(foreground,backing)],fade_style='standard',feather=TITLE_FADE_FEATHER,
                            top_padding=TITLE_FADE_PADDING,bottom_padding=TITLE_FADE_PADDING,
                            feather_power=TITLE_FADE_POWER,minimum_shade=90,early_taper=early))
                    self.assertEqual(results[0],results[1]);self.assertGreaterEqual(results[1][1],3)
                    self.assertEqual(old.crop((0,top,1080,bottom+1)).tobytes(),new.crop((0,top,1080,bottom+1)).tobytes())
                    base=original.getpixel((1000,top));delta=lambda im,y:max(abs(a-b) for a,b in zip(im.getpixel((1000,y)),base))
                    for offset in (12,24,48):
                        self.assertLess(delta(new,top-offset),delta(old,top-offset))
                        self.assertEqual(new.getpixel((1000,top-offset)),new.getpixel((1000,bottom+offset)))
                    self.assertEqual(new.getpixel((1000,top-124)),base);self.assertEqual(new.getpixel((1000,bottom+124)),base)
                    self.assertGreater(delta(new,top-70),0)
                    for y in (top-40,top,top+20,bottom+40):
                        self.assertEqual(len({new.getpixel((x,y)) for x in range(1080)}),1)

    def test_actual_renderer_enables_earlier_taper_only_for_the_title(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['heading']='Čuvamo svoju riječ.'
        plan=default_plan(card);plan.update(heading_tone='paper_dark',heading_shade='emphasis',heading_opacity=90);calls=[]
        def observe(image,*args,**kwargs):
            calls.append((kwargs.get('feather'),kwargs.get('early_taper',False)))
            return protect_text(image,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#aaaaaa').save(photo)
            with patch('easybosnian.hybrid.protect_text',side_effect=observe):result=render_hybrid(card,'forest-cream',photo,root/'card.jpg',plan)
        self.assertEqual([c for c in calls if c[1]],[(TITLE_FADE_FEATHER,True)])
        self.assertGreaterEqual(result['heading_contrast'],3);self.assertGreaterEqual(result['example_contrast'],4.5)
        self.assertEqual(result['composition'],plan)

    def test_live_guidance_controls_jarring_blends_without_a_blanket_strength_or_edge_bias(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
            review_compositions(h.package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']})
        prompt=model.call_args.args[0]
        for rule in ('taper starts IMMEDIATELY outside the measured lettering','vivid backing looks jarring','FIRST try a softer approved shade_strength','not a global preference for low opacity or dull colours','Compare all three equally'):
            self.assertIn(rule,prompt)
