"""Production title backings span both edges, independently of title length."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from easybosnian.hybrid import (default_plan,render_hybrid,protect_text,HEADING_TOP,
                               TITLE_FADE_FEATHER,TITLE_FADE_PADDING)
from easybosnian.visual_placement import review_compositions
from test_project import reviewed_fixture


class FullWidthTitleTests(unittest.TestCase):
    def test_actual_renderer_has_uniform_rows_to_both_edges_for_black_and_white_titles(self):
        source=reviewed_fixture()['cards'][2]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for title in ('rep','Čuvamo svoju riječ'):
                for tone,background in (('paper_dark','#ffffff'),('ink_light','#000000')):
                    with self.subTest(title=title,tone=tone):
                        card=copy.deepcopy(source);card['heading']=title
                        plan=dict(default_plan(card),confidence='high',heading_tone=tone)
                        before=copy.deepcopy(plan);surfaces=[]
                        photo=root/'photo.png';Image.new('RGB',(1080,1350),background).save(photo)
                        def observe(image,*args,**kwargs):
                            result=protect_text(image,*args,**kwargs)
                            if kwargs.get('feather')==TITLE_FADE_FEATHER:
                                self.assertGreater(result[2],0)
                                # Observe the real photographic backing before
                                # category, glyphs, panels or PRIMJER are drawn.
                                for y in (HEADING_TOP-40,HEADING_TOP,HEADING_TOP+20):
                                    row={image.getpixel((x,y)) for x in range(1080)}
                                    self.assertEqual(len(row),1)
                                    self.assertNotEqual(next(iter(row))[:3],Image.new('RGB',(1,1),background).getpixel((0,0)))
                                surfaces.append(image.copy())
                            return result
                        with patch('easybosnian.hybrid.protect_text',side_effect=observe):
                            metrics=render_hybrid(card,'gold-cream',photo,root/'card.jpg',plan)
                        self.assertEqual(len(surfaces),1)
                        self.assertGreaterEqual(metrics['heading_contrast'],3)
                        self.assertGreaterEqual(metrics['body_contrast'],4.5)
                        self.assertGreaterEqual(metrics['example_contrast'],4.5)
                        self.assertEqual(metrics['composition'],before);self.assertEqual(plan,before)
                        for y in (0,HEADING_TOP-TITLE_FADE_PADDING-TITLE_FADE_FEATHER):
                            self.assertEqual(surfaces[0].getpixel((0,y))[:3],Image.new('RGB',(1,1),background).getpixel((0,0)))

    def test_prompt_strongly_prefers_lower_example_for_an_upper_body_but_keeps_other_positions(self):
        package=reviewed_fixture()
        proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette=p)
                  for c,p in zip(package['cards'],('gold-cream','blue-ice','forest-cream'))}}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
            result,status=review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in proposal['cards']})
        self.assertEqual(status,'reviewed');self.assertEqual(result['cards'],proposal['cards'])
        prompt=model.call_args.args[0]
        for rule in ('MUST span the ENTIRE IMAGE WIDTH','same shade opacity across each horizontal row',
                     'STRONGLY PREFER placing PRIMJER in the LOWER photo area',
                     'First compare safe lower placements','When the body sits lower, an example far above remains',
                     "against that actual part of the photograph",'do not inherit the top area'):
            self.assertIn(rule,prompt)
        self.assertNotIn('Pillow lightens the surrounding photograph rather than extending core opacity',prompt)
        model.assert_called_once()
