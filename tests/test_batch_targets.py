"""Midnight reruns replace the selected row; routine starts preserve yesterday."""
import copy
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from easybosnian.cli import prepare, prepared_date
from easybosnian.cloud_prepare import cloud_run
from easybosnian.core import PROJECT, read_json, write_json
from easybosnian.daily import daily
from easybosnian.validate import normalise
from easybosnian.selection import batch_date, novelty_history, selection_context
from test_project import reviewed_fixture


class BatchTargetTests(unittest.TestCase):
    def setUp(self):
        self.old=reviewed_fixture();self.old['date']='2026-10-03';self.old['bosnian_level']='A2'
        self.history={'project':PROJECT,'days':[{'date':self.old['date'],'content':self.old}]}

    def test_latest_is_date_ordered_ignores_imports_and_never_uses_future_rows(self):
        history=copy.deepcopy(self.history)
        for date in ('2026-10-05','2026-10-02'):
            package=copy.deepcopy(self.old);package['date']=date
            history['days'].insert(0,{'date':date,'content':package})
        history['days'].append({'date':'2026-10-04','content':{'schema_version':'legacy_word_history'}})
        self.assertEqual(batch_date(history,'2026-10-04'),'2026-10-03')
        self.assertEqual(batch_date(history,'2026-10-05'),'2026-10-05')
        self.assertEqual(batch_date(history,'2026-10-04','today'),'2026-10-04')
        self.assertEqual(batch_date({'days':[]},'2026-10-04'),'2026-10-04')
        history['days'][-2]['content']['date']='2026-10-01'
        with self.assertRaisesRegex(ValueError,'history row'):batch_date(history,'2026-10-04')
        with self.assertRaises(ValueError):batch_date(self.history,'2026-10-04','unknown')

    def test_all_four_daily_choices_use_the_latest_date_after_midnight(self):
        for choice in ('same_words','same_theme','new','custom'):
            with self.subTest(choice=choice),tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(prompt):
                    self.assertEqual(prompt.split('\n\nTrusted local context index:',1)[0],'Prepare 2026-10-03')
                    self.assertIn('max_output_tokens=10000',prompt)
                    package=copy.deepcopy(self.old)
                    package['caption']+=' Novi poziv.\n👉easybosnian.com'
                    for card in package['cards']:
                        card['background_prompt']+=' Fresh natural light.'
                        card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
                    write_json(root/'build/preparation/2026-10-03.json',package)
                    return '{"status":"ready","reason":"none"}'
                for name,value in [('ROOT',root),('today','2026-10-04'),('select_run_level','A2')]:
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name,return_value=value) if name!='ROOT' else patch('easybosnian.cloud_prepare.ROOT',value))
                for name in ('require_publishing','check_infrastructure','validate','fit_check'):
                    stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
                store=stack.enter_context(patch('easybosnian.cloud_prepare.Store'));store.return_value.history.return_value=self.history
                save=stack.enter_context(patch('easybosnian.cloud_prepare.prepare'))
                stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
                result=cloud_run('daily',choice)
                self.assertEqual(result['date'],'2026-10-03');self.assertEqual(result['run_date'],'2026-10-04')
                self.assertEqual(save.call_args.kwargs['batch_target'],'latest')
                self.assertEqual(save.call_args.kwargs['run_date'],'2026-10-04')
                context=read_json(root/'build/preparation-context.json')
                self.assertEqual(context['selection']['previous'],self.old)
                self.assertEqual(context['batch_date'],'2026-10-03')
                if choice=='custom':self.assertEqual(context['selection']['requested_words'],[w['lemma'] for w in self.old['words']])

    def test_routine_start_prepares_current_date_even_when_a_previous_batch_exists(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
            def agent(prompt):
                self.assertEqual(prompt.split('\n\nTrusted local context index:',1)[0],'Prepare 2026-10-04')
                self.assertIn('max_output_tokens=10000',prompt)
                package=copy.deepcopy(self.old);package['date']='2026-10-04'
                write_json(root/'build/preparation/2026-10-04.json',package)
                return '{"status":"ready","reason":"none"}'
            stack.enter_context(patch('easybosnian.cloud_prepare.ROOT',root))
            stack.enter_context(patch('easybosnian.cloud_prepare.today',return_value='2026-10-04'))
            for name in ('require_publishing','check_infrastructure','validate','fit_check','prepare'):
                stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
            store=stack.enter_context(patch('easybosnian.cloud_prepare.Store'));store.return_value.history.return_value=self.history
            stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
            result=cloud_run('daily',batch_target='today')
            self.assertEqual(result['date'],'2026-10-04')
            self.assertEqual(read_json(root/'build/preparation-context.json')['selection']['choice'],'new')
            self.assertIsNone(result['cleanup_batch_id'])

    def test_preview_reuses_latest_exactly_without_research_or_live_gate(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cloud_prepare.ROOT',Path(temp)),patch('easybosnian.cloud_prepare.today',return_value='2026-10-04'),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.validate'),patch('easybosnian.cloud_prepare.fit_check'),patch('easybosnian.cloud_prepare.run_codex') as agent,patch('easybosnian.cloud_prepare.require_publishing') as live,patch('easybosnian.cloud_prepare.prepare') as save:
            store.return_value.history.return_value=self.history
            self.assertEqual(cloud_run('preview')['date'],'2026-10-03')
            agent.assert_not_called();live.assert_not_called();save.assert_not_called()

    def test_novelty_exempts_selected_concepts_without_removing_other_dates(self):
        chosen=selection_context(self.history,'2026-10-03','same_words')
        filtered=novelty_history(self.history,'2026-10-03',chosen)
        self.assertEqual(filtered['days'],self.history['days'])
        self.assertEqual(set(filtered['reused_word_keys']),{normalise(k) for w in self.old['words'] for k in [w['lemma'],*w['equivalence_keys']]})
        other=copy.deepcopy(self.old);other['date']='2026-10-02'
        history=copy.deepcopy(self.history);history['days'].append({'date':other['date'],'content':other})
        self.assertEqual(novelty_history(history,'2026-10-03',chosen)['days'][1]['content'],other)

    def test_trusted_save_overwrites_latest_and_rejects_an_arbitrary_older_date(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.ROOT',Path(temp)),patch('easybosnian.cli.verify_repository'),patch('easybosnian.cli.today',return_value='2026-10-04'),patch('easybosnian.cli.Store') as store,patch('easybosnian.cli.validate'),patch('easybosnian.cli.fit_check'):
            path=Path(temp)/'draft.json';legacy=copy.deepcopy(self.old)
            for card in legacy['cards']:card['design_template']='framed'
            write_json(path,legacy)
            store.return_value.history.return_value=self.history
            prepare(path,batch_target='latest',run_date='2026-10-04')
            store.return_value.save_content.assert_not_called()
            from easybosnian.core import read_json
            staged=read_json(Path(temp)/'build/reviewed-content.secret')['content']
            self.assertEqual(staged['date'],'2026-10-03')
            self.assertTrue(all('design_template' not in c for c in staged['cards']))
            store.return_value.save_content.reset_mock()
            for date,target in [('2026-10-02','latest'),('2026-10-03','today')]:
                wrong=copy.deepcopy(self.old);wrong['date']=date;write_json(path,wrong)
                with self.subTest(date=date,target=target),self.assertRaises(ValueError):prepare(path,batch_target=target)
            store.return_value.save_content.assert_not_called()

    def test_publication_and_cleanup_use_prepared_date_not_current_clock(self):
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.ROOT',Path(temp)),patch('easybosnian.cli.today',return_value='2026-10-04'),patch('easybosnian.daily.ROOT',Path(temp)),patch('easybosnian.daily.today',return_value='2026-10-04'),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',return_value={}),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.cleanup',return_value={'removed':0}) as cleanup,patch('easybosnian.daily.publish_instagram',return_value={'status':'published','published':True}),patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'false','TIKTOK_POSTING_ENABLED':'false','INSTAGRAM_STORIES_ENABLED':'false'},clear=True):
            path=Path(temp)/'build/preparation-result.json'
            result={'date':'2026-10-03','mode':'daily','project':PROJECT,'status':'reviewed content staged privately'}
            write_json(path,result);store.return_value.content.return_value=self.old
            daily(prepared_date('daily'),'daily')
            store.return_value.content.assert_called_once_with('2026-10-03')
            cleanup.assert_called_once_with(store.return_value,'2026-10-03','instagram')
            for change in ({'mode':'preview'},{'project':'another-project'},{'status':'failed'},{'date':'2026-10-05'}):
                write_json(path,{**result,**change})
                with self.subTest(change=change),self.assertRaises(ValueError):prepared_date('daily')
            write_json(path,result)
            with self.assertRaises(ValueError):prepared_date('verify')
