"""Independent custom photo retention, exact provenance and fresh copy."""
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
from easybosnian.selection import selection_context,check_selection,reused_kinds,word_levels
from easybosnian.photo_reuse import prepare_photos,seal_photos,loaded_photos
from easybosnian.artwork import artwork
from easybosnian.hybrid import default_plan
from easybosnian.cloud_prepare import cloud_run
from easybosnian.http import SafeError
from test_photo_reuse import A,B,SOURCE,photo,fresh
from test_project import reviewed_fixture


class CustomSameImageTests(unittest.TestCase):
    def setUp(self):
        self.old=reviewed_fixture();self.old.update(batch_id=A,bosnian_level='A2')
        self.history={'project':PROJECT,'days':[{'date':self.old['date'],'batch_id':A,'content':self.old}]}

    def selected(self,actions=None,theme=''):
        return selection_context(self.history,self.old['date'],'custom',theme,['']*3,
                                 actions or ['keep_today','keep_today','same_image'],source_batch_id=A)

    def candidate(self):
        package=fresh(self.old)
        for card in package['cards']:
            if card['kind']!='word':card['background_prompt']+=' Fresh natural light.'
        return package

    def store(self):
        store=MagicMock();store.history.return_value=self.history;store.publications_for_date.return_value=[]
        def read(method,path):
            kind=path.rsplit('/',1)[-1]
            return {'image':base64.b64encode(photo()).decode(),'source':self.old.get('background_sources',{}).get(kind,SOURCE),
                    'prompt':next(c['background_prompt'] for c in self.old['cards'] if c['kind']==kind)}
        store.call.side_effect=read
        return store

    def test_each_role_can_keep_its_word_photo_and_level_while_other_actions_are_independent(self):
        for index,kind in enumerate(('quiz','lesson','word')):
            actions=['chatgpt']*3;actions[index]='same_image';choice=self.selected(actions)
            self.assertEqual(reused_kinds(choice),(kind,))
            self.assertEqual(choice['requested_words'][index],self.old['words'][index]['lemma'])
            self.assertEqual(choice['pinned_words'][index],self.old['words'][index])
        choice=self.selected();package=self.candidate();check_selection(package,choice)
        self.assertEqual(word_levels(package,choice,'B2'),['A2']*3)
        changed=self.selected(['same_image','keep_today','chatgpt'],'Druga tema')
        self.assertEqual(changed['word_actions'],['same_image','chatgpt','chatgpt'])
        self.assertEqual(changed['requested_words'][0],self.old['words'][0]['lemma'])
        for words,history in ((['','',''],{'days':[]}),(['','','x'],self.history)):
            with self.assertRaises(ValueError):selection_context(history,self.old['date'],'custom','Tema',words,
                                                                  ['chatgpt','chatgpt','same_image'])

    def test_selected_word_and_prompt_are_frozen_but_copy_must_be_new(self):
        choice=self.selected();valid=self.candidate();check_selection(valid,choice)
        for change in ('word','prompt','old_copy','other_prompt','replacement'):
            bad=copy.deepcopy(valid)
            if change=='word':bad['words'][2]['lemma']='drugo'
            elif change=='prompt':bad['cards'][2]['background_prompt']+=' Different photo.'
            elif change=='old_copy':bad['cards'][2]['body']=self.old['cards'][2]['body']
            elif change=='other_prompt':bad['cards'][0]['background_prompt']=self.old['cards'][0]['background_prompt']
            else:
                bad['words'][2]['lemma']='drugo'
                bad['private_review']['word_replacements']=[{'word_index':2,'requested_word':self.old['words'][2]['lemma'],
                    'chosen_word':'drugo','cause':'theme_mismatch','reason':'A reviewed theme mismatch cannot replace a frozen photograph word.'}]
            with self.subTest(change=change),self.assertRaises(ValueError):check_selection(bad,choice)

    def test_partial_fetch_and_seal_read_only_selected_files_and_refuse_expiry_or_tampering(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.photo_reuse.ROOT',Path(temp)),patch.dict(os.environ,{'GITHUB_RUN_URL':'run'}):
            store=self.store();prepared=prepare_photos(store,self.old,A,B,self.old['date'],kinds=('word',))
            self.assertEqual(store.call.call_count,1);self.assertTrue(store.call.call_args.args[1].endswith('/word'))
            metadata=seal_photos(prepared,metadata=True)
            self.assertEqual(metadata,{'background_sources':{'word':SOURCE}})
            package=dict(self.candidate(),batch_id=B,**metadata)
            self.assertEqual(set(loaded_photos(package)),{'word'})
            wrong=copy.deepcopy(package);wrong['background_sources']['word']['artwork_id']='r-'+'9'*32
            with self.assertRaises(ValueError):loaded_photos(wrong)
            prepared['paths']['word'].write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Research changed'):seal_photos(prepared,metadata=True)
            store.call.side_effect=SafeError('expired',http_status=404)
            with self.assertRaisesRegex(ValueError,'No FLUX request'):
                prepare_photos(store,self.old,A,B,self.old['date'],kinds=('word',))

    def test_later_full_reuse_accepts_a_mixed_source_batch_without_guessing(self):
        second={'batch_id':B,'artwork_id':'r-'+'2'*32}
        self.old.update(background_source=SOURCE,background_sources={'word':second})
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.photo_reuse.ROOT',Path(temp)):
            prepared=prepare_photos(self.store(),self.old,A,B,self.old['date'])
            metadata=seal_photos(prepared,metadata=True)
            self.assertEqual(metadata['background_sources'],{'quiz':SOURCE,'lesson':SOURCE,'word':second})
            self.assertEqual(len(loaded_photos(dict(self.candidate(),batch_id=B,**metadata))),3)

    def test_mixed_artwork_generates_only_other_cards_and_records_both_source_types(self):
        package=dict(self.candidate(),batch_id=B,background_sources={'word':SOURCE})
        proposal={'cards':{c['kind']:dict(default_plan(c),confidence='high',palette='forest-cream') for c in package['cards']}}
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);saved=root/'word.jpg';saved.write_bytes(photo())
            stack.enter_context(patch('easybosnian.artwork.ROOT',root))
            provider=MagicMock();provider.generate.return_value=photo()
            stack.enter_context(patch('easybosnian.artwork.provider',return_value=provider))
            review=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)))
            stack.enter_context(patch('easybosnian.visual_history.recent_choices',return_value=([],'available')))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            store=MagicMock();assets=artwork(store,package,review_images=True,reused_backgrounds={'word':saved})
            self.assertEqual(provider.generate.call_count,2)
            self.assertEqual([call.args[2] for call in provider.generate.call_args_list],['quiz','lesson'])
            self.assertEqual(package['background_sources'],{'word':SOURCE})
            self.assertEqual(package['background_source']['batch_id'],B)
            self.assertNotEqual(package['background_source'],SOURCE)
            review.assert_called_once();store.expose.assert_not_called();store.save_content.assert_not_called()
            self.assertEqual(len(assets),3)
            manifest=read_json(root/'build'/B/'prepared-artwork.secret')
            self.assertEqual(manifest['input']['background_sources'],{'word':SOURCE})
            self.assertEqual(saved.read_bytes(),photo())

    def test_cloud_custom_attaches_only_retained_card_and_keeps_batch_target_semantics(self):
        for target in ('latest','none','all_today'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(prompt,**kwargs):
                    self.assertEqual(len(kwargs['images']),1)
                    self.assertEqual(kwargs['images'][0].name,'word-photo.jpg')
                    context=read_json(root/'build/preparation-context.json')
                    self.assertEqual(context['reused_photo_kinds'],['word'])
                    self.assertEqual(context['selection']['quiz_option_target'],3)
                    package=self.candidate();package['date']=context['batch_date'];package['batch_id']=context['batch']['batch_id']
                    write_json(root/f'build/preparation/{package["date"]}.json',package)
                    return '{"status":"ready","reason":"none"}'
                for module in ('cloud_prepare','photo_reuse','cli'):
                    stack.enter_context(patch('easybosnian.'+module+'.ROOT',root))
                stack.enter_context(patch('easybosnian.cloud_prepare.Store',return_value=self.store()))
                stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value='2026-10-03'))
                stack.enter_context(patch('easybosnian.cloud_prepare.load_level',return_value='A2'))
                draw=stack.enter_context(patch('easybosnian.cloud_prepare.secrets.choice',return_value=3))
                child=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
                for name in ('check_infrastructure','require_publishing','validate','fit_check','prepare'):
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
                with contextlib.redirect_stdout(io.StringIO()):
                    result=cloud_run('daily','custom',custom_actions=['keep_today','keep_today','same_image'],batch_target=target)
                staged=read_json(root/'build/reviewed-content.secret')['content']
                self.assertEqual(staged['background_sources'],{'word':SOURCE})
                self.assertEqual(staged['date'],self.old['date'] if target=='latest' else '2026-10-03')
                self.assertEqual(staged['batch_id']==A,target=='latest')
                draw.assert_called_once_with((2,3,4));child.assert_called_once()


if __name__=='__main__':unittest.main()
