"""Smooth boundary alpha, lower example padding and targeted measured clearance."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian.hybrid import (protect_text,serif,heading,default_plan,measured_plan,render_hybrid,
                                EXAMPLE_BLOCK_GAP,HEADING_TOP,CATEGORY_TOP,CATEGORY_HEIGHT)
from easybosnian.visual_adjustment import nearest_valid_plan
from easybosnian.render import measure
from test_project import reviewed_fixture


class SoftFadeSpacingTests(unittest.TestCase):
    def test_renderer_keeps_low_example_text_safe_but_allows_its_fade_to_finish(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card)
        plan['blocks'][-1].update(y=1094,font_size=36,max_lines=1)
        plan['blocks'][-1]['photo_tone']='paper_dark'
        card['example']='Pogledaj ovu riječ.'
        seen=[]
        def observe(image,*args,**kwargs):
            if kwargs.get('bottom_padding')==18:seen.append(args[5])
            return protect_text(image,*args,**kwargs)
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.jpg';Image.new('RGB',(1080,1350),'#b0b0b0').save(photo)
            with patch('easybosnian.hybrid.protect_text',side_effect=observe):
                metrics=render_hybrid(card,'forest-cream',photo,Path(temp)/'out.jpg',plan)
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][3],1286)
        self.assertLessEqual(metrics['example_bounds'][3],1170)
        self.assertGreaterEqual(metrics['example_contrast'],4.5)

    def test_title_eases_inside_category_boundary_instead_of_clipping_an_opaque_band(self):
        source=Image.new('RGBA',(1080,1350),'#b0b0b0');image=source.copy();face=serif(74)
        _,score,alpha=protect_text(image,(64,HEADING_TOP),['Čuvaj riječ.'],face,['#ffffff'],3,
            (0,127,1080,1350),feather=100)
        self.assertGreater(alpha,0);self.assertGreaterEqual(score,3)
        self.assertEqual(image.crop((0,0,1080,128)).tobytes(),source.crop((0,0,1080,128)).tobytes())
        values=[image.getpixel((540,y))[0] for y in range(127,HEADING_TOP)]
        self.assertLessEqual(max(abs(a-b) for a,b in zip(values,values[1:])),5)
        self.assertGreaterEqual(HEADING_TOP-(CATEGORY_TOP+CATEGORY_HEIGHT),48)

    def test_example_shading_leaves_room_below_text_and_tapers_to_zero_at_limit(self):
        image=Image.new('RGBA',(1080,1350),'#b0b0b0');face=serif(34,True);rows=['Ovo je jedna rečenica.']
        bottom=1060+measure(rows,face)[0]
        _,score,alpha=protect_text(image,(64,1060),rows,face,['#ffffff'],4.5,
                                  (0,400,1080,1170),feather=48,bottom_padding=18)
        self.assertGreaterEqual(score,4.5);self.assertGreater(alpha,0)
        self.assertEqual(image.getpixel((540,bottom+2)),image.getpixel((540,bottom+16)))
        self.assertNotEqual(image.getpixel((540,bottom+16)),(176,176,176,255))
        self.assertEqual(image.getpixel((540,1169)),(176,176,176,255))
        self.assertEqual(image.getpixel((540,1170)),(176,176,176,255))
        steps=[image.getpixel((540,y))[0] for y in range(bottom+18,1170)]
        self.assertLessEqual(max(abs(a-b) for a,b in zip(steps,steps[1:])),5)

    def test_tight_example_is_repositioned_nearby_without_losing_design(self):
        card=reviewed_fixture()['cards'][2];plan=default_plan(card);plan['confidence']='high'
        body=measured_plan(card,plan)[0];plan['blocks'][1]['y']=body['bounds'][3]+12
        with self.assertRaisesRegex(ValueError,'breathing room'):measured_plan(card,plan)
        with tempfile.TemporaryDirectory() as temp:
            photo=Path(temp)/'photo.jpg';Image.new('RGB',(1080,1350),'#555555').save(photo)
            adjusted=nearest_valid_plan(card,plan,photo);self.assertIsNotNone(adjusted)
        safe,record=adjusted;blocks=measured_plan(card,safe)
        self.assertGreaterEqual(blocks[1]['y']-blocks[0]['bounds'][3],EXAMPLE_BLOCK_GAP)
        for old,new in zip(plan['blocks'],safe['blocks']):
            self.assertEqual({k:v for k,v in old.items() if k not in ('x','y')},
                             {k:v for k,v in new.items() if k not in ('x','y')})
        self.assertTrue(record['moves'])


if __name__=='__main__':unittest.main()
