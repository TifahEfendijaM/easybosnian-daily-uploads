"""Regression tests for false rejections; real glyphs, exact data, one model call."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from easybosnian.hybrid import block_spec, default_plan, measured_plan, render_hybrid, serif, roles, MIN_BLOCK_GAP, EXAMPLE_BLOCK_GAP
from easybosnian.render import draw_rows, font, measure
from easybosnian.visual_measurements import block_measurements, PROFILE_COLUMNS
from easybosnian.visual_placement import KINDS, review_compositions
from easybosnian.visual_policy import apply_policy
from test_project import reviewed_fixture
import test_visual_provenance as provenance_tests


class GlyphAcceptanceTests(unittest.TestCase):
    def test_examples_now_require_breathing_room_while_preserving_other_geometry(self):
        cases=[
            ({'kind':'lesson','heading':'Kuda treba skrenuti?',
              'body':'Kad pitaš za put, traži i mjesto skretanja. „Skreni desno” govori o pravcu, ali „Skreni desno na sljedećoj raskrsnici” govori i gdje. Ako ti uputa nije jasna, pitaj na kojoj raskrsnici treba skrenuti.',
              'example':'Na kojoj raskrsnici trebam skrenuti lijevo?'},'notebook_margin',870,1090,34,12),
            ({'kind':'word','heading':'kaciga',
              'body':'Kaciga je zaštitna oprema koju nosimo na glavi. Biciklistička kaciga treba odgovarati veličini glave i pravilno stajati. Prije vožnje namjesti je i pričvrsti remen.',
              'example':'Prije vožnje stavila sam kacigu na glavu.'},'overlay_dark',850,1080,36,10),
        ]
        for card,style,body_y,example_y,example_size,gap in cases:
            plan=default_plan(card);plan['confidence']='high'
            plan['blocks'][0].update(style=style,y=body_y,font_size=34,line_spacing=1.25,max_lines=6)
            plan['blocks'][1].update(y=example_y,font_size=example_size,line_spacing=1.30,max_lines=2)
            with self.assertRaisesRegex(ValueError,'breathing room'):measured_plan(card,plan)
            plan['blocks'][0]['y']-=24
            plan['blocks'][1]['y']-=24
            plan['blocks'][1]['y']+=EXAMPLE_BLOCK_GAP-gap
            before=copy.deepcopy(plan)
            measured=measured_plan(card,plan)
            self.assertEqual(measured[1]['y']-measured[0]['bounds'][3],EXAMPLE_BLOCK_GAP)
            self.assertEqual(plan,before)
            # Preserve a real positive minimum gap and reject any overlap.
            for clearance in (EXAMPLE_BLOCK_GAP-1,0,-1):
                bad=copy.deepcopy(plan);bad['blocks'][1]['y']=measured[0]['bounds'][3]+clearance
                with self.assertRaisesRegex(ValueError,'overlap'):measured_plan(card,bad)

    def test_single_line_has_no_adjacent_line_to_collide_with(self):
        for face in (font(32),serif(32,True)):
            text='ČĆŠŽĐ gjpqy'
            height,step=measure([text],face,1.20)
            image=Image.new('L',(600,120))
            draw_rows(ImageDraw.Draw(image),(0,0),[text],face,255,1.20)
            self.assertEqual(image.getbbox()[3],height)
            self.assertEqual(step,round(face.size*1.20))

    def test_safe_accented_baselines_pass_but_real_collisions_still_fail(self):
        for face in (font(32),serif(32,True)):
            rows=['ČĆŠŽĐ','gjpqy'];boxes=[face.getbbox(row) for row in rows]
            step=round(face.size*1.20)
            # The old pooled-glyph test rejects this safe ordered pair.
            self.assertLess(step,max(b[3] for b in boxes)-min(b[1] for b in boxes)+4)
            self.assertGreaterEqual(step+boxes[1][1]-boxes[0][3],4)
            measure(rows,face,1.20)
            with self.assertRaisesRegex(ValueError,'leading collides'):
                measure(list(reversed(rows)),face,1.20)

    def test_height_matches_drawn_bottom_not_a_pooled_descender_on_last_row(self):
        for face in (font(32),serif(32,True)):
            rows=['gjpqy','ČĆŠŽĐ'];height,step=measure(rows,face,1.55)
            image=Image.new('L',(600,180))
            draw_rows(ImageDraw.Draw(image),(0,0),rows,face,255,1.55)
            self.assertEqual(image.getbbox()[3],height)
            boxes=[face.getbbox(row) for row in rows]
            pooled=max(b[3] for b in boxes)-min(b[1] for b in boxes)+step
            self.assertLess(height,pooled)

    def test_unboxed_trailing_space_does_not_reject_separate_visible_blocks(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2])
        card['body']='Čuvamo svako slovo.';card['example']='Ovo je primjer.'
        plan=default_plan(card);plan['confidence']='high'
        plan['blocks'][0].update(x=640,y=400,width=376,font_size=32)
        plan['blocks'][1].update(x=64,y=420,width=952,font_size=28)
        measured=measured_plan(card,plan)
        self.assertGreater(measured[1]['bounds'][2],measured[0]['bounds'][0])
        self.assertLess(measured[1]['occupied_bounds'][2]+14,measured[0]['bounds'][0])
        before=copy.deepcopy(plan)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#45525d').save(photo)
            result=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg',plan)
        self.assertEqual(plan,before)
        self.assertEqual(result['composition'],before)
        self.assertGreaterEqual(result['example_contrast'],4.5)
        # Actual copy overlap is still forbidden, as is panel surface overlap.
        plan['blocks'][1]['x']=640;plan['blocks'][1]['width']=376
        with self.assertRaisesRegex(ValueError,'overlap'):measured_plan(card,plan)
        plan['blocks'][1].update(x=64,width=952)
        card['example']='Čuvamo svako bosansko slovo i pišemo pažljivo svaki dan.'
        with self.assertRaisesRegex(ValueError,'overlap'):measured_plan(card,plan)


class ReviewerFitDataTests(unittest.TestCase):
    def test_body_fit_profiles_share_measurements_without_removing_real_styles(self):
        from easybosnian.designs import BODY_STYLES,PANEL_STYLES
        card=reviewed_fixture()['cards'][2]
        data=block_measurements(card,'body')
        self.assertEqual(set(data['measurements_by_style']),set(BODY_STYLES))
        self.assertEqual(set(data['fit_profiles']),{'rounded','split_panel','plain'})
        for style in set(BODY_STYLES)-{'split_panel','plain'}:
            self.assertEqual(data['measurements_by_style'][style]['measurement_family'],'rounded')
        # Body and answer insets differ; each role still has its own exact
        # profiles. No drawing renderer or allowed geometry is aliased.
        for role in ('body','A'):
            current=card if role=='body' else reviewed_fixture()['cards'][0]
            measured=block_measurements(current,role)
            for style in measured['measurements_by_style']:
                family=measured['measurements_by_style'][style]['measurement_family']
                for row in measured['fit_profiles'][family]:
                    width,size,leading,lines,height=row
                    spec=block_spec(current,role,width,style,size,leading)
                    self.assertEqual((len(spec['rows']),spec['height']),(lines,height))

    def test_every_profile_is_an_exact_renderer_measurement_and_catalogue_is_complete(self):
        from easybosnian.designs import BODY_STYLES,ANSWER_STYLES,EXAMPLE_STYLES
        package=reviewed_fixture()
        for card in package['cards']:
            for role in roles(card):
                data=block_measurements(card,role)
                expected=EXAMPLE_STYLES if role=='example' else BODY_STYLES if role=='body' else ANSWER_STYLES
                self.assertEqual(set(data['measurements_by_style']),set(expected))
                for style,reference in data['measurements_by_style'].items():
                    for row in data['fit_profiles'][reference['measurement_family']]:
                        values=dict(zip(PROFILE_COLUMNS,row))
                        spec=block_spec(card,role,values['width'],style,values['font_size'],values['line_spacing'])
                        self.assertEqual(spec['height'],values['height'])
                        self.assertEqual(len(spec['rows']),values['line_count'])

    def test_prompt_explains_exact_fit_without_limiting_free_creative_choices(self):
        package=reviewed_fixture()
        decisions={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='blue-ice') for c in package['cards']}}
        candidates={kind:{'sheet':Path('build')/(kind+'.jpg')} for kind in KINDS}
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(decisions)) as child:
            result,status=review_compositions(package,candidates)
        child.assert_called_once();self.assertEqual(status,'reviewed')
        self.assertEqual(child.call_args.kwargs['timeout'],600)
        prompt=child.call_args.args[0]
        self.assertIn('samples are not a geometry or creativity menu',prompt)
        self.assertIn('Do not place an example using an estimated body height',prompt)
        self.assertIn('Choose each block x,y,width freely',prompt)
        self.assertNotIn('correct_option',prompt)
        self.assertEqual(result['cards'],decisions['cards'])


class PerCardReviewIsolationTests(unittest.TestCase):
    def test_bad_one_card_schema_keeps_valid_siblings_and_approved_palette(self):
        helper=provenance_tests.VisualProvenanceTests();helper.setUp()
        proposal=helper.proposal(helper.package)
        proposal['cards']['lesson']['blocks'][0]['font']='untrusted.ttf'
        proposal['cards']['word']['blocks'][0]['style']='outlined'
        placement,metrics=helper.render(helper.package,proposal)
        self.assertEqual(placement['status'],'reviewed')
        for kind in ('quiz','word'):
            self.assertEqual(placement['cards'][kind]['provenance']['layout']['source'],'chatgpt')
            self.assertEqual(metrics[kind]['composition'],apply_policy(proposal['cards'][kind],panel_opacity=100))
        lesson=placement['cards']['lesson']
        self.assertEqual(lesson['provenance']['layout'],{'source':'fallback','reason':'review violated the declarative schema'})
        self.assertEqual(lesson['provenance']['palette']['source'],'chatgpt')
        self.assertNotIn('untrusted.ttf',str(placement))


if __name__=='__main__':unittest.main()
