import copy
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock,patch
from easybosnian.cli import stage_content,prepared_content
from easybosnian.core import PROJECT,write_json
from easybosnian.daily import daily
from test_project import reviewed_fixture

A='b-'+'a'*32
B='b-'+'b'*32

class PublishedHistoryTests(unittest.TestCase):
    def run_case(self,mode='daily',render_fails=False,ig=False,fb=False,story_fails=False,save_fails=False,all_today=False):
        package=reviewed_fixture();package['batch_id']=B
        store=MagicMock();events=[]
        def render(*a,**k):
            events.append('render')
            if render_fails:raise ValueError('image rejected')
            return {}
        def publish(name,confirmed):
            events.append(name)
            if not confirmed:raise RuntimeError('explicit provider rejection')
            return {'status':'published','published':True}
        def save(*a,**k):
            events.append('save')
            if save_fails:raise RuntimeError('storage unavailable')
        store.save_content.side_effect=save
        store.delete_content.side_effect=lambda *a:events.append('prune') or {'removed':True}
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'false','INSTAGRAM_STORIES_ENABLED':'true','FACEBOOK_STORIES_ENABLED':'false'},clear=True))
            for name in ('verify_repository','require_publishing','validate'):
                stack.enter_context(patch('easybosnian.daily.'+name))
            stack.enter_context(patch('easybosnian.daily.ROOT',Path(temp)))
            stack.enter_context(patch('easybosnian.daily.Store',return_value=store))
            stack.enter_context(patch('easybosnian.daily.artwork',side_effect=render))
            stack.enter_context(patch('easybosnian.daily.cleanup',return_value={'status':'removed'}))
            stack.enter_context(patch('easybosnian.daily.cleanup_day',return_value=({'status':'removed'},[])))
            stack.enter_context(patch('easybosnian.daily.publish_instagram',side_effect=lambda *a,**k:publish('ig',ig)))
            stack.enter_context(patch('easybosnian.daily.publish_facebook',side_effect=lambda *a,**k:publish('fb',fb)))
            story=stack.enter_context(patch('easybosnian.daily.publish_stories',side_effect=RuntimeError('Story failure') if story_fails else None,return_value={'published':True}))
            failure=stack.enter_context(patch('easybosnian.daily.failure',return_value='safe failure'))
            raises=mode=='daily' and (render_fails or not ig or not fb or story_fails or save_fails)
            kwargs={'cleanup_all':True,'cleanup_batch_ids':[A],'prune_history_ids':[A]} if all_today else {}
            if raises:
                with self.assertRaises(RuntimeError):daily(package['date'],mode,batch_id=B,replace=False,package=package,**kwargs)
            else:daily(package['date'],mode,batch_id=B,replace=False,package=package,**kwargs)
            store.content.assert_not_called()
        return store,events,story,failure,package

    def test_failed_generation_preview_and_no_confirmed_feed_leave_history_untouched(self):
        for options in ({'render_fails':True},{'mode':'preview'},{'all_today':True}):
            with self.subTest(options=options):
                store,events,_,_,_=self.run_case(**options)
                store.save_content.assert_not_called();store.delete_content.assert_not_called()
                if options.get('render_fails') or options.get('mode')=='preview':self.assertEqual(events,['render'])

    def test_first_confirmed_feed_saves_once_even_when_another_platform_or_story_fails(self):
        for options in ({'ig':True},{'fb':True},{'ig':True,'fb':True,'story_fails':True}):
            with self.subTest(options=options):
                store,events,_,_,package=self.run_case(**options)
                store.save_content.assert_called_once_with(package,preserve_artwork=True)
                self.assertGreater(events.index('save'),events.index('ig' if options.get('ig') else 'fb'))
                if options.get('ig'):self.assertLess(events.index('save'),events.index('fb'))

    def test_all_today_prunes_only_after_confirmed_feed_and_successful_history_save(self):
        store,events,_,_,_=self.run_case(ig=True,fb=True,all_today=True)
        self.assertEqual(events,['render','ig','save','prune','fb'])
        store.delete_content.assert_called_once_with(A,'2026-10-02')
        store,events,_,failure,_=self.run_case(ig=True,fb=True,all_today=True,save_fails=True)
        store.save_content.assert_called_once();store.delete_content.assert_not_called()
        self.assertEqual(events,['render','ig','save','fb']);failure.assert_called_once()

    def test_staged_input_is_private_run_scoped_and_independent_of_history(self):
        package=reviewed_fixture();package['batch_id']=B
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.ROOT',Path(temp)),patch('easybosnian.cli.today',return_value='2026-10-02'),patch('easybosnian.cli.validate'),patch.dict(os.environ,{'GITHUB_RUN_URL':'https://example.test/run'}):
            result={'project':PROJECT,'mode':'daily','date':package['date'],'batch_id':B,'status':'reviewed content staged privately','batch_target':'none','cleanup_batch_id':None}
            write_json(Path(temp)/'build/preparation-result.json',result);stage_content(package)
            self.assertEqual((Path(temp)/'build/reviewed-content.secret').stat().st_mode & 0o777,0o600)
            self.assertEqual(prepared_content('daily'),package)
            for mutation in ('run','batch','date'):
                changed=copy.deepcopy(package)
                if mutation=='run':os.environ['GITHUB_RUN_URL']='https://example.test/other'
                if mutation=='batch':changed['batch_id']=A
                if mutation=='date':changed['date']='2026-10-01'
                if mutation!='run':stage_content(changed)
                with self.assertRaises(ValueError):prepared_content('daily')
                os.environ['GITHUB_RUN_URL']='https://example.test/run'
