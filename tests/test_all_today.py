import copy
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from easybosnian.batches import plan_batch
from easybosnian.cli import prepare, prepared_batch
from easybosnian.cloud_prepare import cloud_run
from easybosnian.core import PROJECT, ROOT, read_json, write_json
from easybosnian.daily import daily
from easybosnian.replacement import cleanup, cleanup_day
from easybosnian.store import Store
from test_multiple_batches import A, B, C, record

D='b-'+'d'*32


class AllTodayTests(unittest.TestCase):
    def setUp(self):
        self.date='2026-10-04'
        self.history={'project':PROJECT,'days':[
            record(A,'2026-10-03','2026-10-04T01:10:00Z',3),
            record(B,self.date,'2026-10-04T01:00:00Z',1),
            record(C,self.date,'2026-10-04T01:01:00Z',2)]}
        self.package=copy.deepcopy(self.history['days'][1]['content']);self.package['batch_id']=D

    def test_plan_freezes_all_today_including_metadata_and_orphan_ids(self):
        before=copy.deepcopy(self.history)
        self.history['days'].append({'batch_id':'legacy-2026-10-04','date':self.date,'content':{'date':self.date}})
        plan=plan_batch(self.history,self.date,'all_today',publication_batch_ids=[B,D])
        self.assertEqual(plan['source_batch_id'],C)  # Prefer today's source even if yesterday was created later.
        self.assertEqual(plan['date'],self.date);self.assertIsNone(plan['cleanup_batch_id'])
        self.assertNotIn(plan['batch_id'],[A,B,C,D]);self.assertNotIn(A,plan['cleanup_batch_ids'])
        self.assertEqual(plan['cleanup_batch_ids'],sorted([B,C,D,'legacy-2026-10-04']))
        self.assertEqual(plan['prune_history_ids'],sorted([B,C,'legacy-2026-10-04']))
        self.assertEqual(self.history['days'][:3],before['days'])

    def test_after_midnight_empty_today_is_an_addition_never_yesterday_cleanup(self):
        history={'days':[self.history['days'][0]]}
        plan=plan_batch(history,self.date,'all_today')
        self.assertEqual(plan['source_batch_id'],A);self.assertEqual(plan['date'],self.date)
        self.assertNotEqual(plan['batch_id'],A)
        self.assertEqual(plan['cleanup_batch_ids'],[]);self.assertEqual(plan['prune_history_ids'],[])
        # Automatic scheduling continues to add independently, without any cleanup scope.
        automatic=plan_batch(self.history,self.date,'none')
        self.assertIsNone(automatic['cleanup_batch_id']);self.assertNotIn('prune_history_ids',automatic)
        self.assertEqual(automatic['date'],self.date)

    def test_trusted_result_rejects_changed_date_new_batch_deletion_and_scope_injection(self):
        result={'project':PROJECT,'date':self.date,'run_date':self.date,'batch_id':D,'mode':'daily',
                'status':'reviewed content staged privately','batch_target':'all_today',
                'cleanup_batch_id':None,'cleanup_batch_ids':[B,C],'prune_history_ids':[B,C]}
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.ROOT',Path(temp)),patch('easybosnian.cli.today',return_value=self.date):
            path=Path(temp)/'build/preparation-result.json';write_json(path,result)
            date,id,replace,scope=prepared_batch('daily',details=True)
            self.assertEqual((date,id,replace),(self.date,D,False));self.assertTrue(scope['cleanup_all'])
            for change in ({'run_date':'2026-10-03'},{'cleanup_batch_ids':[D]},
                           {'prune_history_ids':[A]},{'cleanup_batch_ids':[B,B]},
                           {'batch_target':'none'},{'cleanup_batch_ids':['../outside']}):
                write_json(path,{**result,**change})
                with self.subTest(change=change),self.assertRaises(ValueError):prepared_batch('daily',details=True)

    def test_save_refuses_changed_current_date_scope_before_history_write(self):
        plan=plan_batch(self.history,self.date,'all_today');package=copy.deepcopy(self.package);package['batch_id']=plan['batch_id']
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.verify_repository'),patch('easybosnian.cli.Store') as factory:
            store=factory.return_value;store.history.return_value=self.history;store.publications_for_date.return_value=[{'batch_id':A}]
            path=Path(temp)/'draft.json';write_json(path,package)
            with self.assertRaisesRegex(ValueError,'cleanup scope'):
                prepare(path,batch_target='all_today',run_date=self.date,plan=plan)
            store.save_content.assert_not_called()

    def test_all_four_preparation_choices_carry_frozen_scope_and_never_delete(self):
        for choice in ('new','same_theme','same_words','custom'):
            with self.subTest(choice=choice),tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                store=MagicMock();store.history.return_value=self.history;store.publications_for_date.return_value=[{'batch_id':D}]
                def agent(prompt):
                    context=read_json(root/'build/preparation-context.json');plan=context['batch']
                    self.assertEqual(plan['source_batch_id'],C);self.assertEqual(plan['prune_history_ids'],[B,C])
                    self.assertEqual(context['history'],self.history)
                    p=copy.deepcopy(self.package);p['batch_id']=plan['batch_id']
                    p['caption']+=' Novi izazov.'
                    for card in p['cards']:
                        card['background_prompt']+=' Fresh natural light.'
                        card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
                    p['cards'][0]['quiz_format']=context['selection']['quiz_format_target']
                    write_json(root/'build/preparation/2026-10-04.json',p)
                    return '{"status":"ready","reason":"none"}'
                stack.enter_context(patch('easybosnian.cloud_prepare.ROOT',root))
                stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value=self.date))
                for name in ('require_publishing','check_infrastructure','check_selection','validate','fit_check','failure'):
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
                stack.enter_context(patch('easybosnian.cloud_prepare.Store',return_value=store))
                saved=stack.enter_context(patch('easybosnian.cloud_prepare.prepare'))
                stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
                result=cloud_run('daily',choice,batch_target='all_today')
                self.assertEqual(result['cleanup_batch_ids'],[B,C,D]);self.assertEqual(result['prune_history_ids'],[B,C])
                self.assertEqual(saved.call_args.kwargs['plan']['cleanup_batch_ids'],[B,C,D])
                store.delete_content.assert_not_called();store.forget.assert_not_called()

    def run_daily(self,mode='daily',render_error=False,prune_error=False):
        store=MagicMock();store.content.return_value=self.package
        sequence=[]
        def render(*a,**k):
            sequence.append('render')
            if render_error:raise ValueError('fit failed')
            return {}
        def prune(*a):
            sequence.append('erase '+a[0])
            if prune_error:raise ValueError('storage failed')
            return {'removed':True}
        store.delete_content.side_effect=prune
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'true','FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'true'},clear=True),ExitStack() as stack:
            for name in ('verify_repository','write_json'):
                stack.enter_context(patch('easybosnian.daily.'+name))
            stack.enter_context(patch('easybosnian.daily.Store',return_value=store))
            stack.enter_context(patch('easybosnian.daily.artwork',side_effect=render))
            def clean(s,ids,date,platform):
                sequence.append('cleanup '+platform);self.assertEqual(ids,[B,C]);self.assertEqual(date,self.date)
                return {'status':'failed; old content may remain','removed':0},[ValueError('delete failed')]
            cleanup_mock=stack.enter_context(patch('easybosnian.daily.cleanup_day',side_effect=clean))
            publishers={}
            for name in ('publish_instagram','publish_facebook','publish_tiktok'):
                publishers[name]=stack.enter_context(patch('easybosnian.daily.'+name,side_effect=lambda *a,**k:sequence.append('publish') or {'published':True}))
            notice=stack.enter_context(patch('easybosnian.daily.failure',return_value='safe warning'))
            if render_error:
                with self.assertRaises(RuntimeError):daily(self.date,mode,batch_id=D,cleanup_all=True,cleanup_batch_ids=[B,C],prune_history_ids=[B,C])
            else:daily(self.date,mode,batch_id=D,cleanup_all=True,cleanup_batch_ids=[B,C],prune_history_ids=[B,C])
        return store,sequence,cleanup_mock,publishers,notice

    def test_preview_and_render_failure_never_erase_history_delete_or_publish(self):
        for mode,fail in [('preview',False),('daily',True)]:
            with self.subTest(mode=mode):
                store,sequence,clean,publishers,notice=self.run_daily(mode,render_error=fail)
                self.assertEqual(sequence,['render']);store.delete_content.assert_not_called();clean.assert_not_called()
                for fn in publishers.values():fn.assert_not_called()

    def test_render_precedes_history_removal_and_cleanup_errors_never_block_publish(self):
        for prune_error in (False,True):
            with self.subTest(prune_error=prune_error):
                store,sequence,clean,publishers,notice=self.run_daily(prune_error=prune_error)
                self.assertEqual(sequence[:5],['render','cleanup instagram','publish','erase '+B,'erase '+C])
                store.save_content.assert_called_once_with(self.package,preserve_artwork=True)
                self.assertEqual(store.delete_content.call_args_list[0].args,(B,self.date))
                self.assertEqual(clean.call_count,3)
                for fn in publishers.values():fn.assert_called_once()
                self.assertEqual(notice.call_count,5 if prune_error else 3)

    def test_kill_switch_blocks_all_today_before_storage_or_removal(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':'false'},clear=True),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.failure',return_value='disabled'):
            with self.assertRaises(RuntimeError):daily(self.date,'daily',batch_id=D,cleanup_all=True,cleanup_batch_ids=[B],prune_history_ids=[B])
            store.assert_not_called()

    def test_all_known_cleanup_removes_all_supported_ids_only_from_requested_batch_and_date(self):
        for platform in ('instagram','facebook'):
            items=[{'date':self.date,'batch_id':B,'platform':platform,'kind':kind,'object_id':id,'account_id':'42','recorded_order':n} for n,(kind,id) in enumerate([('feed','123'),('story','456'),('feed','789'),('story','888'),('photo','999')],1)]
            store=MagicMock();store.publications.return_value=items;provider=MagicMock();provider.user_id=provider.page_id='42';provider.owned_ids.return_value={x['object_id'] for x in items}
            provider.delete.side_effect=provider.owned_ids.return_value.discard
            with patch.dict(os.environ,{'INSTAGRAM_USER_ID':'42'}),patch('easybosnian.replacement.require_publishing'),patch('easybosnian.replacement.'+('InstagramDeletion' if platform=='instagram' else 'Facebook'),return_value=provider):
                result=cleanup(store,B,platform,all_known=True,expected_date=self.date)
                self.assertEqual(result['removed'],4 if platform=='instagram' else 2)
                self.assertNotIn('999',[c.args[0] for c in provider.delete.call_args_list])
                if platform=='facebook':self.assertEqual(provider.owned_ids.call_args_list[0].args,('feed',))
                for change in ({'date':'2026-10-03'},{'batch_id':A}):
                    store.publications.return_value=[{**items[0],**change}];provider.reset_mock()
                    with self.assertRaises(ValueError):cleanup(store,B,platform,all_known=True,expected_date=self.date)
                    provider.delete.assert_not_called()

    def test_cleanup_continues_to_other_batches_without_retry_and_tiktok_is_untouched(self):
        store=MagicMock()
        with patch('easybosnian.replacement.cleanup',side_effect=[ValueError('permission'),{'removed':1,'already_absent':2}]) as remove:
            result,errors=cleanup_day(store,[B,C],self.date,'instagram')
            self.assertEqual(remove.call_count,2);self.assertEqual(result['removed'],1);self.assertEqual(len(errors),1)
            self.assertEqual(remove.call_args.kwargs,{'all_known':True,'expected_date':self.date})
            remove.reset_mock();result,errors=cleanup_day(store,[B,C],self.date,'tiktok')
            remove.assert_not_called();self.assertEqual(errors,[]);self.assertIn('manual',result['status'])
            store.publications.assert_not_called();store.forget.assert_not_called()

    def test_store_date_scope_is_authenticated_project_bound_and_explicit(self):
        item={'date':self.date,'batch_id':B}
        with patch.dict(os.environ,{'EASYBOSNIAN_WORKER_URL':'https://example.test','EASYBOSNIAN_ADMIN_TOKEN':'private'}),patch('easybosnian.store.request') as send:
            send.return_value={'project':PROJECT,'date':self.date,'items':[item]}
            store=Store();self.assertEqual(store.publications_for_date(self.date),[item])
            self.assertEqual(send.call_args.args[1],'https://example.test/v1/publications/dates/'+self.date)
            self.assertEqual(send.call_args.args[3]['Authorization'],'Bearer private')
            for response in ({'project':'other','date':self.date,'items':[item]},
                             {'project':PROJECT,'date':self.date,'items':[{**item,'date':'2026-10-03'}]}):
                send.return_value=response
                with self.assertRaises(ValueError):store.publications_for_date(self.date)
            store.delete_content(B,self.date)
            self.assertEqual(send.call_args.args[:3],('DELETE','https://example.test/v1/history/batches/'+B,{'date':self.date}))
            with self.assertRaises(ValueError):store.delete_content(self.date,self.date)

    def test_form_has_three_targets_and_clock_dispatch_is_unchanged(self):
        self.assertIn('options: [latest, none, all_today]',(ROOT/'.github/workflows/preparation.yml').read_text())
        worker=(ROOT/'cloudflare/worker.mjs').read_text()
        self.assertIn("batch_target:'none'",worker)
        self.assertIn("f.hour!=='05'",worker);self.assertIn("f.minute!=='00'",worker)
