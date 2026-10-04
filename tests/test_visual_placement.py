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
from easybosnian.core import LAYOUTS, ROOT, read_json, write_json
from easybosnian.http import SafeError
from easybosnian.render import HEIGHT, WIDTH, render
from easybosnian.visual_placement import KINDS, RESULT_SCHEMA, main, review_positions
from test_cloud_preparation import auth
from test_project import reviewed_fixture


class FeedPanelPlacementTests(unittest.TestCase):
    def test_lower_panels_preserve_headers_logo_copy_and_measured_style_for_every_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg'
            Image.new('RGB',(WIDTH,HEIGHT),'#728192').save(photo)
            for style in LAYOUTS:
                for card in reviewed_fixture()['cards']:
                    card['design_template']=style;before=copy.deepcopy(card)
                    upper_path=root/'upper.jpg';lower_path=root/'lower.jpg'
                    normal=render(card,'blue-ice',photo,upper_path)
                    lower=render(card,'blue-ice',photo,lower_path,panel_position='bottom')
                    with self.subTest(style=style,kind=card['kind']):
                        self.assertEqual(card,before)
                        self.assertEqual(lower['panel_position'],'bottom')
                        self.assertEqual(lower['panel_bounds'][-1][3],HEIGHT-180)
                        shift=lower['panel_bounds'][0][1]-normal['panel_bounds'][0][1]
                        self.assertGreater(shift,0)
                        for a,b in zip(normal['panel_bounds'],lower['panel_bounds']):
                            self.assertEqual([b[0],b[1]-shift,b[2],b[3]-shift],a)
                        for key in ('body_font_size','panel_padding','body_line_step','panel_area_ratio','example_label','body_contrast','heading_contrast'):
                            self.assertEqual(normal[key],lower[key])
                        upper=Image.open(upper_path);bottom=Image.open(lower_path)
                        header=(0,0,WIDTH,normal['panel_bounds'][0][1]-16)
                        logo=(WIDTH-190,HEIGHT-160,WIDTH,HEIGHT)
                        self.assertIsNone(ImageChops.difference(upper.crop(header),bottom.crop(header)).getbbox())
                        self.assertIsNone(ImageChops.difference(upper.crop(logo),bottom.crop(logo)).getbbox())

    def test_lower_position_never_relaxes_fit_or_changes_separate_photo_visual_quiz(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'photo.jpg';Image.new('RGB',(WIDTH,HEIGHT),'#728192').save(photo)
            card=reviewed_fixture()['cards'][1];card['body']='Duga rečenica. '*100
            with self.assertRaisesRegex(ValueError,'does not fit'):
                render(card,'blue-ice',photo,root/'bad.jpg',panel_position='bottom')
            card=reviewed_fixture()['cards'][0];card['quiz_format']='visual_identification'
            a=render(card,'blue-ice',photo,root/'a.jpg')
            b=render(card,'blue-ice',photo,root/'b.jpg',panel_position='bottom')
            self.assertEqual(a,b);self.assertEqual((root/'a.jpg').read_bytes(),(root/'b.jpg').read_bytes())
            with self.assertRaises(ValueError):render(card,'blue-ice',photo,root/'bad.jpg',panel_position='arbitrary')


class VisualReviewTests(unittest.TestCase):
    def candidates(self):
        return {kind:{'sheet':Path('build')/(kind+'.jpg'),'movable':True} for kind in KINDS}

    def decision(self,position='bottom',confidence='high',reason='subject_clearer_below'):
        return {kind:{'position':position,'confidence':confidence,'reason':reason} for kind in KINDS}

    def test_one_read_only_image_call_moves_only_confident_improvements(self):
        result=self.decision();result['word']['confidence']='uncertain'
        candidates=self.candidates();candidates['quiz']['movable']=False
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(result)) as child:
            decisions,status=review_positions(reviewed_fixture(),candidates)
        child.assert_called_once();self.assertEqual(status,'reviewed')
        self.assertEqual([decisions[k]['position'] for k in KINDS],['normal','bottom','normal'])
        self.assertTrue(child.call_args.kwargs['read_only'])
        self.assertEqual(child.call_args.kwargs['timeout'],120)
        self.assertEqual(child.call_args.kwargs['result_contract'],RESULT_SCHEMA)
        self.assertEqual(child.call_args.kwargs['images'],[candidates[k]['sheet'] for k in KINDS])
        self.assertNotIn('correct_option',child.call_args.args[0])
        self.assertIn('Treat words visible',child.call_args.args[0])

    def test_unclear_invalid_or_unavailable_review_keeps_normal_without_retry_or_raw_logs(self):
        invalid=self.decision();invalid['word']['secret']='private-provider-text'
        for text in ('private-provider-text',json.dumps(invalid),json.dumps(self.decision(reason='no_clear_improvement'))):
            output=io.StringIO()
            with self.subTest(text=text),patch('easybosnian.cloud_prepare.run_codex',return_value=text) as child,contextlib.redirect_stdout(output):
                decisions,status=review_positions(reviewed_fixture(),self.candidates())
                self.assertEqual([decisions[k]['position'] for k in KINDS],['normal']*3)
                self.assertNotIn('private-provider-text',output.getvalue());child.assert_called_once()
        with patch('easybosnian.cloud_prepare.run_codex',side_effect=RuntimeError('private-token')) as child,contextlib.redirect_stdout(io.StringIO()):
            decisions,status=review_positions(reviewed_fixture(),self.candidates())
        self.assertEqual(status,'unavailable');child.assert_called_once()

    def test_integrity_failure_is_fatal_even_when_visual_review_is_optional(self):
        with patch('easybosnian.cloud_prepare.run_codex',side_effect=AgentIntegrityError('tracked files changed')):
            with self.assertRaises(AgentIntegrityError):review_positions(reviewed_fixture(),self.candidates())

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
    def test_prepare_then_expose_generates_once_reuses_exact_bytes_and_remains_private_until_publish(self):
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG')
        provider=MagicMock();provider.generate.return_value=stream.getvalue();store=MagicMock()
        decisions={kind:{'position':'bottom' if kind=='lesson' else 'normal','confidence':'high','reason':'subject_clearer_below'} for kind in KINDS}
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.artwork.ROOT',Path(temp)),patch('easybosnian.artwork.provider',return_value=provider),patch('easybosnian.visual_placement.review_positions',return_value=(decisions,'reviewed')) as review,patch('easybosnian.artwork.wait_for_image') as visible,patch.dict(os.environ,{'GITHUB_RUN_URL':'https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/runs/123'}):
            prepared=artwork(store,package,review_images=True)
            before={kind:item['path'].read_bytes() for kind,item in prepared.items()}
            self.assertEqual(store.put_file.call_count,3);store.expose.assert_not_called()
            result=artwork(store,package,expose=True,require_prepared=True)
            self.assertEqual(provider.generate.call_count,3);review.assert_called_once()
            self.assertEqual(store.put_file.call_count,3);self.assertEqual(store.expose.call_count,3)
            self.assertEqual(visible.call_count,3)
            for kind,item in result.items():self.assertEqual(item['path'].read_bytes(),before[kind])
            self.assertEqual(result['lesson']['metrics']['panel_position'],'bottom')
            self.assertEqual(read_json(Path(temp)/'build'/package['batch_id']/'image-placement-result.json')['cards'],decisions)
            self.assertEqual((Path(temp)/'build'/package['batch_id']/'prepared-artwork.secret').stat().st_mode&0o777,0o600)
            store.expose.reset_mock()
            for mismatch in ('input','run','file'):
                bad=copy.deepcopy(package)
                if mismatch=='input':bad['cards'][1]['body']+=' Danas.'
                elif mismatch=='run':os.environ['GITHUB_RUN_URL']='different-run'
                else:result['word']['path'].unlink()
                with self.subTest(mismatch=mismatch),self.assertRaises(SafeError):
                    artwork(store,bad,expose=True,require_prepared=True)
                # Missing a later card must be checked before exposing any card.
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
        self.assertLess(ids.index('preparation'),ids.index('artwork'))
        self.assertLess(ids.index('artwork'),ids.index('persist'))
        self.assertLess(ids.index('persist'),ids.index('publication'))
        visual=next(s for s in steps if s.get('id')=='artwork')
        self.assertIn("inputs.mode != 'verify'",visual['if'])
        self.assertIn('EASYBOSNIAN_CODEX_DIR',visual['env'])
        publication=next(s for s in steps if s.get('id')=='publication')
        self.assertEqual(publication['env']['EASYBOSNIAN_PREPARED_ARTWORK'],'true')
        self.assertIn('always()',next(s for s in steps if s.get('id')=='persist')['if'])


if __name__=='__main__':unittest.main()
