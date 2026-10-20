"""Adversarial declarative inputs and actual glyph/pixel rendering, without APIs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from PIL import Image, ImageDraw

from easybosnian.designs import BODY_STYLES, EXAMPLE_STYLES, PANEL_STYLES, MARKER_STYLES
from easybosnian.hybrid import block_spec, default_plan, declared_block, editorial_plan, measured_plan, render_hybrid
from easybosnian.render import font, measure, wrap, draw_tracked_label
from easybosnian.visual_placement import RESULT_SCHEMA, review_compositions
from easybosnian.stories import artwork_palette
from easybosnian.success_report import report_data, with_rendering
from test_project import reviewed_fixture
from test_success_report import RUN, results


class DeclarativeVisualContractTests(unittest.TestCase):
    def test_photographic_body_and_answers_require_panels_but_title_example_fades_remain(self):
        card=reviewed_fixture()['cards'][2]
        plan=default_plan(card)
        plan['blocks'][0]['style']='caption'
        with self.assertRaisesRegex(ValueError,'Invalid hybrid composition contract'):
            measured_plan(card,plan)
        with self.assertRaisesRegex(ValueError,'Unsupported explanation/answer style'):
            block_spec(card,'body',952,'caption')
        self.assertNotIn('caption',BODY_STYLES)
        self.assertEqual(set(BODY_STYLES)-{'plain'},set(PANEL_STYLES)-{'pill','folded_corner'})
        plan['blocks'][0]['style']='plain'
        with self.assertRaisesRegex(ValueError,'Paper styles require the editorial design'):
            measured_plan(card,plan)
        for role in ('A','B'):
            quiz=reviewed_fixture()['cards'][0]
            with self.assertRaisesRegex(ValueError,'Unsupported explanation/answer style'):
                block_spec(quiz,role,952,'caption')
        # Both requested title/example colour directions still render; all
        # original body-panel treatments remain distinct in the pixel test.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg'
            Image.new('RGB',(1080,1350),'#828282').save(photo)
            for tone in ('paper_dark','ink_light'):
                plan=default_plan(card);plan['heading_tone']=tone
                plan['blocks'][-1]['photo_tone']=tone
                metrics=render_hybrid(card,'terracotta-sand',photo,root/f'{tone}.jpg',plan)
                self.assertEqual(metrics['heading_tone'],tone)
                self.assertEqual(metrics['example_tone'],tone)
                self.assertGreaterEqual(metrics['heading_contrast'],3)
                self.assertGreaterEqual(metrics['example_contrast'],4.5)

    def test_tracked_bosnian_category_accents_share_capital_baseline(self):
        face=font(50,'SemiBold')
        image=Image.new('L',(360,120))
        draw_tracked_label(ImageDraw.Draw(image),(16,40),'SŠCČ',face,255)
        x=16;bounds=[]
        for letter in 'SŠCČ':
            width=face.getlength(letter)
            bounds.append(image.crop((round(x),0,round(x+width),120)).getbbox())
            x+=width+4
        self.assertEqual(bounds[0][3],bounds[1][3])
        self.assertEqual(bounds[2][3],bounds[3][3])
        self.assertLess(bounds[1][1],bounds[0][1])
        self.assertLess(bounds[3][1],bounds[2][1])

    def test_model_contract_rejects_every_freeform_rendering_escape_and_role_mix(self):
        package=reviewed_fixture()
        base={'cards':{c['kind']:dict(default_plan(c),palette='blue-ice') for c in package['cards']}}
        validator=Draft202012Validator(RESULT_SCHEMA)
        self.assertFalse(list(validator.iter_errors(base)))
        # Provider-facing structured transport needs explicit null/default intent;
        # leaving optional keys undefined must not break the entire visual stage.
        def check_objects(schema):
            if schema.get('type')=='object':
                self.assertEqual(set(schema['required']),set(schema['properties']))
                self.assertFalse(schema['additionalProperties'])
            for branch in schema.get('anyOf',[]):check_objects(branch)
            for child in schema.get('properties',{}).values():check_objects(child)
            if 'items' in schema:check_objects(schema['items'])
        check_objects(RESULT_SCHEMA)
        for field,value in [('text','New\ntext'),('font','custom.ttf'),('colour','#123456'),
                            ('opacity',.4),('radius',8),('border',{}),('shadow','css'),
                            ('filter','blur'),('draw','python code'),('height',20)]:
            bad=copy.deepcopy(base);bad['cards']['word']['blocks'][0][field]=value
            self.assertTrue(list(validator.iter_errors(bad)),field)
        for role,styles in [('body',EXAMPLE_STYLES),('example',BODY_STYLES)]:
            for style in styles:
                bad=copy.deepcopy(base);block=next(b for b in bad['cards']['word']['blocks'] if b['role']==role)
                block['style']=style
                self.assertTrue(list(validator.iter_errors(bad)),(role,style))
        for field,value in [('design','anything'),('palette','#123456'),('photo_window',{'opacity':.3})]:
            bad=copy.deepcopy(base);bad['cards']['word'][field]=value
            self.assertTrue(list(validator.iter_errors(bad)),field)
        bad=copy.deepcopy(base);del bad['cards']['word']['palette']
        self.assertTrue(list(validator.iter_errors(bad)))

    def test_typography_is_role_bounded_measured_and_never_clamped_or_truncated(self):
        card=reviewed_fixture()['cards'][2]
        for role,style,low,high in [('body','rounded',32,48),('example','italic_photo_fade',28,40)]:
            for size in (low,high):
                spec=block_spec(card,role,952,style,size,1.55)
                self.assertEqual(spec['face'].size,size)
            for size in (low-1,high+1,True,36.5):
                with self.assertRaises(ValueError):block_spec(card,role,952,style,size)
            for leading in (1.19,1.56,True,float('nan')):
                with self.assertRaises(ValueError):block_spec(card,role,952,style,low,leading)
        quiz=reviewed_fixture()['cards'][0]
        for size in (31,47):
            with self.assertRaises(ValueError):block_spec(quiz,'A',952,'rounded',size)
        with self.assertRaises(ValueError):block_spec(card,'body',300,'rounded',48,1.3,1)
        a=block_spec(card,'body',500,'rounded',36,1.25)
        b=block_spec(card,'body',500,'rounded',36,1.55)
        self.assertEqual(a['rows'],b['rows']);self.assertGreater(b['height'],a['height'])
        plan=default_plan(card);plan['blocks'][0].update(font_size=48,line_spacing=1.55)
        plan['blocks'][1]['y']=plan['blocks'][0]['y']+block_spec(card,'body',952,'rounded',48,1.55)['height']-5
        with self.assertRaises(ValueError):measured_plan(card,plan)
        # A long proposal must fail, rather than shrink the requested typography.
        long=copy.deepcopy(card);long['body']='Čuvamo č, ć, š, ž i đ. '*35
        with self.assertRaises(ValueError):measured_plan(long,default_plan(long))

    def test_unicode_wrap_reconstructs_source_and_does_not_break_nonbreaking_words(self):
        for preference in ('natural','balanced'):
            for text in ('Čuvamo č, ć, š, ž i đ. Bosanski jezik.',
                         'Čuvamo\u2003svako\u2009slovo i sva značenja.',
                         'Bosna\u00a0i\u00a0Hercegovina ima lijepa mjesta.',
                         'Čuvamo c\u0301 i s\u030c u izvornom obliku.'):
                rows=wrap(text,font(32),430,preference)
                self.assertEqual(rows.reconstructed(),text)
                self.assertTrue(all(font(32).getlength(row)<=430 for row in rows))
        with self.assertRaises(ValueError):wrap('Bosna\u00a0i\u00a0Hercegovina',font(48),120)
        with self.assertRaises(ValueError):wrap('Nova\nlinija',font(32),500)
        face=font(48);rows=['ČĆŠŽĐ\u0301','ČĆŠŽĐ\u0301']
        with self.assertRaises(ValueError):measure(rows,face,1.0)

    def test_body_styles_are_real_distinct_pixels_and_examples_remain_unboxed_italic(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['body']='Čuvamo svako slovo.';card['example']='Čuvamo č, ć, š, ž i đ.'
        before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#394854').save(photo)
            outputs={}
            for style in BODY_STYLES:
                plan=editorial_plan(card) if style=='plain' else default_plan(card)
                plan['confidence']='high';plan['blocks'][0]['style']=style
                if style!='plain':plan['blocks'][0].update(y=750);plan['blocks'][1].update(y=1020)
                metrics=render_hybrid(card,'blue-ice',photo,root/'card.jpg',plan)
                self.assertGreaterEqual(metrics['body_contrast'],4.5)
                self.assertEqual(metrics['block_styles']['body'],style)
                outputs[style]=(root/'card.jpg').read_bytes()
            self.assertEqual(len(set(outputs.values())),14)
            for style in EXAMPLE_STYLES:
                plan=editorial_plan(card) if style=='italic_footer' else default_plan(card)
                plan['blocks'][-1]['style']=style
                with patch('easybosnian.hybrid.draw_rows',wraps=__import__('easybosnian.render',fromlist=['draw_rows']).draw_rows) as draw:
                    metrics=render_hybrid(card,'blue-ice',photo,root/'example.jpg',plan)
                example=next(c for c in draw.call_args_list if ' '.join(c.args[2])==card['example'])
                self.assertTrue(str(example.args[3].path).endswith('Lora-Italic.ttf'))
                self.assertNotIn(metrics['example_bounds'],metrics['panel_bounds'])
            self.assertEqual(card,before)

    def test_every_answer_panel_combines_with_every_badge_without_changing_copy_or_geometry(self):
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0])
        quiz['question']='Koji je odgovor tačan?'
        quiz['options']=[{'label':'A','text':'Čuvamo sva slova.'},{'label':'B','text':'Biramo drugi odgovor.'}]
        before=copy.deepcopy(quiz)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#394854').save(photo)
            variants={}
            for style in PANEL_STYLES:
                bounds=[];pixels=[]
                for badge in MARKER_STYLES:
                    plan=default_plan(quiz)
                    for i,block in enumerate(plan['blocks']):
                        block.update(style=style,marker_style=badge,x=64,y=740+i*180,width=952)
                    with patch('easybosnian.hybrid.draw_rows',wraps=__import__('easybosnian.render',fromlist=['draw_rows']).draw_rows) as draw:
                        metrics=render_hybrid(quiz,'blue-ice',photo,root/'answer.jpg',plan)
                    self.assertGreaterEqual(metrics['body_contrast'],4.5)
                    self.assertEqual(metrics['answer_badges'],{'A':badge,'B':badge})
                    text=[' '.join(c.args[2]) for c in draw.call_args_list]
                    for option in quiz['options']:self.assertIn(option['text'],text)
                    bounds.append(metrics['panel_bounds']);pixels.append((root/'answer.jpg').read_bytes())
                self.assertTrue(all(b==bounds[0] for b in bounds))
                self.assertEqual(len(set(pixels)),4)
                variants[style]=pixels[0]
            self.assertEqual(len(set(variants.values())),15)
        self.assertEqual(quiz,before)

    def test_shared_answer_row_aligns_panel_heights_badges_and_glyph_baselines(self):
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0])
        quiz['question']='Šta se lijepi na pismo kao sredstvo plaćanja poštarine?'
        quiz['options']=[{'label':'A','text':'Razglednica'},
                         {'label':'B','text':'Poštanska marka'},
                         {'label':'C','text':'Novine'}]
        plan=default_plan(quiz);plan['confidence']='high'
        for block,(x,y,width) in zip(plan['blocks'],((64,320,440),(524,320,492),(64,490,320))):
            block.update(x=x,y=y,width=width,style='minimal_rule',font_size=38,line_spacing=1.3)
        measured=measured_plan(quiz,plan)
        self.assertEqual(measured[0]['bounds'][1::2],measured[1]['bounds'][1::2])
        self.assertEqual(measured[2]['y'],490)  # Intentional stagger stays exact.
        before=copy.deepcopy(quiz)
        from easybosnian.render import draw_rows
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);Image.new('RGB',(1080,1350),'#394854').save(root/'photo.jpg')
            with patch('easybosnian.hybrid.draw_rows',wraps=draw_rows) as drawing:
                metrics=render_hybrid(quiz,'charcoal-lemon',root/'photo.jpg',root/'quiz.jpg',plan)
            calls=[c for c in drawing.call_args_list if hasattr(c.args[2],'source')
                   and c.args[2].source in [o['text'] for o in quiz['options']]
                   and isinstance(c.args[4],str)]  # Exclude glyph masks used for contrast checks.
            self.assertEqual(len(calls),3)
            # draw_rows subtracts actual glyph top; compare the common origin,
            # rather than demanding accent pixels begin at the same height.
            origins=[c.args[1][1]-min(c.args[3].getbbox(row)[1] for row in c.args[2]) for c in calls]
            self.assertEqual(origins[0],origins[1])
            self.assertEqual(metrics['panel_bounds'][0][1::2],metrics['panel_bounds'][1][1::2])
            for call,option in zip(calls,quiz['options']):
                self.assertEqual(call.args[2].reconstructed(),option['text'])
        self.assertEqual(quiz,before)

    def test_shared_answer_font_cells_preserve_multiline_diacritics_and_fit(self):
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0])
        quiz['options']=[{'label':'A','text':'Čuvanje pisama i čitanje poruka'},
                         {'label':'B','text':'Širenje znanja i slanje čestitki'}]
        specs=[block_spec(quiz,role,440,font_size=38) for role in ('A','B')]
        self.assertGreater(len(specs[0]['rows']),1)
        self.assertEqual(len(specs[0]['rows']),len(specs[1]['rows']))
        self.assertEqual(specs[0]['height'],specs[1]['height'])
        for spec,option in zip(specs,quiz['options']):
            self.assertEqual(spec['rows'].reconstructed(),option['text'])
            actual_height=measure(spec['rows'],spec['face'],spec['line_spacing'])[0]
            self.assertLessEqual(spec['text_cell_offset']+actual_height,spec['text_cell_height'])
        with self.assertRaises(ValueError):
            block_spec(quiz,'A',440,font_size=38,max_lines=1)

    def test_bottom_sheet_and_required_photo_content_geometry_are_enforced(self):
        card=reviewed_fixture()['cards'][2]
        for change in ({'y':600},{'y':750,'width':480}):
            plan=default_plan(card);plan['blocks'][0].update(style='bottom_sheet',**change)
            with self.assertRaises(ValueError):measured_plan(card,plan)
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0]);quiz['quiz_format']='visual_identification'
        plan=default_plan(quiz);plan['confidence']='high'
        measured_plan(quiz,plan)
        plan['blocks'][0]['y']=plan['photo_window']['y']+30
        with self.assertRaises(ValueError):measured_plan(quiz,plan)

    def test_invalid_contract_calls_visual_model_once_and_uses_deterministic_fallback(self):
        package=reviewed_fixture();proposal={'cards':{c['kind']:dict(default_plan(c),palette='blue-ice') for c in package['cards']}}
        proposal['cards']['word']['blocks'][0]['font_size']=100
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as child:
            selected,status=review_compositions(package,{k:{'sheet':Path(k+'.jpg')} for k in ('quiz','lesson','word')})
        child.assert_called_once();self.assertEqual(status,'reviewed')
        for card in package['cards']:
            self.assertEqual(selected['cards'][card['kind']],dict(default_plan(card),palette='blue-ice'))
        self.assertEqual(selected['card_failures'],{'word':'review violated the declarative schema'})

    def test_quiz_options_have_independent_styles_badges_typography_and_geometry(self):
        quiz=copy.deepcopy(reviewed_fixture()['cards'][0]);quiz['options'].append({'label':'D','text':'Glas'})
        plan=default_plan(quiz)
        for i,(block,style,badge) in enumerate(zip(plan['blocks'],('rounded','outlined','side_rule','overlay_dark'),
                                                 ('circle','rounded_square','square','triangle'))):
            block.update(x=64 if i%2==0 else 564,y=400+i*185,width=452,style=style,marker_style=badge,
                         font_size=34+i*2,line_spacing=1.3)
        measured=measured_plan(quiz,plan)
        self.assertEqual([b['x'] for b in measured],[64,564,64,564])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);Image.new('RGB',(1080,1350),'#394854').save(root/'photo.jpg')
            metrics=render_hybrid(quiz,'blue-ice',root/'photo.jpg',root/'quiz.jpg',plan)
            self.assertEqual(list(metrics['answer_badges'].values()),['circle','rounded_square','square','triangle'])
            variants=[]
            for badge in ('circle','rounded_square','square','triangle'):
                same=default_plan(quiz)
                for b in same['blocks']:b['marker_style']=badge
                render_hybrid(quiz,'blue-ice',root/'photo.jpg',root/'quiz.jpg',same)
                variants.append((root/'quiz.jpg').read_bytes())
            self.assertEqual(len(set(variants)),4)
        bad=copy.deepcopy(plan);bad['blocks'][0]['marker_style']='draw a star'
        with self.assertRaises(ValueError):measured_plan(quiz,bad)
        for card in reviewed_fixture()['cards'][1:]:
            bad=default_plan(card);bad['blocks'][0]['marker_style']='triangle'
            with self.assertRaises(ValueError):measured_plan(card,bad)

    def test_legacy_design_template_cannot_change_artwork_cache_provenance(self):
        from easybosnian.artwork import render_input
        package=reviewed_fixture();expected=render_input(package)
        for card in package['cards']:card['design_template']='framed'
        self.assertEqual(render_input(package),expected)
        self.assertEqual(expected['rendering_version'],21)

    def test_unshaded_italic_rejects_mixed_photo_but_fixed_fade_can_pass(self):
        from PIL import ImageDraw
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['body']='Ovo je primjer.'
        card['example']='Čuvamo č, ć, š, ž i đ.'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);photo=Image.new('RGB',(1080,1350),'white');draw=ImageDraw.Draw(photo)
            for x in range(0,1080,12):draw.rectangle((x,0,x+5,1350),fill='black')
            photo.save(root/'photo.png')
            plan=default_plan(card);plan['blocks'][1]['style']='italic_photo'
            with self.assertRaises(ValueError):render_hybrid(card,'blue-ice',root/'photo.png',root/'bad.jpg',plan)
            plan['blocks'][1]['style']='italic_photo_fade'
            result=render_hybrid(card,'blue-ice',root/'photo.png',root/'good.jpg',plan)
            self.assertGreater(result['example_shading'],0)
            self.assertGreaterEqual(result['example_contrast'],4.5)

    def test_per_card_palettes_carry_into_stories_and_whitelisted_report_typography(self):
        package=reviewed_fixture();choices={'quiz':'blue-ice','lesson':'forest-mint','word':'terracotta-sand'}
        # Use only actual catalogue IDs (names deliberately never inferred).
        from easybosnian.core import ROOT,read_json
        ids=list(read_json(ROOT/'data/design-palettes.json'));choices=dict(zip(choices,ids[:3]))
        assets={k:{'metrics':{'palette':p}} for k,p in choices.items()}
        for k,p in choices.items():self.assertEqual(artwork_palette(package,assets,k),read_json(ROOT/'data/design-palettes.json')[p])
        placement={'batch':package['date'],'batch_id':package['date'],'cards':{
            k:{'position':'free','palette':p,'design':'hybrid','block_styles':{'body':'rounded'},
               'block_typography':{'body':{'font_size':36,'line_spacing':1.4,'max_lines':None,'wrapping':'balanced'}}} for k,p in choices.items()}}
        data=report_data(package,results(),RUN);final=with_rendering(data,placement)
        self.assertEqual(final['final_palette'],'per card')
        self.assertEqual({c['rendering']['palette'] for c in final['cards']},set(choices.values()))
        bad=copy.deepcopy(placement);bad['cards']['word']['block_typography']['body']['font']='evil.ttf'
        with self.assertRaises(ValueError):with_rendering(data,bad)
