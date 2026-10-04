import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from unittest.mock import MagicMock, patch

from PIL import Image
from easybosnian.artwork import artwork
from easybosnian.http import SafeError, request
from easybosnian.store import Store, wait_for_image
from test_project import reviewed_fixture


class ImageHostingTests(unittest.TestCase):
    def test_delayed_public_visibility_only_polls_get_and_keeps_exact_bytes(self):
        fetch=MagicMock(side_effect=[SafeError('not visible',http_status=404)]*2+[b'rendered'])
        with patch('easybosnian.store.time.sleep') as sleep:
            wait_for_image('https://example.test/images/one.jpg',b'rendered',fetch)
        self.assertEqual(fetch.call_count,3)
        self.assertEqual(sleep.call_count,2)
        self.assertTrue(all(c.args[0]=='GET' and c.kwargs['raw'] for c in fetch.call_args_list))
        self.assertTrue(all(0<c.kwargs['timeout']<=10 for c in fetch.call_args_list))
        self.assertTrue(all(c.args==(5,) for c in sleep.call_args_list))

    def test_mismatch_or_auth_quota_network_failure_stops_immediately(self):
        failures=[b'different',SafeError('unauthorized',http_status=401),
                  SafeError('forbidden',http_status=403),SafeError('quota',http_status=429),
                  SafeError('service failed',http_status=503),SafeError('network outcome uncertain')]
        for result in failures:
            fetch=MagicMock(side_effect=result if isinstance(result,Exception) else None,
                            return_value=result)
            with self.subTest(result=result),patch('easybosnian.store.time.sleep') as sleep:
                with self.assertRaises(SafeError):wait_for_image('https://example.test/image.jpg',b'rendered',fetch)
                fetch.assert_called_once();sleep.assert_not_called()

    def test_visibility_wait_is_bounded_without_reuploading(self):
        clock=[0.0]
        fetch=MagicMock(side_effect=SafeError('not visible',http_status=404))
        def advance(seconds):clock[0]+=seconds
        with patch('easybosnian.store.time.monotonic',side_effect=lambda:clock[0]), \
             patch('easybosnian.store.time.sleep',side_effect=advance):
            with self.assertRaisesRegex(SafeError,'after 180 seconds') as error:
                wait_for_image('https://example.test/image.jpg',b'rendered',fetch)
        self.assertEqual(error.exception.stage,'storage');self.assertEqual(clock[0],180)
        self.assertEqual(fetch.call_count,36)
        self.assertTrue(all(c.args[0]=='GET' for c in fetch.call_args_list))

    def test_exposure_sends_renderer_bytes_once_and_accepts_only_own_random_url(self):
        origin='https://example.test';url=origin+'/images/'+'a'*64+'.jpg'
        with patch.dict(os.environ,{'EASYBOSNIAN_WORKER_URL':origin,'EASYBOSNIAN_ADMIN_TOKEN':'private'}), \
             patch('easybosnian.store.request',return_value={'url':url}) as send:
            store=Store();self.assertEqual(store.expose('b-'+'b'*32,'quiz-card.jpg',b'jpeg'),url)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[:3],('POST',origin+'/v1/expose/batches/b-'+'b'*32+'/quiz-card.jpg',b'jpeg'))
            self.assertEqual(send.call_args.args[3]['Content-Type'],'image/jpeg')
            for wrong in ('http://example.test/images/'+'a'*64+'.jpg',
                          'https://another.test/images/'+'a'*64+'.jpg',url+'?token=private',origin+'/v1/history'):
                send.return_value={'url':wrong}
                with self.subTest(url=wrong),self.assertRaisesRegex(SafeError,'unexpected public image URL'):
                    store.expose('b-'+'b'*32,'quiz-card.jpg',b'jpeg')

    def test_http_retains_numeric_status_and_only_allowlisted_storage_details(self):
        for reason,expected in [('asset_not_visible','not visible in KV yet'),
                                ('asset_write_failed','private image storage failed'),
                                ('private-token-in-untrusted-reason','inspect provider permissions/status')]:
            payload={'error':'private-token-in-provider-prose','stage':'storage','reason':reason}
            error=HTTPError('https://example.test',409,'untrusted',{},io.BytesIO(json.dumps(payload).encode()))
            with self.subTest(reason=reason),patch('easybosnian.http.urlopen',side_effect=error):
                with self.assertRaisesRegex(SafeError,expected) as result:request('POST','https://example.test')
            self.assertEqual(result.exception.http_status,409);self.assertEqual(result.exception.stage,'storage')
            self.assertNotIn('private-token',str(result.exception))
        with patch('easybosnian.http.urlopen',side_effect=URLError('private-token')):
            with self.assertRaises(SafeError) as result:request('GET','https://example.test')
        self.assertIsNone(result.exception.http_status)

    def test_three_card_generation_and_writes_are_not_repeated_while_visibility_lags(self):
        package=reviewed_fixture();package['batch_id']='b-'+'b'*32
        image=io.BytesIO();Image.new('RGB',(1024,1024),'#647880').save(image,'JPEG')
        generator=MagicMock();generator.generate.return_value=image.getvalue()
        origin='https://example.test';mutations=[];bodies={};reads={}
        def mutation(method,url,body=None,headers=None,**kwargs):
            mutations.append((method,url,body))
            if method=='PUT':return {'stored':True}
            name=url.rsplit('/',1)[-1];index=['quiz-card.jpg','lesson-card.jpg','word-card.jpg'].index(name)+1
            public=origin+'/images/'+str(index)*64+'.jpg';bodies[public]=body
            return {'url':public}
        def fetch(method,url,**kwargs):
            self.assertEqual(method,'GET');reads[url]=reads.get(url,0)+1
            if reads[url]==1:raise SafeError('not visible',http_status=404)
            return bodies[url]
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'EASYBOSNIAN_WORKER_URL':origin,'EASYBOSNIAN_ADMIN_TOKEN':'private'}), \
             patch('easybosnian.artwork.ROOT',Path(temp)),patch('easybosnian.artwork.provider',return_value=generator), \
             patch('easybosnian.store.request',side_effect=mutation),patch('easybosnian.artwork.request',side_effect=fetch), \
             patch('easybosnian.store.time.sleep'):
            result=artwork(Store(),package,expose=True)
            self.assertEqual(list(result),['quiz','lesson','word'])
            self.assertEqual(generator.generate.call_count,3)
            self.assertEqual([c[0] for c in mutations],['PUT','POST']*3)
            for item in result.values():self.assertEqual(bodies[item['url']],item['path'].read_bytes())
        self.assertEqual(list(reads.values()),[2,2,2])

    def test_preview_still_never_exposes_or_reads_public_images(self):
        package=reviewed_fixture();image=io.BytesIO();Image.new('RGB',(1024,1024)).save(image,'JPEG')
        store=MagicMock();generator=MagicMock();generator.generate.return_value=image.getvalue()
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.artwork.ROOT',Path(temp)), \
             patch('easybosnian.artwork.provider',return_value=generator),patch('easybosnian.artwork.request') as fetch:
            artwork(store,package,expose=False)
        self.assertEqual(store.put_file.call_count,3);store.expose.assert_not_called();fetch.assert_not_called()
