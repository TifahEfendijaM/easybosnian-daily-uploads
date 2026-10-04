import os
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from easybosnian.http import SafeError, provider_codes, request
from easybosnian.meta import Instagram, Facebook


class MetaReadinessTests(unittest.TestCase):
    def test_provider_diagnostics_expose_only_integer_codes(self):
        codes = provider_codes({'error': {'code': 9007, 'error_subcode': 2207027, 'message': 'private payload'}})
        self.assertIn('9007', codes); self.assertIn('2207027', codes); self.assertNotIn('private', codes)
        for payload in (None, {'error': []}, {'error': {'code': 'private-token', 'error_subcode': True}}):
            self.assertEqual(provider_codes(payload), 'provider code unavailable; provider subcode unavailable')

    def test_false_deletion_acknowledgement_is_not_success_or_retried(self):
        response = MagicMock(); response.__enter__.return_value.read.return_value = b'{"success":false}'
        with patch('easybosnian.http.urlopen', return_value=response) as call, self.assertRaisesRegex(SafeError, 'success=false'):
            request('DELETE', 'https://graph.facebook.com/v26.0/123')
        call.assert_called_once()

    def instagram(self):
        with patch.dict(os.environ, {'META_GRAPH_VERSION': 'v26.0'}):
            return Instagram(token='test', user_id='42')

    def test_story_waits_for_two_finished_reads_before_single_publish(self):
        ig = self.instagram()
        ig.call = MagicMock(side_effect=[{'status_code': 'FINISHED'}, {'status_code': 'FINISHED'}])
        with patch('easybosnian.meta.time.sleep') as sleep:
            self.assertEqual(ig.ready('123', stable=True), 'FINISHED')
        self.assertEqual(ig.call.call_count, 2)
        self.assertTrue(all(call.args[0] == 'GET' for call in ig.call.call_args_list))
        sleep.assert_called_once_with(5)

    def test_readiness_stability_resets_when_processing_resumes(self):
        ig = self.instagram()
        ig.call = MagicMock(side_effect=[{'status_code': s} for s in ('FINISHED', 'IN_PROGRESS', 'FINISHED', 'FINISHED')])
        with patch('easybosnian.meta.time.sleep'):
            self.assertEqual(ig.ready('123', stable=True), 'FINISHED')
        self.assertEqual(ig.call.call_count, 4)

    def test_expired_error_or_already_published_is_never_ready(self):
        for status in ('PUBLISHED', 'ERROR', 'EXPIRED'):
            ig = self.instagram(); ig.call = MagicMock(return_value={'status_code': status})
            with self.subTest(status=status), self.assertRaises(ValueError): ig.ready('123', stable=True)
            ig.call.assert_called_once()

    def test_still_processing_has_bounded_read_only_polling(self):
        ig = self.instagram(); ig.call = MagicMock(return_value={'status_code': 'IN_PROGRESS'})
        with patch('easybosnian.meta.time.sleep') as sleep, self.assertRaises(ValueError):
            ig.ready('123', stable=True)
        self.assertEqual(ig.call.call_count, 12)
        self.assertEqual(sleep.call_count, 11)

    def test_partial_story_failure_preserves_container_and_uses_only_one_publish_attempt(self):
        from PIL import Image
        from easybosnian.core import ROOT
        from easybosnian.stories import publish_stories
        from test_project import reviewed_fixture
        package = reviewed_fixture()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'data').mkdir()
            (root/'data/design-palettes.json').write_bytes((ROOT/'data/design-palettes.json').read_bytes())
            build = root/'build'/package['date']; build.mkdir(parents=True)
            assets = {}
            for card in package['cards']:
                path = build/(card['kind']+'-card.jpg'); Image.new('RGB', (1080,1350)).save(path)
                assets[card['kind']] = {'path': path, 'background_path': path}
            ig = MagicMock(); ig.user_id = '42'; ig.story.side_effect = ['101','102']
            ig.publish.side_effect = ['201',SafeError('HTTP 400; provider code 9007')]
            ig.ready.return_value = 'FINISHED'; ig.call.return_value = {'status_code':'FINISHED'}
            store = MagicMock(); store.expose.side_effect = lambda date,name,body: 'https://images.example/'+name
            image_reads={}
            def read_image(method,url,**kwargs):
                self.assertEqual(method,'GET');image_reads[url]=image_reads.get(url,0)+1
                if image_reads[url]==1:raise SafeError('not visible',http_status=404)
                return (build/url.rsplit('/',1)[-1]).read_bytes()
            with patch.dict(os.environ, {'INSTAGRAM_STORIES_ENABLED':'true'}), patch('easybosnian.stories.ROOT',root), patch('easybosnian.stories.Instagram',return_value=ig), patch('easybosnian.stories.require_publishing'), patch('easybosnian.stories.verify_story',return_value='https://www.instagram.com/stories/easy_bosnian/201'), patch('easybosnian.stories.request',side_effect=read_image), patch('easybosnian.store.time.sleep'), patch('easybosnian.stories.failure',return_value='safe failure'), self.assertRaises(SafeError):
                publish_stories(store,package,assets)
            result = json.loads((build/'instagram-stories-result.json').read_text())
            self.assertEqual(result['stories'][0]['media_id'],'201')
            self.assertEqual(result['containers'][-1],{'slide':'lesson','container_id':'102','ready_status':'FINISHED','status_after_failure':'FINISHED'})
            self.assertEqual(ig.publish.call_count,2)
            self.assertEqual(list(image_reads.values()),[2,2]);self.assertEqual(store.expose.call_count,2)
            for call in store.expose.call_args_list:self.assertEqual(call.args[2],(build/call.args[1]).read_bytes())
            self.assertEqual([c.kwargs for c in ig.ready.call_args_list],[{'stable':True}]*2)


if __name__ == '__main__':
    unittest.main()
