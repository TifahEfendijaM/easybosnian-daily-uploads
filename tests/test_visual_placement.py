import contextlib
import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from PIL import Image, ImageChops

from easybosnian.artwork import artwork
from easybosnian.cloud_prepare import AgentIntegrityError, run_codex
from easybosnian.core import ROOT, read_json, write_json
from easybosnian.http import SafeError
from easybosnian.render import HEIGHT, WIDTH
from easybosnian.visual_placement import KINDS, RESULT_SCHEMA, composition_sheet, main, review_compositions
from easybosnian.hybrid import default_plan, render_hybrid, measured_plan, block_spec, serif, editorial_plan
from easybosnian.stories import artwork_palette
from test_cloud_preparation import auth
from test_project import reviewed_fixture


class HybridCompositionTests(unittest.TestCase):
    def decision(self):
        return {'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='terracotta-sand') for c in reviewed_fixture()['cards']}}

    def candidates(self):
        return {kind:{'sheet':Path('build')/(kind+'.jpg')} for kind in KINDS}

    def test_one_readonly_photo_call_chooses_free_geometry_and_palette_without_private_answers(self):
        result=self.decision()
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(result)) as child:
            decisions,status=review_compositions(reviewed_fixture(),self.candidates())
        self.assertEqual(decisions,result);self.assertEqual(status,'reviewed');child.assert_called_once()
        self.assertTrue(child.call_args.kwargs['read_only']);self.assertEqual(child.call_args.kwargs['timeout'],120)
        self.assertEqual(child.call_args.kwargs['result_contract'],RESULT_SCHEMA)
        self.assertEqual(child.call_args.kwargs['images'],[self.candidates()[k]['sheet'] for k in KINDS])
        prompt=child.call_args.args[0]
        self.assertIn('Choose each block x,y,width freely',prompt);self.assertIn('AFTER assessing',prompt)
        self.assertNotIn('correct_option',prompt);self.assertNotIn('private_review',prompt)

    def test_invalid_unavailable_review_never_retries_or_logs_freeform_text(self):
        bad=self.decision();bad['cards']['word']['private']='private-provider-text'
        for response in ('private-provider-text',json.dumps(bad)):
            output=io.StringIO()
            with patch('easybosnian.cloud_prepare.run_codex',return_value=response) as child,contextlib.redirect_stdout(output):
                result,status=review_compositions(reviewed_fixture(),self.candidates())
            child.assert_called_once();self.assertEqual(status,'unavailable')
            self.assertTrue(all(p['confidence']=='uncertain' for p in result['cards'].values()))
            self.assertNotIn('private-provider-text',output.getvalue())
        with patch('easybosnian.cloud_prepare.run_codex',side_effect=AgentIntegrityError('modified')):
            with self.assertRaises(AgentIntegrityError):review_compositions(reviewed_fixture(),self.candidates())

    def test_reference_sheet_complete_photo_crop_and_hybrid_have_distinct_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';baseline=root/'baseline.jpg';output=root/'sheet.jpg'
            Image.new('RGB',(1080,1350),'red').save(photo);Image.new('RGB',(1080,1350),'blue').save(baseline)
            composition_sheet(photo,baseline,output)
            with Image.open(output) as image:
                self.assertEqual(image.size,(2160,900))
                self.assertEqual(image.getpixel((360,450)),image.getpixel((1080,450)))
                self.assertNotEqual(image.getpixel((360,450)),image.getpixel((1800,450)))

    def test_independent_options_example_and_body_positions_and_exact_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#798e95').save(photo)
            for card in reviewed_fixture()['cards']:
                before=copy.deepcopy(card);plan=default_plan(card);plan['confidence']='high'
                if card['kind']=='quiz':
                    for index,b in enumerate(plan['blocks']):b.update(x=64 if index%2==0 else 564,y=410+index*220,width=452)
                else:
                    if card.get('example'):plan['blocks'][-1]['y']=1050
                with patch('easybosnian.hybrid.draw_rows',wraps=__import__('easybosnian.render',fromlist=['draw_rows']).draw_rows) as drawing:
                    result=render_hybrid(card,'blue-ice',photo,root/(card['kind']+'.jpg'),plan)
                self.assertEqual(card,before);self.assertEqual(result['panel_position'],'free')
                self.assertGreaterEqual(result['body_contrast'],4.5);self.assertGreaterEqual(result['heading_contrast'],3)
                texts=[' '.join(call.args[2]) for call in drawing.call_args_list]
                for text in ([o['text'] for o in card['options']] if card['kind']=='quiz' else [card['body'],card.get('example')]):
                    if text:self.assertIn(text,texts)
                if card.get('example'):
                    self.assertGreaterEqual(result['example_contrast'],4.5)
                    self.assertIn('Italic over photograph',result['example_style'])
                    self.assertEqual(len(result['panel_bounds']),1)

    def test_geometry_cannot_overlap_header_logo_other_blocks_or_lose_a_choice(self):
        card=reviewed_fixture()['cards'][0]
        for mutation in ('header','logo','overlap','missing','order','width'):
            plan=default_plan(card)
            if mutation=='header':plan['blocks'][0]['y']=200
            elif mutation=='logo':plan['blocks'][-1]['y']=1170
            elif mutation=='overlap':plan['blocks'][1]['y']=plan['blocks'][0]['y']
            elif mutation=='missing':plan['blocks'].pop()
            elif mutation=='order':plan['blocks'].reverse()
            else:plan['blocks'][0]['x']=716
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):measured_plan(card,plan)

    def test_photo_window_preserves_complete_photo_and_example_stays_over_it(self):
        card=reviewed_fixture()['cards'][2];card['body']='Ovo je kratko objašnjenje.';card['example']='Čuvamo č, ć, š, ž i đ.'
        plan={'confidence':'high','design':'hybrid','photo_window':{'y':500,'height':600,'fit':'contain'},'blocks':[
            {'role':'body','style':'rounded','x':64,'y':280,'width':952,'font_size':44,'line_spacing':1.30}, {'role':'example','style':'italic_photo_fade','x':320,'y':920,'width':440,'font_size':36,'line_spacing':1.30}]}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1024,1024),'#798e95').save(photo)
            result=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg',plan)
            self.assertFalse(result['photo_cropped']);self.assertEqual(result['photo_bounds'],[240,500,840,1100])
            bad=copy.deepcopy(plan);bad['blocks'][-1]['width']=952
            with self.assertRaises(ValueError):render_hybrid(card,'blue-ice',photo,root/'bad.jpg',bad)

    def test_editorial_renders_wide_photo_plain_body_and_italic_footer_with_exact_copy(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);before=copy.deepcopy(card)
        plan=editorial_plan(card)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg'
            Image.new('RGB',(1024,1024),'#718593').save(photo)
            with patch('easybosnian.hybrid.draw_rows',wraps=__import__('easybosnian.render',fromlist=['draw_rows']).draw_rows) as drawing:
                result=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg',plan)
            self.assertEqual(card,before);self.assertEqual(result['design'],'editorial')
            self.assertEqual(result['block_styles'],{'body':'plain','example':'italic_footer'})
            self.assertEqual(result['panel_bounds'],[]);self.assertEqual(result['photo_bounds'][2]-result['photo_bounds'][0],952)
            self.assertTrue(result['photo_cropped']);self.assertGreaterEqual(result['example_contrast'],4.5)
            self.assertLessEqual(result['example_bounds'][2],880);self.assertLessEqual(result['example_bounds'][3],1286)
            self.assertGreaterEqual(result['example_bounds'][1],result['photo_bounds'][3]+24)
            text=[' '.join(call.args[2]) for call in drawing.call_args_list]
            self.assertIn(card['body'],text);self.assertIn(card['example'],text)
            with Image.open(root/'card.jpg') as image:self.assertEqual((image.size,image.mode),((1080,1350),'RGB'))

    def test_supported_panel_and_example_styles_change_pixels_not_copy_or_font_fit(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);before=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#728192').save(photo)
            normal=render_hybrid(card,'blue-ice',photo,root/'normal.jpg')
            plan=default_plan(card);plan['confidence']='high'
            plan['blocks'][0]['style']='outlined';plan['blocks'][1].update(style='italic_photo_fade',y=950)
            altered=render_hybrid(card,'blue-ice',photo,root/'altered.jpg',plan)
            self.assertEqual(card,before);self.assertNotEqual((root/'normal.jpg').read_bytes(),(root/'altered.jpg').read_bytes())
            self.assertEqual(altered['block_styles'],{'body':'outlined','example':'italic_photo_fade'})
            self.assertEqual(len(altered['panel_bounds']),1);self.assertEqual(normal['body_font_size'],altered['body_font_size'])
            self.assertGreaterEqual(altered['example_contrast'],4.5)

    def test_style_contract_rejects_custom_fonts_bad_combinations_and_footer_photo_logo_collisions(self):
        card=reviewed_fixture()['cards'][2]
        for mutation in ('boxed','code','body_italic','example_plain','plain_overlay','footer_logo','footer_photo','photo_body','missing_photo','cover_hybrid'):
            plan=editorial_plan(card) if mutation in ('footer_logo','footer_photo','photo_body','missing_photo') else default_plan(card)
            if mutation=='boxed':plan['blocks'][1]['style']='boxed'
            elif mutation=='code':plan['blocks'][0]['style']='draw arbitrary code'
            elif mutation=='body_italic':plan['blocks'][0]['style']='italic_photo'
            elif mutation=='example_plain':plan['blocks'][1]['style']='plain'
            elif mutation=='plain_overlay':plan['blocks'][0]['style']='plain'
            elif mutation=='footer_logo':plan['blocks'][1]['width']=952
            elif mutation=='footer_photo':plan['blocks'][1]['y']=plan['photo_window']['y']+40
            elif mutation=='photo_body':plan['photo_window']['y']=plan['blocks'][0]['y']+40
            elif mutation=='missing_photo':plan['photo_window']=None
            else:plan['photo_window']={'y':500,'height':400,'fit':'cover'}
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):measured_plan(card,plan)
        quiz=reviewed_fixture()['cards'][0];plan=default_plan(quiz);plan['design']='editorial'
        with self.assertRaises(ValueError):measured_plan(quiz,plan)

    def test_editorial_reference_shows_style_choice_in_fourth_column_and_model_catalogue(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,colour in [('photo','red'),('hybrid','blue'),('editorial','green')]:Image.new('RGB',(1080,1350),colour).save(root/(name+'.jpg'))
            composition_sheet(root/'photo.jpg',root/'hybrid.jpg',root/'sheet.jpg',root/'editorial.jpg')
            with Image.open(root/'sheet.jpg') as sheet:
                self.assertEqual(sheet.size,(2880,900));self.assertNotEqual(sheet.getpixel((1800,450)),sheet.getpixel((2520,450)))
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(self.decision())) as child:
            review_compositions(reviewed_fixture(),self.candidates())
        prompt=child.call_args.args[0]
        for expected in ('editorial','outlined','italic_photo','italic_footer','measurements_by_style','x880'):
            self.assertIn(expected,prompt)

    def test_editorial_default_does_not_clip_long_copy_to_force_design(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['body']='Čuvamo svako slovo. '*100
        with self.assertRaises(ValueError):editorial_plan(card)

    def test_legacy_planning_metadata_does_not_affect_final_images_or_unboxed_examples(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#728192').save(photo)
            baseline=render_hybrid(card,'blue-ice',photo,root/'baseline.jpg')
            for style in ('framed','poster'):
                card['design_template']=style
                result=render_hybrid(card,'blue-ice',photo,root/'legacy.jpg')
                self.assertEqual(result,baseline)
                self.assertEqual((root/'legacy.jpg').read_bytes(),(root/'baseline.jpg').read_bytes())
            for design in ('hybrid','editorial'):
                plan=default_plan(card) if design=='hybrid' else editorial_plan(card)
                with patch('easybosnian.hybrid.draw_rows',wraps=__import__('easybosnian.render',fromlist=['draw_rows']).draw_rows) as drawing:
                    result=render_hybrid(card,'blue-ice',photo,root/'final.jpg',plan)
                call=next(c for c in drawing.call_args_list if ' '.join(c.args[2])==card['example'])
                self.assertTrue(str(call.args[3].path).endswith('Lora-Italic.ttf'))
                self.assertNotIn(result['example_bounds'],result['panel_bounds'])
            from easybosnian.designs import EXAMPLE_STYLES
            self.assertEqual(EXAMPLE_STYLES,('italic_photo','italic_photo_fade','italic_footer'))

    def test_licensed_serif_has_true_italic_and_complete_bosnian_glyphs(self):
        for italic in (False,True):
            face=serif(36,italic);rows=__import__('easybosnian.render',fromlist=['wrap']).wrap('Čć Šš Žž Đđ',face,900)
            self.assertEqual(' '.join(rows),'Čć Šš Žž Đđ')
            self.assertEqual(face.getname()[0],'Lora')
        self.assertIn('SIL OPEN FONT LICENSE',(ROOT/'assets/fonts/Lora-LICENSE.txt').read_text())

    def test_default_quizzes_fit_two_three_four_choices_and_all_shared_palettes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#798e95').save(photo)
            for count in (2,3,4):
                card=copy.deepcopy(reviewed_fixture()['cards'][0])
                card['question']='Koji odgovor je tačan?'
                card['options']=[{'label':letter,'text':text} for letter,text in zip('ABCD',['Da','Ne','Možda','Nikada'])][:count]
                for palette in read_json(ROOT/'data/design-palettes.json'):
                    result=render_hybrid(card,palette,photo,root/'quiz.jpg')
                    self.assertEqual(len(result['panel_bounds']),count)
                    self.assertLessEqual(result['panel_bounds'][-1][3],1170)
                    self.assertGreaterEqual(result['body_contrast'],4.5)

    def test_example_fade_cannot_wash_the_adjacent_explanation_panel(self):
        from easybosnian.render import draw_rows
        card=copy.deepcopy(reviewed_fixture()['cards'][2]);card['example']='Ovo je primjer.'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(1080,1350),'#fff3e4').save(photo)
            result=render_hybrid(card,'terracotta-sand',photo,root/'card.jpg')
            box=result['panel_bounds'][0]
            with Image.open(root/'card.jpg') as image:
                # Far from text/accent/JPEG boundaries: paper remains its exact colour.
                pixel=image.getpixel((box[2]-40,box[3]-20))
                self.assertTrue(all(abs(a-b)<=2 for a,b in zip(pixel,(255,243,228))))

    def test_image_cli_uses_stripped_environment_contract_and_read_only_sandbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'build').mkdir();image=root/'build/photo.jpg'
            Image.new('RGB',(20,20)).save(image)
            credential=root/'auth.json';credential.write_text(auth())
            seen=[]
            def execute(args,**kwargs):
                if args[0]=='codex':
                    seen.append((args,kwargs))
                    (root/'build/cloud-agent-last.secret').write_text(json.dumps(self.decision()))
                return subprocess.CompletedProcess(args,0,stdout='')
            with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.auth_file',return_value=credential),patch('easybosnian.cloud_prepare.verify_repository'),patch('easybosnian.cloud_prepare.subprocess.run',side_effect=execute),patch.dict(os.environ,{'GH_TOKEN':'private','INSTAGRAM_ACCESS_TOKEN':'private','OPENAI_API_KEY':'private'}):
                run_codex('Inspect the picture',result_contract=RESULT_SCHEMA,images=[image],read_only=True)
            args,options=seen[0]
            self.assertEqual(args[args.index('--sandbox')+1],'read-only')
            self.assertEqual(args[args.index('--image')+1],str(image.resolve()))
            self.assertIn('web_search="disabled"',args)
            self.assertFalse(any(k in options['env'] for k in ('GH_TOKEN','INSTAGRAM_ACCESS_TOKEN','OPENAI_API_KEY')))
            self.assertEqual(read_json(root/'build/cloud-agent-result-schema.json'),RESULT_SCHEMA)
            self.assertEqual((root/'build/cloud-agent-events.secret').stat().st_mode&0o777,0o600)

    def test_failed_or_timed_out_child_cannot_bypass_tracked_file_check(self):
        for timed_out in (False,True):
            with self.subTest(timed_out=timed_out),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);credential=root/'auth.json';credential.write_text(auth())
                def execute(args,**kwargs):
                    if args[0]=='codex':
                        if timed_out:raise subprocess.TimeoutExpired(args,1)
                        return subprocess.CompletedProcess(args,1)
                    return subprocess.CompletedProcess(args,0,stdout='src/easybosnian/render.py')
                with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.auth_file',return_value=credential),patch('easybosnian.cloud_prepare.verify_repository'),patch('easybosnian.cloud_prepare.subprocess.run',side_effect=execute):
                    with self.assertRaises(AgentIntegrityError):run_codex('Inspect',read_only=True)


