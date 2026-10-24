import copy
import os
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from easybosnian.batches import identity, latest_record, plan_batch
from easybosnian.cli import prepare, prepared_batch
from easybosnian.cloud_prepare import cloud_run
from easybosnian.core import PROJECT, ROOT, read_json, write_json
from easybosnian.daily import daily
from easybosnian.replacement import cleanup
from easybosnian.selection import selection_context, novelty_history
from easybosnian.store import Store
from easybosnian.validate import validate
from test_project import reviewed_fixture

A='b-'+'a'*32;B='b-'+'b'*32;C='b-'+'c'*32


def record(id,date,created,order=1):
    package=reviewed_fixture();package.update(batch_id=id,date=date,bosnian_level='A2')
    for word in package['words']:word['bosnian_level']='A2'
    return {'batch_id':id,'date':date,'created_at':created,'created_order':order,'content':package}


class MultipleBatchesTests(unittest.TestCase):
    def setUp(self):
        self.history={'project':PROJECT,'days':[record(A,'2026-10-03','2026-10-03T21:00:00Z'),record(B,'2026-10-04','2026-10-03T22:01:00Z',2)]}

    def test_latest_uses_creation_time_not_date_list_order_or_last_edit(self):
        later=record(C,'2026-10-03','2026-10-03T22:02:00Z',3)
        self.history['days'].insert(0,later)
        plan=plan_batch(self.history,'2026-10-04','latest')
        self.assertEqual(plan,{'batch_id':C,'date':'2026-10-03','source_batch_id':C,'cleanup_batch_id':C})
        self.history['days'][1]['content']['private_review']['reviewed_at']='2026-10-04T12:00:00Z'
        self.assertEqual(latest_record(self.history,'2026-10-04')['batch_id'],C)
        later['created_at']=self.history['days'][-1]['created_at']
        self.assertEqual(latest_record(self.history,'2026-10-04')['batch_id'],C)

    def test_none_allocates_independent_current_date_and_preserves_latest_history(self):
        before=copy.deepcopy(self.history)
        one=plan_batch(self.history,'2026-10-04','none');two=plan_batch(self.history,'2026-10-04','none')
        self.assertEqual(one['date'],'2026-10-04');self.assertEqual(one['source_batch_id'],B)
        self.assertIsNone(one['cleanup_batch_id']);self.assertNotEqual(one['batch_id'],two['batch_id'])
        self.assertEqual(self.history,before)

    def test_save_rejects_a_none_plan_that_would_overwrite_existing_content(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.verify_repository'),patch('easybosnian.cli.Store') as store:
            store.return_value.history.return_value=self.history
            path=Path(temp)/'draft.json';write_json(path,self.history['days'][1]['content'])
            plan={'batch_id':B,'date':'2026-10-04','source_batch_id':B,'cleanup_batch_id':None}
            with self.assertRaisesRegex(ValueError,'trusted independent/replacement'):
                prepare(path,batch_target='none',run_date='2026-10-04',plan=plan)
            store.return_value.save_content.assert_not_called()

    def test_imported_ids_require_one_matching_artifact_batch_not_just_a_date(self):
        import importlib.util
        import json
        spec=importlib.util.spec_from_file_location('publication_import',ROOT/'scripts/import_publication_ids.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        history=copy.deepcopy(self.history);history['days'][0]['date']='2026-10-04'
        files={'instagram-result.json':json.dumps({'batch':'2026-10-04','batch_id':B})}
        self.assertEqual(module.import_scope(files,'2026-10-04',history),B)
        with self.assertRaises(ValueError):module.import_scope(files,'2026-10-04',history,A)
        legacy={'instagram-result.json':json.dumps({'batch':'2026-10-04'})}
        with self.assertRaisesRegex(ValueError,'ambiguous'):module.import_scope(legacy,'2026-10-04',history)
        self.assertEqual(module.import_scope(legacy,'2026-10-04',history,B),B)
        files['facebook-result.json']=json.dumps({'batch':'2026-10-04','batch_id':A})
        with self.assertRaises(ValueError):module.import_scope(files,'2026-10-04',history)

    def test_intentional_reuse_works_across_kept_batches_but_new_choices_check_all_history(self):
        previous=self.history['days'][1]['content'];package=copy.deepcopy(previous);package['batch_id']=C
        package['caption']+=' Novi izazov.'
        for card in package['cards']:
            card['background_prompt']+=' New light.'
            card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
        for choice in ('same_words','custom'):
            chosen=selection_context(self.history,'2026-10-04',choice,source_batch_id=B)
            validate(package,novelty_history(self.history,package['date'],chosen,package),include_today=True)
        for choice in ('same_theme','new'):
            chosen=selection_context(self.history,package['date'],choice,source_batch_id=B)
            with self.subTest(choice=choice),self.assertRaises(ValueError):validate(package,novelty_history(self.history,package['date'],chosen),include_today=True)
        # Identity, not date, decides which stored row is self.
        with self.assertRaises(ValueError):validate(previous,self.history)

    def test_none_preparation_saves_a_new_id_for_all_four_selections_after_midnight(self):
        history={'project':PROJECT,'days':[self.history['days'][0]]}
        for choice in ('same_words','same_theme','new','custom'):
            with self.subTest(choice=choice),tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(prompt):
                    self.assertEqual(prompt.split('\n\nTrusted local context index:',1)[0],'Prepare 2026-10-04')
                    self.assertIn('max_output_tokens=10000',prompt)
                    context=read_json(root/'build/preparation-context.json')
                    self.assertEqual(context['selection']['previous'],history['days'][0]['content'])
                    package=copy.deepcopy(history['days'][0]['content']);package.update(date='2026-10-04',batch_id=context['batch']['batch_id'])
                    package['caption']+=' Novi izazov.'
                    for card in package['cards']:
                        card['background_prompt']+=' Fresh natural light.'
                        card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
                    write_json(root/'build/preparation/2026-10-04.json',package)
                    return '{"status":"ready","reason":"none"}'
                stack.enter_context(patch('easybosnian.cloud_prepare.ROOT',root))
                stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value='2026-10-04'))
                for name in ('require_publishing','check_infrastructure','validate','fit_check'):
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
                stack.enter_context(patch('easybosnian.cloud_prepare.Store')).return_value.history.return_value=history
                save=stack.enter_context(patch('easybosnian.cloud_prepare.prepare'))
                stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
                result=cloud_run('daily',choice,batch_target='none')
                self.assertNotEqual(result['batch_id'],A);self.assertIsNone(result['cleanup_batch_id'])
                self.assertEqual(save.call_args.kwargs['plan']['source_batch_id'],A)
                self.assertEqual(history['days'][0]['content']['batch_id'],A)

    def test_none_publishes_and_records_only_its_id_without_any_cleanup(self):
        package=self.history['days'][1]['content'];store=MagicMock();store.content.return_value=package
        def publish(*args,record,**kwargs):record('feed','123','42');return {'published':True,'status':'published'}
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'true'},clear=True),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store',return_value=store),patch('easybosnian.daily.artwork',return_value={}),patch('easybosnian.daily.publish_instagram',side_effect=publish),patch('easybosnian.daily.cleanup') as clean,patch('easybosnian.daily.write_json'):
            result=daily('2026-10-04','daily',batch_id=B,replace=False)
        store.content.assert_called_once_with(B);store.remember.assert_called_once_with(B,'instagram','feed','123','42')
        clean.assert_not_called();self.assertEqual(result['instagram']['replacement_cleanup']['removed'],0)
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'false'},clear=True),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.failure',return_value='disabled'):
            with self.assertRaises(RuntimeError):daily('2026-10-04','daily',batch_id=B,replace=False)
            store.assert_not_called()

    def test_cleanup_can_only_remove_returned_ids_from_the_exact_batch(self):
        store=MagicMock();ig=MagicMock();ig.user_id='42';ig.owned_ids.return_value={'123','456'}
        ig.delete.side_effect=ig.owned_ids.return_value.discard
        item={'batch_id':B,'platform':'instagram','kind':'feed','object_id':'123','account_id':'42','recorded_order':2}
        store.publications.return_value=[item]
        with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.InstagramDeletion',return_value=ig):
            cleanup(store,B,'instagram');store.publications.assert_called_once_with(B)
            ig.delete.assert_called_once_with('123');store.forget.assert_called_once_with(B,'instagram','123')
            store.publications.return_value=[{**item,'batch_id':A}];ig.reset_mock()
            with self.assertRaisesRegex(ValueError,'different batch'):cleanup(store,B,'instagram')
            ig.delete.assert_not_called()

    def test_prepared_result_controls_batch_identity_and_cleanup_independently_of_date(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.ROOT',Path(temp)),patch('easybosnian.cli.today',return_value='2026-10-04'):
            path=Path(temp)/'build/preparation-result.json'
            result={'project':PROJECT,'date':'2026-10-03','batch_id':A,'mode':'daily','status':'reviewed content staged privately','batch_target':'latest','cleanup_batch_id':A}
            write_json(path,result);self.assertEqual(prepared_batch('daily'),('2026-10-03',A,True))
            result.update(date='2026-10-04',batch_target='none',batch_id=B,cleanup_batch_id=None)
            write_json(path,result);self.assertEqual(prepared_batch('daily'),('2026-10-04',B,False))
            for change in ({'cleanup_batch_id':A},{'cleanup_batch_id':B},{'batch_id':'../../outside'}):
                write_json(path,{**result,**change})
                with self.subTest(change=change),self.assertRaises(ValueError):prepared_batch('daily')

    def test_store_uses_batch_specific_content_publication_and_artwork_paths(self):
        with patch.dict(os.environ,{'EASYBOSNIAN_WORKER_URL':'https://example.test','EASYBOSNIAN_ADMIN_TOKEN':'private'}),patch('easybosnian.store.request',return_value={'items':[],'url':'https://example.test/image'}) as send:
            store=Store();store.content(B);self.assertEqual(send.call_args.args[1],'https://example.test/v1/history/batches/'+B)
            store.publications(B);self.assertIn('/publications/batches/'+B,send.call_args.args[1])
            store.put_file(B,'quiz-card.jpg',b'bytes');self.assertIn('/private/batches/'+B,send.call_args.args[1])
            store.expose(B,'quiz-story.jpg');self.assertIn('/expose/batches/'+B,send.call_args.args[1])

    def test_migration_preserves_content_ids_order_orphans_and_daily_claims(self):
        import json
        db=sqlite3.connect(':memory:')
        db.executescript('CREATE TABLE history(date TEXT PRIMARY KEY,theme_json TEXT,words_json TEXT,content_json TEXT); CREATE TABLE preparation_dispatches(date TEXT PRIMARY KEY,status TEXT);')
        db.executescript((ROOT/'cloudflare/migrations/0004_publication_ids.sql').read_text())
        package=copy.deepcopy(self.history['days'][0]['content']);package.pop('batch_id')
        db.execute('INSERT INTO history VALUES(?,?,?,?)',(package['date'],json.dumps(package['theme']),json.dumps(package['words']),json.dumps(package)))
        for order,date,id in [(4,'2026-10-03','123'),(9,'2026-10-03','456'),(15,'2026-10-02','789')]:db.execute('INSERT INTO publication_ids(rowid,date,platform,kind,object_id,account_id) VALUES(?,?,?,?,?,?)',(order,date,'instagram','feed',id,'42'))
        db.execute("INSERT INTO preparation_dispatches VALUES('2026-10-03','accepted')")
        db.executescript((ROOT/'cloudflare/migrations/0005_multiple_batches.sql').read_text())
        restored=json.loads(db.execute('SELECT content_json FROM history').fetchone()[0]);self.assertEqual(restored.pop('batch_id'),'legacy-2026-10-03');self.assertEqual(restored,package)
        self.assertEqual(db.execute('SELECT rowid,batch_id,object_id FROM publication_ids ORDER BY rowid').fetchall(),[(4,'legacy-2026-10-03','123'),(9,'legacy-2026-10-03','456'),(15,'legacy-2026-10-02','789')])
        self.assertEqual(db.execute('SELECT * FROM preparation_dispatches').fetchall(),[('2026-10-03','accepted')])
        db.execute('INSERT INTO history SELECT ?,date,created_at,theme_json,words_json,content_json FROM history LIMIT 1',(B,))
        self.assertEqual(db.execute('SELECT COUNT(*) FROM history WHERE date=?',(package['date'],)).fetchone()[0],2)
        db.close()
