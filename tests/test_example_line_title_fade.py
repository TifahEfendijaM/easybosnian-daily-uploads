"""Prefer safe single-line examples; restore title extent without forcing shade."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw,ImageChops
from easybosnian.hybrid import (default_plan,measured_plan,render_hybrid,heading,
                               protect_text,TITLE_FADE_FEATHER,PHOTO_FADE_FEATHER)
from easybosnian.visual_adjustment import (single_line_example_plan,applied_adjustment,
                                          safe_adjustment,EXAMPLE_LINE_REASON)
from easybosnian.success_report import report_data,with_rendering,render_report
from test_project import reviewed_fixture
from test_success_report import RUN,results
import test_visual_provenance as provenance_harness

EXAMPLE='Patka kraj vode ima žut kljun i zelenu glavu.'


class ExampleLineTitleFadeTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.photo=self.root/'photo.jpg'
        Image.new('RGB',(1080,1350),'#303030').save(self.photo)
        self.card=reviewed_fixture()['cards'][2];self.card['example']=EXAMPLE
        self.plan=dict(default_plan(self.card),confidence='high',heading_tone='paper_dark')
        self.plan['blocks'][-1].update(width=300,x=64,y=1050,font_size=28,
                                       max_lines=2,photo_tone='paper_dark')

    def test_actual_duck_sentence_widens_to_one_exact_line_without_other_design_changes(self):
        original=copy.deepcopy(self.plan);source=copy.deepcopy(self.card)
        self.assertEqual(len(measured_plan(self.card,self.plan)[-1]['rows']),2)
        final=single_line_example_plan(self.card,self.plan,self.photo)
        example=measured_plan(self.card,final)[-1]
        self.assertEqual(list(example['rows']),[EXAMPLE])
        self.assertEqual(example['width'],559)
        self.assertEqual((example['x'],example['y']),(64,1050))
        expected=copy.deepcopy(original);expected['blocks'][-1]['width']=559
        self.assertEqual(final,expected);self.assertEqual(self.plan,original);self.assertEqual(self.card,source)
        detail=applied_adjustment(original,final)
        self.assertEqual(detail['reason'],EXAMPLE_LINE_REASON)
        self.assertEqual(detail['moves'],[{'element':'example',
             'from':{'x':64,'y':1050,'width':300},'to':{'x':64,'y':1050,'width':559}}])
        self.assertEqual(safe_adjustment(detail),detail)
        self.plan['blocks'][-1]['max_lines']=1
        repaired=single_line_example_plan(self.card,self.plan,self.photo)
        self.assertEqual(repaired['blocks'][-1]['max_lines'],1)
        self.assertEqual(len(measured_plan(self.card,repaired)[-1]['rows']),1)

    def test_nearest_horizontal_shift_keeps_y_and_long_or_already_single_lines_stay_unchanged(self):
        self.plan['blocks'][-1]['x']=700
        final=single_line_example_plan(self.card,self.plan,self.photo)
        self.assertEqual((final['blocks'][-1]['x'],final['blocks'][-1]['width']),(457,559))
        self.assertEqual(final['blocks'][-1]['y'],1050)
        final['blocks'][-1]['max_lines']=1
        self.assertIsNone(single_line_example_plan(self.card,final,self.photo))
        self.card['example']=' '.join([EXAMPLE]*3)
        self.plan['blocks'][-1].update(x=64,width=952,max_lines=None)
        self.assertIsNone(single_line_example_plan(self.card,self.plan,self.photo))

    def test_collision_and_narrow_photo_window_keep_valid_wrapping(self):
        self.card['body']='Kljun pomaže ptici.'
        self.plan['blocks'][0].update(x=600,y=980,width=416,font_size=36)
        self.plan['blocks'][-1]['y']=1000
        measured_plan(self.card,self.plan)
        self.assertIsNone(single_line_example_plan(self.card,self.plan,self.photo))
        self.plan['blocks'][0].update(x=64,y=900,width=952)
        self.plan.update(heading_tone='auto',photo_window={'y':350,'height':500,'fit':'contain'})
        self.plan['blocks'][-1].update(x=360,y=500)
        render_hybrid(self.card,'forest-cream',self.photo,self.root/'window.jpg',self.plan)
        self.assertIsNone(single_line_example_plan(self.card,self.plan,self.photo))

    def harness(self):
        h=provenance_harness.VisualProvenanceTests();h.setUp()
        h.package['cards'][2]['example']=EXAMPLE
        proposal=h.proposal(h.package)
        for plan in proposal['cards'].values():plan['palette']='forest-cream'
        proposal['cards']['word']=dict(self.plan,palette='forest-cream')
        return h,proposal

    def test_pipeline_reports_applied_width_with_independent_palette_and_no_extra_calls(self):
        h,proposal=self.harness()
        placement,metrics=h.render(h.package,proposal)
        word=placement['cards']['word']
        self.assertEqual(word['status'],'adjusted')
        self.assertEqual(word['provenance']['layout']['source'],'chatgpt')
        self.assertIn('single-line PRIMJER',word['provenance']['layout']['reason'])
        self.assertEqual(word['provenance']['palette']['source'],'chatgpt')
        self.assertEqual(word['composition']['blocks'][-1]['width'],559)
        self.assertEqual(len(measured_plan(h.package['cards'][2],metrics['word']['composition'])[-1]['rows']),1)
        report=with_rendering(report_data(h.package,results(),RUN),placement)
        text,markup=render_report(report)
        self.assertIn(r'single\-line PRIMJER adjustment',text)
        self.assertIn('single-line PRIMJER adjustment',markup)
        self.assertIn('width',text);self.assertIn('559',text)
        changed=copy.deepcopy(placement)
        changed['cards']['word']['layout_adjustment']['moves'][0]['to']['width']+=1
        with self.assertRaisesRegex(ValueError,'differs from rendered composition'):
            with_rendering(report_data(h.package,results(),RUN),changed)

    def test_combined_position_repair_and_one_line_expansion_are_both_reported(self):
        h,proposal=self.harness()
        proposal['cards']['word']['blocks'][0]['x']=30
        proposal['cards']['word']['blocks'][-1]['x']=700
        placement,_=h.render(h.package,proposal)
        word=placement['cards']['word'];moves=word['layout_adjustment']['moves']
        self.assertEqual(word['status'],'adjusted')
        self.assertEqual({m['element'] for m in moves},{'body','example'})
        example=next(m for m in moves if m['element']=='example')
        self.assertEqual(example['from'],{'x':700,'y':1050,'width':300})
        self.assertEqual(example['to'],{'x':457,'y':1050,'width':559})
        for bad in (dict(word['layout_adjustment'],reason='untrusted'),
                    {'reason':EXAMPLE_LINE_REASON,'moves':[dict(example,element='body')]}):
            with self.assertRaises(ValueError):safe_adjustment(bad)

    def test_unreadable_wider_line_keeps_the_original_safe_wrapping_without_fallback(self):
        h,proposal=self.harness()
        proposal['cards']['word']['blocks'][-1]['style']='italic_photo'
        photo=Image.new('RGB',(1080,1350),'#080808')
        ImageDraw.Draw(photo).rectangle((400,0,1079,1349),fill='#ffffff')
        placement,metrics=h.render(h.package,proposal,photo=photo)
        word=placement['cards']['word']
        self.assertEqual(word['status'],'accepted')
        self.assertEqual(word['composition']['blocks'][-1]['width'],300)
        self.assertEqual(word['provenance']['palette']['source'],'chatgpt')
        self.assertNotIn('layout_adjustment',word);self.assertNotIn('rejection',word)
        self.assertGreaterEqual(metrics['word']['example_contrast'],4.5)

    def test_title_restores_100px_extent_while_examples_and_category_protection_stay_compact(self):
        Image.new('RGB',(1080,1350),'#b0b0b0').save(self.photo)
        plan=default_plan(self.card);plan['heading_tone']='paper_dark'
        observed=[]
        def checked(image,*args,**kwargs):
            before=image.copy();result=protect_text(image,*args,**kwargs)
            if kwargs.get('feather')==TITLE_FADE_FEATHER:
                bounds=ImageChops.difference(image.convert('RGB'),before.convert('RGB')).getbbox()
                observed.append(bounds)
                self.assertEqual(image.crop((0,0,1080,127)).tobytes(),before.crop((0,0,1080,127)).tobytes())
            return result
        with patch('easybosnian.hybrid.protect_text',side_effect=checked):
            result=render_hybrid(self.card,'forest-cream',self.photo,self.root/'title.jpg',plan)
        self.assertEqual((TITLE_FADE_FEATHER,PHOTO_FADE_FEATHER),(100,32))
        bottom=heading(self.card)[2]
        self.assertEqual(len(observed),1)
        self.assertGreater(observed[0][3],bottom+32)
        self.assertLessEqual(observed[0][3],math.ceil(bottom+100))
        self.assertGreaterEqual(result['heading_contrast'],3)
        for background,tone in [('#000000','paper_dark'),('#ffffff','ink_light')]:
            Image.new('RGB',(1080,1350),background).save(self.photo)
            plan['heading_tone']=tone
            self.assertEqual(render_hybrid(self.card,'forest-cream',self.photo,self.root/'readable.jpg',plan)['heading_shading'],0)


if __name__=='__main__':unittest.main()