class PreparedArtworkTests(unittest.TestCase):
    def test_prepare_then_expose_generates_once_and_reuses_exact_safe_hybrid_artwork(self):
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue();store=MagicMock()
        decisions={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='terracotta-sand') for c in package['cards']}}
        decisions['cards']['lesson']['blocks'][0]['style']='outlined'
        # Bad word geometry must fall back alone without a model/generation retry.
        decisions['cards']['word']['blocks'][0]['y']=200
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.artwork.ROOT',Path(temp)),patch('easybosnian.artwork.provider',return_value=provider),patch('easybosnian.visual_placement.review_compositions',return_value=(decisions,'reviewed')) as review,patch('easybosnian.artwork.wait_for_image') as visible,patch.dict(os.environ,{'GITHUB_RUN_URL':'https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/123'}):
            prepared=artwork(store,package,review_images=True)
            before={kind:item['path'].read_bytes() for kind,item in prepared.items()}
            self.assertEqual(store.put_file.call_count,3);store.expose.assert_not_called()
            result=artwork(store,package,expose=True,require_prepared=True)
            self.assertEqual(provider.generate.call_count,3);review.assert_called_once()
            self.assertEqual(store.put_file.call_count,3);self.assertEqual(store.expose.call_count,3);self.assertEqual(visible.call_count,3)
            for kind,item in result.items():self.assertEqual(item['path'].read_bytes(),before[kind])
            self.assertEqual(result['lesson']['metrics']['panel_position'],'free')
            self.assertEqual(result['lesson']['metrics']['block_styles']['body'],'outlined')
            self.assertEqual(result['word']['metrics']['panel_position'],'normal')
            self.assertEqual(result['lesson']['metrics']['palette'],'terracotta-sand')
            self.assertEqual(result['word']['metrics']['palette'],package['design_palette'])
            self.assertEqual(artwork_palette(package,result,'lesson'),read_json(ROOT/'data/design-palettes.json')['terracotta-sand'])
            safe=read_json(Path(temp)/'build'/package['batch_id']/'image-placement-result.json')
            self.assertEqual(safe['cards']['lesson']['block_styles']['body'],'outlined')
            self.assertEqual(safe['cards']['word']['block_styles']['body'],'rounded')
            self.assertIn('rejected',safe['cards']['word']['status']);self.assertNotIn('private_review',str(safe))
            self.assertEqual((Path(temp)/'build'/package['batch_id']/'prepared-artwork.secret').stat().st_mode&0o777,0o600)
            store.expose.reset_mock()
            for mismatch in ('input','run','file'):
                bad=copy.deepcopy(package)
                if mismatch=='input':bad['cards'][1]['body']+=' Danas.'
                elif mismatch=='run':os.environ['GITHUB_RUN_URL']='different-run'
                else:result['word']['path'].unlink()
                with self.subTest(mismatch=mismatch),self.assertRaises(SafeError):artwork(store,bad,expose=True,require_prepared=True)
                store.expose.assert_not_called()
                os.environ['GITHUB_RUN_URL']='https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/123'
            self.assertEqual(provider.generate.call_count,3)

    def test_verify_cannot_render_and_daily_kill_switch_blocks_private_artwork(self):
        with patch.dict(os.environ,{'MODE':'verify'}),patch('easybosnian.artwork.artwork') as generate:
            with self.assertRaises(ValueError):main()
            generate.assert_not_called()
        with patch.dict(os.environ,{'MODE':'daily'}),patch('easybosnian.core.verify_repository'),patch('easybosnian.core.require_publishing',side_effect=ValueError('disabled')),patch('easybosnian.notify.failure',return_value='test-only'),patch('easybosnian.artwork.artwork') as generate:
            with self.assertRaises(RuntimeError):main()
            generate.assert_not_called()

    def test_workflow_reviews_before_persist_and_reuses_only_prepared_artwork(self):
        workflow=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['run']['steps'];ids=[s.get('id') for s in steps]
        self.assertLess(ids.index('preparation'),ids.index('artwork'));self.assertLess(ids.index('artwork'),ids.index('persist'));self.assertLess(ids.index('persist'),ids.index('publication'))
        visual=next(s for s in steps if s.get('id')=='artwork');self.assertIn("inputs.mode != 'verify'",visual['if'])
        self.assertIn('EASYBOSNIAN_CODEX_DIR',visual['env'])
        publication=next(s for s in steps if s.get('id')=='publication');self.assertEqual(publication['env']['EASYBOSNIAN_PREPARED_ARTWORK'],'true')
        self.assertIn('always()',next(s for s in steps if s.get('id')=='persist')['if'])


if __name__=='__main__':unittest.main()
