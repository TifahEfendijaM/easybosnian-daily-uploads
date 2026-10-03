import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from easybosnian.core import ROOT, PROJECT, REPO
from easybosnian.daily import daily
from easybosnian.facebook_stories import publish_facebook_stories, verify_story
from easybosnian.meta import Facebook
from easybosnian.readiness import check_infrastructure
from test_project import reviewed_fixture


def story(post_id='201', photo_id='101'):
    return {'post_id': post_id, 'media_id': photo_id, 'status': 'PUBLISHED',
            'media_type': 'photo', 'url': 'https://www.facebook.com/stories/'+post_id}


class FacebookStoryTests(unittest.TestCase):
    def setUp(self):
        guard=patch('easybosnian.notify.gh',return_value='test-only')
        guard.start();self.addCleanup(guard.stop)
        cleanup=patch('easybosnian.daily.cleanup',return_value={'removed':0,'already_absent':0})
        cleanup.start();self.addCleanup(cleanup.stop)

    def test_meta_upload_and_story_contract_uses_fresh_unpublished_photo(self):
        with patch.dict(os.environ, {'META_GRAPH_VERSION': 'v26.0'}):
            facebook = Facebook(token='test-only-token', page_id='1284422991426579')
        facebook.call = MagicMock(side_effect=[{'id': '101'}, {'success': True, 'post_id': 201}])
        photo_id = facebook.photo('https://images.example/card.jpg', 'Pitanje dana s tri mogućnosti.')
        self.assertEqual(facebook.story(photo_id), '201')
        self.assertEqual(facebook.call.call_args_list[0].args[2]['published'], 'false')
        self.assertEqual(facebook.call.call_args_list[1].args,
                         ('POST', facebook.page_id+'/photo_stories', {'photo_id': '101'}))
        for response in ({'success': False, 'post_id': '201'}, {'success': True}, {'success': True, 'post_id': 'invalid'}):
            facebook.call.return_value = response; facebook.call.side_effect = None
            with self.subTest(response=response), self.assertRaises(ValueError): facebook.story('101')

    def test_readback_requires_matching_current_photo_story_and_actual_url(self):
        facebook = MagicMock(); actual = story()
        facebook.stories.return_value = {'data': [actual]}
        self.assertEqual(verify_story(facebook, '201', '101'), actual['url'])
        for change in ({'media_id': 'wrong'}, {'media_type': 'video'}, {'status': 'ARCHIVED'},
                       {'url': 'https://elsewhere.example/stories/201'}, {'url': 'https://facebook.com/feed/201'}):
            wrong = {**actual, **change}; facebook.stories.return_value = {'data': [wrong]}
            with self.subTest(change=change), self.assertRaises(ValueError): verify_story(facebook, '201', '101')
        facebook.stories.return_value = {'data': [story('202')]}
        with patch('easybosnian.facebook_stories.time.sleep'), self.assertRaises(ValueError):
            verify_story(facebook, '201', '101')

    def test_readback_uses_cursors_and_bounded_polling_without_a_second_publish(self):
        facebook = MagicMock()
        facebook.stories.side_effect = [
            {'data': [], 'paging': {'next': 'https://untrusted.example/next', 'cursors': {'after': 'opaque-cursor'}}},
            {'data': [story()]},
        ]
        verify_story(facebook, '201', '101')
        self.assertEqual([call.args for call in facebook.stories.call_args_list], [(None,), ('opaque-cursor',)])
        facebook.story.assert_not_called()
        facebook.stories.reset_mock(); facebook.stories.side_effect = None; facebook.stories.return_value = {'data': []}
        with patch('easybosnian.facebook_stories.time.sleep') as sleep, self.assertRaises(ValueError):
            verify_story(facebook, '201', '101')
        self.assertEqual(facebook.stories.call_count, 6); self.assertEqual(sleep.call_count, 5)

    def test_publishing_preserves_three_cards_order_and_records_partial_failure(self):
        package = reviewed_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'data').mkdir(); (root/'data/design-palettes.json').write_bytes((ROOT/'data/design-palettes.json').read_bytes())
            build = root/'build'/package['date']; build.mkdir(parents=True); assets = {}
            for card in package['cards']:
                path = build/(card['kind']+'-card.jpg'); Image.new('RGB', (1080, 1350), '#648699').save(path)
                assets[card['kind']] = {'path': path}
            facebook = MagicMock(); facebook.photo.side_effect = ['101', '102', '103']; facebook.story.side_effect = ['201', '202', '203']
            facebook.stories.return_value = {'data': [story(str(201+i), str(101+i)) for i in range(3)]}
            store = MagicMock(); store.expose.side_effect = lambda date,name: 'https://images.example/'+name
            with patch.dict(os.environ, {'FACEBOOK_POSTING_ENABLED': 'true', 'FACEBOOK_STORIES_ENABLED': 'true'}), \
                 patch('easybosnian.facebook_stories.ROOT', root), patch('easybosnian.facebook_stories.require_publishing') as kill, \
                 patch('easybosnian.facebook_stories.Facebook', return_value=facebook), \
                 patch('easybosnian.facebook_stories.request', side_effect=lambda method,url,**kwargs: (build/url.rsplit('/',1)[-1]).read_bytes()), \
                 patch('easybosnian.facebook_stories.failure', return_value='safe failure'):
                result = publish_facebook_stories(store, package, assets)
                self.assertTrue(result['published']); facebook.verify_page.assert_called_once()
                self.assertEqual([x['slide'] for x in result['stories']], ['quiz', 'lesson', 'word'])
                self.assertEqual([call.args[0] for call in facebook.story.call_args_list], ['101', '102', '103'])
                self.assertEqual([call.args[1] for call in facebook.photo.call_args_list], [c['alt_text'] for c in package['cards']])
                for card in package['cards']:
                    with Image.open(build/(card['kind']+'-story.jpg')) as image: self.assertEqual(image.size, (1080, 1920))
                facebook.photo.reset_mock(); facebook.story.reset_mock(); facebook.photo.side_effect = ['101', '102', '103']; facebook.story.side_effect = ['201', '202', '203']
                kill.side_effect = [None, None, None, ValueError('disabled')]
                with self.assertRaises(RuntimeError): publish_facebook_stories(store, package, assets)
                partial = json.loads((build/'facebook-stories-result.json').read_text())
                self.assertFalse(partial['published']); self.assertEqual(len(partial['stories']), 1)
                self.assertEqual(facebook.story.call_count, 1)
                self.assertEqual(partial['failed_stage'], 'Facebook Stories photo upload')

    def test_disabled_publisher_never_contacts_facebook(self):
        for flags in ({'FACEBOOK_POSTING_ENABLED': 'true', 'FACEBOOK_STORIES_ENABLED': 'false'},
                      {'FACEBOOK_POSTING_ENABLED': 'false', 'FACEBOOK_STORIES_ENABLED': 'true'}):
            with patch.dict(os.environ, flags), patch('easybosnian.facebook_stories.require_publishing'), \
                 patch('easybosnian.facebook_stories.Facebook') as facebook, patch('easybosnian.facebook_stories.write_json'), \
                 patch('easybosnian.facebook_stories.failure', return_value='disabled'), self.assertRaises(RuntimeError):
                publish_facebook_stories(None, reviewed_fixture(), {})
            facebook.assert_not_called()
        with patch('easybosnian.facebook_stories.require_publishing', side_effect=ValueError('disabled')), \
             patch('easybosnian.facebook_stories.Facebook') as facebook, patch('easybosnian.facebook_stories.write_json'), \
             patch('easybosnian.facebook_stories.failure', return_value='disabled'), self.assertRaises(RuntimeError):
            publish_facebook_stories(None, reviewed_fixture(), {})
        facebook.assert_not_called()

    def test_live_lowercase_published_status_is_confirmed_and_lowercase_archived_rejected(self):
        facebook=MagicMock()
        for status in ('published','PUBLISHED'):
            facebook.stories.return_value={'data':[{**story(),'status':status}]}
            self.assertEqual(verify_story(facebook,'201','101'),'https://www.facebook.com/stories/201')
        facebook.stories.return_value={'data':[{**story(),'status':'archived'}]}
        with self.assertRaisesRegex(ValueError,'archived'):verify_story(facebook,'201','101')

    def test_facebook_stories_run_even_when_instagram_or_its_stories_fail(self):
        for instagram_fails in (True, False):
            with patch.dict(os.environ, {'FACEBOOK_POSTING_ENABLED': 'true', 'FACEBOOK_STORIES_ENABLED': 'true', 'TIKTOK_POSTING_ENABLED': 'true', 'INSTAGRAM_STORIES_ENABLED': 'true'}), \
                 patch('easybosnian.daily.verify_repository'), patch('easybosnian.daily.require_publishing'), \
                 patch('easybosnian.daily.Store') as store, patch('easybosnian.daily.validate'), \
                 patch('easybosnian.daily.artwork', return_value={}), patch('easybosnian.daily.write_json'), \
                 patch('easybosnian.daily.publish_instagram', side_effect=RuntimeError('failed') if instagram_fails else None, return_value={'published': True}), \
                 patch('easybosnian.daily.publish_facebook', return_value={'published': True}), \
                 patch('easybosnian.daily.publish_tiktok', return_value={'published': True}), \
                 patch('easybosnian.daily.publish_stories', side_effect=RuntimeError('failed')), \
                 patch('easybosnian.daily.publish_facebook_stories', return_value={'published': True}) as facebook_stories:
                store.return_value.content.return_value = reviewed_fixture()
                with self.assertRaises(RuntimeError): daily('2026-10-02', 'daily')
                facebook_stories.assert_called_once()

    def test_preview_and_failed_facebook_feed_never_publish_facebook_stories(self):
        for mode in ('preview', 'daily'):
            with patch.dict(os.environ, {'FACEBOOK_POSTING_ENABLED': 'true', 'FACEBOOK_STORIES_ENABLED': 'true', 'TIKTOK_POSTING_ENABLED': 'false', 'INSTAGRAM_STORIES_ENABLED': 'false'}), \
                 patch('easybosnian.daily.verify_repository'), patch('easybosnian.daily.require_publishing'), \
                 patch('easybosnian.daily.Store') as store, patch('easybosnian.daily.validate'), \
                 patch('easybosnian.daily.artwork', return_value={}), patch('easybosnian.daily.write_json'), \
                 patch('easybosnian.daily.publish_instagram', return_value={'published': True}), \
                 patch('easybosnian.daily.publish_facebook', side_effect=RuntimeError('failed')), \
                 patch('easybosnian.daily.publish_facebook_stories') as facebook_stories:
                store.return_value.content.return_value = reviewed_fixture()
                if mode == 'daily':
                    with self.assertRaises(RuntimeError): daily('2026-10-02', mode)
                else: daily('2026-10-02', mode)
                facebook_stories.assert_not_called()

    def test_readiness_checks_story_access_without_a_publish_request(self):
        env = {name:'test-only' for name in ('EASYBOSNIAN_WORKER_URL', 'EASYBOSNIAN_ADMIN_TOKEN', 'INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_USER_ID', 'META_GRAPH_VERSION', 'GH_SECRETS_TOKEN', 'FACEBOOK_PAGE_TOKEN', 'FACEBOOK_PAGE_ID')}
        env.update(INSTAGRAM_TOKEN_ISSUED_AT=datetime.now(timezone.utc).isoformat(), INSTAGRAM_STORIES_ENABLED='false', FACEBOOK_POSTING_ENABLED='true', FACEBOOK_STORIES_ENABLED='true', TIKTOK_POSTING_ENABLED='false')
        with patch.dict(os.environ, env), patch('easybosnian.readiness.verify_repository'), patch('easybosnian.readiness.publishing_enabled', return_value=True), \
             patch('easybosnian.readiness.Store') as store, patch('easybosnian.readiness.Instagram') as instagram, \
             patch('easybosnian.readiness.Facebook') as facebook, patch('easybosnian.readiness.request', return_value={'full_name': REPO, 'private': True}):
            store.return_value.call.return_value={'project': PROJECT}; store.return_value.history.return_value={'project': PROJECT}
            instagram.return_value.verify_account.return_value={'username': 'easy_bosnian', 'account_type': 'BUSINESS'}
            facebook.return_value.stories.return_value={'data': []}
            result=check_infrastructure(); self.assertIn('read access verified', result['facebook_stories'])
            facebook.return_value.story.assert_not_called(); facebook.return_value.photo.assert_not_called()
            facebook.return_value.stories.return_value={}
            with self.assertRaises(ValueError):check_infrastructure()
