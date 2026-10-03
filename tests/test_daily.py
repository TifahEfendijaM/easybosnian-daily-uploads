import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from easybosnian.core import ROOT,require_publishing
from easybosnian.daily import daily
from easybosnian.pipeline import publish_instagram
from easybosnian.facebook import publish_facebook,verify_post
from easybosnian.buffer import Buffer,publish_tiktok,checked_post
from easybosnian.stories import publish_stories,story_image
from test_project import reviewed_fixture
from PIL import Image


class ModeTests(unittest.TestCase):
    def setUp(self):
        guard=patch('easybosnian.notify.gh',return_value='test-only')
        guard.start();self.addCleanup(guard.stop)

    @patch.dict(os.environ,{'GITHUB_ACTIONS':'false'})
    def test_kill_switch_is_read_for_every_live_attempt_and_fails_closed(self):
        with patch('easybosnian.core.gh',return_value='false') as get:
            with self.assertRaises(ValueError):require_publishing()
            self.assertIn('DAILY_POSTING_ENABLED',get.call_args.args)
        with patch('easybosnian.core.gh',return_value='true'):require_publishing()
        with patch('easybosnian.core.gh',side_effect=RuntimeError('denied')):
            with self.assertRaises(RuntimeError):require_publishing()

    def test_each_publisher_honours_kill_switch_before_provider_call(self):
        package=reviewed_fixture()
        for module,function in [('pipeline',lambda:publish_instagram(package,{})),('facebook',lambda:publish_facebook(package,{})),('buffer',lambda:publish_tiktok(package,{})),('stories',lambda:publish_stories(None,package,{}))]:
            with self.subTest(module=module),patch(f'easybosnian.{module}.require_publishing',side_effect=ValueError('disabled')),patch(f'easybosnian.{module}.write_json'),patch(f'easybosnian.{module}.failure',return_value='disabled'),patch(f'easybosnian.{module}.'+('Buffer' if module=='buffer' else 'Facebook' if module=='facebook' else 'Instagram')) as provider:
                with self.assertRaises(RuntimeError):function()
                provider.assert_not_called()

    def test_verify_never_reads_content_renders_or_publishes(self):
        with patch('easybosnian.readiness.check_infrastructure',return_value={'publication':'nothing published'}) as check,patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.artwork') as art,patch('easybosnian.daily.require_publishing') as kill:
            daily(mode='verify');check.assert_called_once();store.assert_not_called();art.assert_not_called();kill.assert_not_called()

    def test_preview_renders_without_exposing_or_posting_and_ignores_kill_switch(self):
        with patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',return_value={}) as art,patch('easybosnian.daily.require_publishing') as live,patch('easybosnian.daily.publish_instagram') as instagram,patch('easybosnian.daily.write_json'):
            store.return_value.content.return_value=reviewed_fixture()
            result=daily('2026-10-02','preview')
            self.assertFalse(result['published']);self.assertFalse(art.call_args.kwargs['expose'])
            live.assert_not_called();instagram.assert_not_called()

    def test_platform_failure_still_attempts_other_enabled_platforms(self):
        with patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'true','TIKTOK_POSTING_ENABLED':'true','INSTAGRAM_STORIES_ENABLED':'true'}),patch('easybosnian.daily.verify_repository'),patch('easybosnian.daily.require_publishing'),patch('easybosnian.daily.Store') as store,patch('easybosnian.daily.validate'),patch('easybosnian.daily.artwork',return_value={}),patch('easybosnian.daily.write_json'),patch('easybosnian.daily.publish_instagram',side_effect=RuntimeError('failed')),patch('easybosnian.daily.publish_facebook',return_value={'published':True}) as facebook,patch('easybosnian.daily.publish_tiktok',return_value={'published':True}) as tiktok,patch('easybosnian.daily.publish_stories') as stories:
            store.return_value.content.return_value=reviewed_fixture()
            with self.assertRaises(RuntimeError):daily('2026-10-02','daily')
            facebook.assert_called_once();tiktok.assert_called_once();stories.assert_not_called()

    def test_story_padding_preserves_dimensions_text_area_and_full_card(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'card.jpg';output=Path(directory)/'story.jpg'
            Image.new('RGB',(1080,1350),'#345678').save(source)
            story_image(source,output,{'panel':'#ffffff'})
            with Image.open(output) as story:
                self.assertEqual(story.size,(1080,1920))
                self.assertEqual(story.getpixel((10,10)),(255,255,255))
                self.assertLess(sum(abs(a-b) for a,b in zip(story.getpixel((500,600)),(52,86,120))),8)

    def test_workflow_has_one_job_three_modes_and_no_output_or_reusable_plumbing(self):
        text=(ROOT/'.github/workflows/preparation.yml').read_text()
        import re
        jobs=text.split('jobs:\n',1)[1]
        self.assertEqual(re.findall(r'^  (\w+):$',jobs,re.M),['run'])
        self.assertIn('options: [verify, preview, daily]',text)
        self.assertNotIn('outputs:',text);self.assertNotIn('workflow_call:',text)
        self.assertFalse((ROOT/'.github/workflows/daily.yml').exists())

    def test_instagram_repeated_invocations_publish_again_without_a_state_gate(self):
        package=reviewed_fixture();assets={c['kind']:{'url':c['kind']} for c in package['cards']}
        from unittest.mock import MagicMock
        ig=MagicMock();ig.publish.return_value='new-post'
        ig.media.return_value={'id':'new-post','caption':package['caption']+'\n\n'+' '.join(package['hashtags']),'media_type':'CAROUSEL_ALBUM','children':{'data':[{'media_type':'IMAGE'}]*3},'permalink':'https://www.instagram.com/p/new/'}
        with patch('easybosnian.pipeline.require_publishing'),patch('easybosnian.pipeline.Instagram',return_value=ig),patch('easybosnian.pipeline.write_json'):
            for _ in range(2):self.assertTrue(publish_instagram(package,assets)['published'])
            self.assertEqual(ig.publish.call_count,2)

    def test_facebook_checks_page_caption_and_ordered_photo_ids(self):
        package=reviewed_fixture()
        from unittest.mock import MagicMock
        fb=MagicMock();fb.page_id='page'
        actual={'id':'post','from':{'id':'page'},'message':package['caption']+'\n\n'+' '.join(package['hashtags']),'is_published':True,'permalink_url':'https://www.facebook.com/page/posts/post','attachments':{'data':[{'subattachments':{'data':[{'type':'photo','target':{'id':x}} for x in ['1','2','3']]}}]}}
        fb.post.return_value=actual;self.assertTrue(verify_post(fb,package,'post',['1','2','3']))
        for mutate in [lambda x:x['from'].update(id='wrong'),lambda x:x.update(message='wrong'),lambda x:x['attachments']['data'][0]['subattachments']['data'].reverse()]:
            wrong=copy.deepcopy(actual);mutate(wrong);fb.post.return_value=wrong
            with self.assertRaises(ValueError):verify_post(fb,package,'post',['1','2','3'])

    def test_buffer_checks_rehosted_bytes_in_order_and_actual_tiktok_permalink(self):
        package=reviewed_fixture()
        from easybosnian.buffer import caption
        from unittest.mock import MagicMock
        buffer=MagicMock();buffer.channel_id='channel'
        with tempfile.TemporaryDirectory() as directory:
            assets={}
            for i,c in enumerate(package['cards']):
                path=Path(directory)/c['kind'];path.write_bytes(bytes([i+1])*100)
                assets[c['kind']]={'path':path}
            actual={'id':'post','channelId':'channel','channelService':'tiktok','text':caption(package),'schedulingType':'automatic','status':'sent','sentAt':'2026-10-03','externalLink':'https://www.tiktok.com/@easy.bosnian/photo/123','assets':[{'mimeType':'image/jpeg','source':str(i)} for i in range(3)]}
            with patch('easybosnian.buffer.request',side_effect=lambda method,url,**k:bytes([int(url)+1])*100):
                self.assertTrue(checked_post(buffer,package,'post',actual,assets))
                wrong=copy.deepcopy(actual);wrong['assets'].reverse()
                with self.assertRaises(ValueError):checked_post(buffer,package,'post',wrong,assets)
                wrong=copy.deepcopy(actual);wrong['externalLink']='https://tiktok.com/@someone/video/123'
                with self.assertRaises(ValueError):checked_post(buffer,package,'post',wrong,assets)
                waiting=copy.deepcopy(actual);waiting['status']='sending'
                self.assertIsNone(checked_post(buffer,package,'post',waiting,assets))

    def test_fresh_daily_content_checks_current_date_but_publishing_can_read_it(self):
        from easybosnian.validate import validate
        package=reviewed_fixture();history={'days':[{'date':package['date'],'content':package}]}
        validate(package,history)
        with self.assertRaises(ValueError):validate(package,history,include_today=True)

    def test_actions_uses_actual_repository_variable_passed_to_job_and_missing_fails_closed(self):
        for value,allowed in [('false',False),('true',True),('',False)]:
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','DAILY_POSTING_ENABLED':value}),patch('easybosnian.core.gh') as query:
                if allowed:require_publishing()
                else:
                    with self.assertRaises(ValueError):require_publishing()
                query.assert_not_called()
