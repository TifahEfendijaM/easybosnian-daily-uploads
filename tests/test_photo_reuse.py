from test_project import accepted_photo_review
import base64
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from PIL import Image
from easybosnian.core import PROJECT,read_json,write_json
from easybosnian.selection import selection_context,check_selection,novelty_history,word_levels
from easybosnian.photo_reuse import prepare_photos,seal_photos,loaded_photos
from easybosnian.artwork import artwork
from easybosnian.hybrid import default_plan
from easybosnian.cloud_prepare import cloud_run
from easybosnian.http import SafeError
from test_project import reviewed_fixture

A='b-'+'a'*32
B='b-'+'b'*32
SOURCE={'batch_id':A,'artwork_id':'r-'+'1'*32}


def photo():
    stream=io.BytesIO();Image.new('RGB',(1024,1024),'#728192').save(stream,'JPEG');return stream.getvalue()


def fresh(previous):
    package=copy.deepcopy(previous);package['caption']+=' Danas.'
    package.pop('background_source',None)
    for card in package['cards']:card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
    return package


class PhotoReuseTests(unittest.TestCase):
    def setUp(self):
        self.old=reviewed_fixture();self.old.update(batch_id=A,bosnian_level='A2')
        self.history={'project':PROJECT,'days':[{'date':self.old['date'],'batch_id':A,'content':self.old}]}

    def store(self):
        store=MagicMock()
        store.call.side_effect=lambda method,path:{'image':base64.b64encode(photo()).decode(),'source':SOURCE,'prompt':next(c['background_prompt'] for c in self.old['cards'] if path.endswith('/'+c['kind']))}
        return store

    def test_same_images_keeps_theme_words_prompts_but_requires_fresh_copy(self):
        selection=selection_context(self.history,self.old['date'],'same_images',source_batch_id=A)
        package=fresh(self.old);check_selection(package,selection)
        self.assertEqual(word_levels(package,selection,'B2'),['A2']*3)
        self.assertTrue(novelty_history(self.history,package['date'],selection,package)['reused_word_keys'])
        for change in ('caption','text','prompt','word'):
            bad=copy.deepcopy(package)
            if change=='caption':bad['caption']=self.old['caption']
            if change=='text':bad['cards'][1]['body']=self.old['cards'][1]['body']
            if change=='prompt':bad['cards'][0]['background_prompt']+=' Changed scene.'
            if change=='word':bad['words'][0]['lemma']='drugo'
            with self.subTest(change=change),self.assertRaises(ValueError):check_selection(bad,selection)
        with self.assertRaises(ValueError):selection_context({'days':[]},package['date'],'same_images')

    def test_saved_photos_are_checked_before_research_and_bound_to_run(self):
        store=self.store()
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.photo_reuse.ROOT',Path(temp)),patch.dict(os.environ,{'GITHUB_RUN_URL':'run-one'}):
            prepared=prepare_photos(store,self.old,A,B,self.old['date']);source=seal_photos(prepared)
            package=fresh(self.old);package.update(batch_id=B,background_source=source)
            paths=loaded_photos(package)
            self.assertEqual(set(paths),{'quiz','lesson','word'})
            self.assertEqual(paths['quiz'].read_bytes(),photo())
            self.assertEqual(paths['quiz'].stat().st_mode & 0o777,0o600)
            self.assertTrue(all(c.args[0]=='GET' for c in store.call.call_args_list))
            with patch.dict(os.environ,{'GITHUB_RUN_URL':'another-run'}),self.assertRaises(ValueError):loaded_photos(package)
            prepared['paths']['quiz'].write_bytes(b'changed by child')
            with self.assertRaisesRegex(ValueError,'Research changed'):seal_photos(prepared)
        store.call.side_effect=SafeError('expired',http_status=404)
        with self.assertRaisesRegex(ValueError,'No FLUX request'):prepare_photos(store,self.old,A,B,self.old['date'])
        store.save_content.assert_not_called();store.expose.assert_not_called()

    def test_reused_photos_still_get_new_review_rendering_without_inference(self):
        package=fresh(self.old);package.update(batch_id=B,background_source=SOURCE)
        proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='terracotta-sand') for c in package['cards']}}
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);paths={}
            for kind in ('quiz','lesson','word'):
                paths[kind]=root/(kind+'.jpg');paths[kind].write_bytes(photo())
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            stack.enter_context(patch('easybosnian.photo_quality.inspect_photos',side_effect=accepted_photo_review))
            provider=stack.enter_context(patch('easybosnian.artwork.provider'))
            review=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            store=MagicMock();assets=artwork(store,package,review_images=True,reused_backgrounds=paths)
            provider.assert_not_called();review.assert_called_once();store.expose.assert_not_called()
            self.assertEqual(len(assets),3)
            with Image.open(assets['quiz']['background_path']) as rendered: self.assertEqual(rendered.size,(1024,1024))
            manifest=read_json(root/'build'/B/'prepared-artwork.secret')
            self.assertEqual(manifest['input']['background_source'],SOURCE)
            self.assertEqual(read_json(root/'build'/B/'image-placement-result.json')['recent_design_runs'],0)

    def test_cloud_reuse_sees_originals_and_keeps_after_midnight_latest_identity(self):
        from easybosnian.core import ROOT as REAL_ROOT
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
            store=self.store();store.history.return_value=self.history
            def agent(prompt,**kwargs):
                self.assertEqual(len(kwargs['images']),3)
                self.assertTrue(all(Path(p).read_bytes()==photo() for p in kwargs['images']))
                package=fresh(self.old)
                package['cards'][0]['quiz_format']=read_json(root/'build/preparation-context.json')['selection']['quiz_format_target']
                write_json(root/f'build/preparation/{self.old["date"]}.json',package)
                return '{"status":"ready","reason":"none"}'
            for module in ('cloud_prepare','photo_reuse','cli'):
                stack.enter_context(patch('easybosnian.'+module+'.ROOT',root))
            stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value='2026-10-03'))
            stack.enter_context(patch('easybosnian.cloud_prepare.Store',return_value=store))
            stack.enter_context(patch('easybosnian.cloud_prepare.select_run_level',return_value='A2'))
            stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
            for name in ('check_infrastructure','require_publishing','validate','fit_check','prepare'):
                stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
            result=cloud_run('daily','same_images')
            self.assertEqual(result['date'],self.old['date']);self.assertEqual(result['batch_id'],A)
            staged=read_json(root/'build/reviewed-content.secret')['content']
            self.assertEqual(staged['background_source'],SOURCE)
            self.assertEqual(staged['words'],self.old['words'])
            store.save_content.assert_not_called()


if __name__=='__main__':unittest.main()
