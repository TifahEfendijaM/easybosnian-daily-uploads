import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from easybosnian.artwork import artwork
from easybosnian.http import SafeError, request, safe_response_error
from easybosnian.notify import failure, next_step
from easybosnian.providers import CloudflareFlux
from test_project import reviewed_fixture


class FluxErrorTests(unittest.TestCase):
    def test_worker_error_retains_safe_reason_code_and_distinct_upstream_status(self):
        payload={'stage':'FLUX generation','reason':'ai_call_failed','code':3040,
                 'provider_http_status':429,'error':'private provider prose and token'}
        error=HTTPError('https://example.test/v1/generate',409,'private',{},io.BytesIO(json.dumps(payload).encode()))
        with patch('easybosnian.http.urlopen',side_effect=error) as send:
            with self.assertRaises(SafeError) as caught:request('POST','https://example.test/v1/generate')
        send.assert_called_once()
        result=caught.exception
        self.assertEqual((result.stage,result.http_status,result.reason,result.provider_code,result.provider_http_status),
                         ('FLUX generation',409,'ai_call_failed',3040,429))
        self.assertIn('provider code 3040; provider HTTP 429',str(result))
        self.assertIn('inference failed',str(result));self.assertNotIn('private',str(result))

    def test_unknown_or_non_numeric_diagnostics_are_never_echoed(self):
        for code,status,reason in [('3040',429,'private-token'),('private-token','private-token',{'private':'token'}),
                                   (100000,999,None),(True,True,[]),(None,None,'ai_call_failed')]:
            with self.subTest(code=code,status=status):
                result=safe_response_error({'stage':'FLUX generation','code':code,'provider_http_status':status,
                                            'reason':reason,'error':'private provider prose'},409)
                self.assertIsNone(result.provider_code)
                self.assertEqual(result.provider_http_status,429 if type(status) is int and status==429 else None)
                self.assertNotIn('private',str(result))
                self.assertNotIn('100000',str(result))
        for value in (None,[],{'stage':{'private':'token'},'reason':[],'error':'private'}):
            self.assertNotIn('private',str(safe_response_error(value,503)))

    def test_unknown_bounded_numeric_provider_codes_remain_diagnostic(self):
        result=safe_response_error({'stage':'FLUX generation','reason':'ai_call_failed','code':9999,'provider_http_status':409},409)
        self.assertEqual(result.provider_code,9999)
        self.assertIn('provider code 9999; provider HTTP 409',str(result))

    def test_meta_codes_keep_existing_nested_format_and_privacy(self):
        result=safe_response_error({'error':{'code':9007,'error_subcode':2207027,'message':'private-token'}},400)
        self.assertIn('provider code 9007; provider subcode 2207027',str(result))
        self.assertIsNone(result.stage);self.assertIsNone(result.provider_code)
        self.assertNotIn('private',str(result))

    @patch.dict(os.environ,{"GITHUB_REPOSITORY_VISIBILITY":"private"})
    def test_artwork_to_failure_issue_keeps_diagnostics_without_generation_retry(self):
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        payload={'stage':'FLUX generation','reason':'ai_call_failed','code':3036,'provider_http_status':429,
                 'error':'private provider prose and token'}
        upstream=HTTPError('https://example.test/v1/generate',409,'private',{},io.BytesIO(json.dumps(payload).encode()))
        store=MagicMock()
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'EASYBOSNIAN_WORKER_URL':'https://example.test','EASYBOSNIAN_ADMIN_TOKEN':'private-token'}), \
             patch('easybosnian.http.urlopen',side_effect=upstream) as send, \
             patch('easybosnian.artwork.ROOT',Path(temp)),patch('easybosnian.notify.ROOT',Path(temp)), \
             patch('easybosnian.artwork.provider',return_value=CloudflareFlux()),patch('easybosnian.notify.gh') as issue:
            with self.assertRaises(SafeError) as caught:artwork(store,package,review_images=True)
            error=caught.exception
            self.assertEqual((error.http_status,error.provider_code,error.provider_http_status),(409,3036,429))
            report=failure(package['date'],error.stage,error,'nothing published by this run','https://example.test/run')
            self.assertIn('daily free allocation is exhausted',report);self.assertIn('00:00 UTC',report)
            self.assertIn('provider code 3036; provider HTTP 429',report)
            self.assertNotIn('private provider',report);self.assertNotIn('private-token',report)
            self.assertEqual((Path(temp)/'build/failure.txt').read_text(),report)
            issue.assert_called_once();send.assert_called_once()
            store.put_file.assert_not_called();store.expose.assert_not_called()

    def test_next_steps_distinguish_provider_limits_from_local_storage(self):
        for code,reason,status,expected in [(3040,'ai_call_failed',429,'temporary inference capacity'),
                                           (3036,'ai_call_failed',429,'daily free allocation'),
                                           (3007,'ai_call_failed',408,'timed out'),
                                           (None,'ai_call_failed',408,'timed out'),
                                           (5035,'ai_call_failed',403,'do not upgrade'),
                                           (None,'cache_write_failed',None,'private Workers KV'),
                                           (None,'ai_binding_missing',None,'no inference request'),
                                           (3042,'ai_call_failed',404,'model ID')]:
            with self.subTest(code=code,reason=reason):
                error=SafeError('fixed',reason=reason,provider_code=code,provider_http_status=status)
                self.assertIn(expected,next_step('FLUX generation',error))

    def test_worker_json_error_without_http_rejection_uses_the_same_safe_mapping(self):
        response=MagicMock();response.read.return_value=json.dumps({'error':'private-token','stage':'FLUX generation',
            'reason':'ai_image_missing','code':None,'provider_http_status':200}).encode()
        response.__enter__.return_value=response
        with patch('easybosnian.http.urlopen',return_value=response) as send:
            with self.assertRaisesRegex(SafeError,'returned no image') as caught:request('POST','https://example.test')
        send.assert_called_once();self.assertEqual(caught.exception.provider_http_status,200)
        self.assertNotIn('private-token',str(caught.exception))

class PrivateFluxDiagnosticTests(unittest.TestCase):
    def test_error_body_is_read_once_privately_without_a_second_inference(self):
        batch='b-'+'a'*32;run='r-'+'b'*32
        error=SafeError('safe status only','FLUX generation',409,diagnostic_saved=True)
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.providers.ROOT',Path(temp)),patch('easybosnian.providers.Store') as factory:
            factory.return_value.call.side_effect=[error,b'private upstream diagnostic']
            with self.assertRaises(SafeError):CloudflareFlux().generate('prompt','2026-10-06','quiz',batch,reviewed_content={},artwork_id=run)
            calls=factory.return_value.call.call_args_list
            self.assertEqual([c.args[0] for c in calls],['POST','GET'])
            self.assertEqual(calls[1].args[1],f'/v1/generation-errors/batches/{batch}/{run}/quiz')
            path=Path(temp)/'build'/batch/'quiz-provider-error.secret'
            self.assertEqual(path.read_bytes(),b'private upstream diagnostic');self.assertEqual(path.stat().st_mode & 0o777,0o600)
