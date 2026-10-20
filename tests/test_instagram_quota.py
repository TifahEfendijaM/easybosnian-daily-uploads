"""Live quota guards, explicit Meta refusals and privacy without another publish."""
import json
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from easybosnian.core import ROOT
from easybosnian.http import SafeError,safe_response_error
from easybosnian.instagram_quota import publishing_quota,require_story_capacity
from easybosnian.meta import Instagram
from easybosnian.notify import next_step
from easybosnian.stories import publish_stories
from test_project import reviewed_fixture


def response(used=98,total=100,window=86400):
    return {'data':[{'quota_usage':used,'config':{'quota_total':total,'quota_duration':window}}]}


class InstagramQuotaTests(unittest.TestCase):
    def test_exact_account_endpoint_is_read_only_and_limit_is_not_hardcoded(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):ig=Instagram(token='private',user_id='42')
        ig.call=MagicMock(return_value=response(98,100))
        quota=publishing_quota(ig)
        ig.call.assert_called_once_with('GET','42/content_publishing_limit',{'fields':'quota_usage,config'})
        self.assertEqual(quota,{'status':'available','quota_usage':98,'quota_total':100,
                              'quota_duration':86400,'remaining':2,'required':3})
        with self.assertRaises(SafeError) as error:require_story_capacity(quota)
        self.assertEqual(error.exception.reason,'instagram_publishing_limit')
        self.assertNotIn('permission',next_step('Instagram Stories publishing quota',error.exception))
        ig.call.return_value=response(19,25,3600)
        quota=publishing_quota(ig);require_story_capacity(quota)
        self.assertEqual((quota['remaining'],quota['quota_duration']),(6,3600))
        ig.call.return_value=response(101,100)
        self.assertEqual(publishing_quota(ig)['remaining'],0)

    def test_unavailable_or_malformed_read_is_unknown_not_an_invented_zero_or_permission_change(self):
        ig=MagicMock()
        for value in (None,{},[],{'data':[]},{'data':[{},{}]},response(True,100),response(0,False),
                      response(-1),response(0,0),response(0,100,0),response(0,'private-token')):
            with self.subTest(value_type=type(value).__name__):
                ig.publishing_limit.return_value=value
                quota=publishing_quota(ig);require_story_capacity(quota)
                self.assertEqual(quota,{'status':'unavailable','reason':'quota_response_invalid'})
                self.assertNotIn('private',str(quota))
        ig.publishing_limit.side_effect=SafeError('private provider prose')
        self.assertEqual(publishing_quota(ig),{'status':'unavailable','reason':'quota_read_failed'})

    def test_meta_quota_is_classified_by_exact_numeric_pair_without_exposing_raw_prose(self):
        error=safe_response_error({'error':{'code':9,'error_subcode':2207042,
                                  'message':'private-token','error_user_msg':'private detail'}},400)
        self.assertEqual(error.reason,'instagram_publishing_limit')
        self.assertIn('publishing quota reached',str(error));self.assertNotIn('private',str(error))
        self.assertIn('rolling quota',next_step('Instagram Stories publishing',error))
        for code,subcode in ((9,2207027),(9007,2207027),(10,2207042),('9',2207042),(True,2207042)):
            other=safe_response_error({'error':{'code':code,'error_subcode':subcode}},400)
            self.assertIsNone(other.reason)

    def run_stories(self,quota_response=None,publish_error=None):
        package=reviewed_fixture();temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);(root/'data').mkdir()
        (root/'data/design-palettes.json').write_bytes((ROOT/'data/design-palettes.json').read_bytes())
        folder=root/'build'/package['date'];folder.mkdir(parents=True)
        assets={c['kind']:{'path':folder/'card.jpg','background_path':folder/'photo.jpg'} for c in package['cards']}
        ig=MagicMock();ig.user_id='42';ig.publishing_limit.return_value=quota_response
        ig.story.side_effect=['101','102','103'];ig.ready.return_value='FINISHED';ig.publish.side_effect=publish_error
        ig.call.return_value={'status_code':'FINISHED'}
        store=MagicMock();record=MagicMock()
        def render(source,destination,*args,**kwargs):Path(destination).write_bytes(b'reviewed JPEG bytes')
        with patch.dict(os.environ,{'INSTAGRAM_STORIES_ENABLED':'true'}),patch('easybosnian.stories.ROOT',root), \
             patch('easybosnian.stories.require_publishing'),patch('easybosnian.stories.Instagram',return_value=ig), \
             patch('easybosnian.stories.story_image',side_effect=render) as render_call, \
             patch('easybosnian.stories.verify_story',return_value='https://www.instagram.com/stories/easy_bosnian/201'), \
             patch('easybosnian.stories.wait_for_image'),patch('easybosnian.stories.failure',return_value='safe failure'), \
             self.assertRaises(SafeError) as error:
            publish_stories(store,package,assets,record=record)
        saved=json.loads((folder/'instagram-stories-result.json').read_text())
        return error.exception,saved,ig,store,record,render_call

    def test_insufficient_known_capacity_stops_before_render_upload_container_or_publish(self):
        error,result,ig,store,record,render=self.run_stories(response(98))
        self.assertEqual(error.reason,'instagram_publishing_limit')
        self.assertEqual(result['failed_stage'],'Instagram Stories publishing quota')
        self.assertEqual(result['publishing_quota']['remaining'],2)
        self.assertEqual(result['stories'],[]);self.assertEqual(result['containers'],[])
        render.assert_not_called();store.put_file.assert_not_called();store.expose.assert_not_called()
        ig.story.assert_not_called();ig.publish.assert_not_called();record.assert_not_called()

    def test_provider_refusal_after_preflight_is_still_one_attempt_and_keeps_explicit_reason(self):
        refusal=safe_response_error({'error':{'code':9,'error_subcode':2207042}},400)
        for quota in (response(0),None):
            error,result,ig,store,record,render=self.run_stories(quota,refusal)
            self.assertEqual(error.reason,'instagram_publishing_limit')
            self.assertEqual(result['failure_reason'],'instagram_publishing_limit')
            self.assertEqual(result['failed_stage'],'Instagram Stories publishing')
            self.assertIn('provider code 9; provider subcode 2207042',result['error'])
            ig.story.assert_called_once();ig.publish.assert_called_once();record.assert_not_called()
            self.assertEqual(result['containers'][-1]['status_after_failure'],'FINISHED')
            self.assertEqual(store.expose.call_count,1)

    def test_quota_refusal_preserves_earlier_confirmed_story_and_stops_the_remaining_set(self):
        refusal=safe_response_error({'error':{'code':9,'error_subcode':2207042}},400)
        error,result,ig,store,record,render=self.run_stories(response(0),['201',refusal])
        self.assertEqual(error.reason,'instagram_publishing_limit')
        self.assertEqual([s['media_id'] for s in result['stories']],['201'])
        self.assertEqual([s['container_id'] for s in result['containers']],['101','102'])
        record.assert_called_once_with('story','201','42')
        self.assertEqual(ig.publish.call_count,2);self.assertEqual(ig.story.call_count,2)
        self.assertIn('1 Instagram Stories confirmed',result['status'])

    def test_daily_summary_names_quota_without_suppressing_other_platforms_or_history(self):
        from easybosnian.daily import daily
        quota_error=SafeError('Instagram Stories incomplete: publishing quota reached',reason='instagram_publishing_limit')
        flags={'FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'true',
               'INSTAGRAM_STORIES_ENABLED':'true','FACEBOOK_STORIES_ENABLED':'true'}
        with patch.dict(os.environ,flags),patch('easybosnian.daily.verify_repository'), \
             patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.Store') as store, \
             patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',return_value={}), \
             patch('easybosnian.daily.cleanup',return_value={'removed':0}), \
             patch('easybosnian.daily.write_json') as save, \
             patch('easybosnian.daily.publish_instagram',return_value={'published':True}) as instagram, \
             patch('easybosnian.daily.publish_facebook',return_value={'published':True}) as facebook, \
             patch('easybosnian.daily.publish_tiktok',return_value={'published':True}) as tiktok, \
             patch('easybosnian.daily.publish_stories',side_effect=quota_error), \
             patch('easybosnian.daily.publish_facebook_stories',return_value={'published':True}) as facebook_stories:
            store.return_value.content.return_value=reviewed_fixture()
            with self.assertRaisesRegex(RuntimeError,'instagram_stories'):daily('2026-10-02','daily')
            outcome=save.call_args.args[1]
            self.assertTrue(outcome['history_saved']);store.return_value.save_content.assert_called_once()
            for provider in (instagram,facebook,tiktok,facebook_stories):provider.assert_called_once()
            self.assertEqual(outcome['platforms']['instagram_stories']['status'],
                             'incomplete; Instagram publishing quota reached')

    def test_verify_quota_probe_reads_both_existing_clients_without_content_or_writes(self):
        spec=importlib.util.spec_from_file_location('_quota_diagnostic',ROOT/'scripts/diagnose_publications.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        ig=MagicMock();fb=MagicMock()
        ig.publishing_limit.return_value=response(50,50);fb.publishing_limit.return_value=response(51,100)
        with patch.object(module,'verify_repository'),patch.object(module,'Store') as store, \
             patch.object(module,'Instagram',return_value=ig),patch.object(module,'InstagramFacebook',return_value=fb):
            result=module.diagnose_publishing_quota()
        store.assert_not_called()
        for client in (ig,fb):
            client.verify_account.assert_called_once();client.publishing_limit.assert_called_once()
            client.story.assert_not_called();client.publish.assert_not_called()
        self.assertEqual(result['instagram_publishing_quotas']['instagram_login']['remaining'],0)
        self.assertEqual(result['instagram_publishing_quotas']['facebook_login']['remaining'],49)


if __name__=='__main__':unittest.main()
