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
from easybosnian.providers import CloudflareFlux, flux_diagnostic_reason
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


class PublicFluxExplanationTests(unittest.TestCase):
    def test_saved_provider_envelopes_add_fixed_explanations_without_retry_or_raw_prose(self):
        cases=[(8007,400,'Prompt contains NSFW content.','ai_content_rejected','content-safety'),
               (4006,429,'You have used up your daily free allocation of 10,000 neurons.','ai_free_allocation_exhausted','free allocation'),
               (4006,429,'Service temporarily at capacity.','ai_capacity_exceeded','temporary inference capacity')]
        batch='b-'+'a'*32;run='r-'+'b'*32
        for code,status,description,reason,expected in cases:
            with self.subTest(code=code,description=description),tempfile.TemporaryDirectory() as temp:
                error=SafeError(f'HTTP 409; provider code {code}; provider HTTP {status}; inference failed',
                                'FLUX generation',409,reason='ai_call_failed',provider_code=code,
                                provider_http_status=status,diagnostic_saved=True)
                body=json.dumps({'internalCode':code,'httpCode':status,'description':description,
                                 'message':'PRIVATE_PROVIDER_BODY','requestId':'PRIVATE_REQUEST_ID',
                                 'prompt':'PRIVATE_QUIZ_REVIEW'}).encode()
                with patch('easybosnian.providers.ROOT',Path(temp)),patch('easybosnian.providers.Store') as factory,patch('easybosnian.notify.ROOT',Path(temp)),patch('easybosnian.notify.gh') as github,patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_VISIBILITY':'public'}):
                    factory.return_value.call.side_effect=[error,body]
                    with self.assertRaises(SafeError) as caught:
                        CloudflareFlux().generate('approved public scene','2026-10-25','quiz',batch,reviewed_content={},artwork_id=run)
                    result=caught.exception
                    self.assertEqual((result.provider_code,result.provider_http_status,result.reason),(code,status,reason))
                    report=failure('2026-10-25','FLUX generation',result,'nothing published')
                    self.assertIn(expected,report)
                    self.assertIn(f'provider code {code}; provider HTTP {status}',report)
                    for private in ('PRIVATE_PROVIDER_BODY','PRIVATE_REQUEST_ID','PRIVATE_QUIZ_REVIEW'):
                        self.assertNotIn(private,report)
                    self.assertEqual([c.args[0] for c in factory.return_value.call.call_args_list],['POST','GET'])
                    github.assert_not_called()
                    path=Path(temp)/'build'/batch/'quiz-provider-error.secret'
                    self.assertEqual(path.read_bytes(),body);self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_unknown_mismatched_and_nonerror_fields_never_supply_an_explanation(self):
        error=SafeError('fixed',provider_code=4006,provider_http_status=429)
        values=[b'invalid',b'null',json.dumps({'internalCode':8007,'httpCode':400,'description':'NSFW'}).encode(),
                json.dumps({'internalCode':4006,'httpCode':400,'description':'NSFW'}).encode(),
                json.dumps({'internalCode':4006,'httpCode':429,'description':'Unknown upstream failure','prompt':'used up daily free allocation of neurons'}).encode(),
                json.dumps({'internalCode':4006,'httpCode':429,'description':{'message':'used up free allocation of neurons'}}).encode()]
        for value in values:
            with self.subTest(value=value):self.assertIsNone(flux_diagnostic_reason(value,error))

    def test_artwork_wrapper_preserves_provider_explanation_for_public_failure_reporting(self):
        package=reviewed_fixture();package['batch_id']='b-'+'a'*32
        error=SafeError('HTTP 409; provider code 8007; provider HTTP 400; content-safety rejection',
                        'FLUX generation',409,reason='ai_content_rejected',provider_code=8007,provider_http_status=400)
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.artwork.ROOT',Path(temp)),patch('easybosnian.artwork.provider') as provider:
            provider.return_value.generate.side_effect=error
            with self.assertRaises(SafeError) as caught:artwork(MagicMock(),package,review_images=True)
            self.assertEqual(caught.exception.reason,'ai_content_rejected')
            self.assertIn('content-safety',str(caught.exception))
            self.assertIn('NSFW/content-safety',next_step('FLUX generation',caught.exception))
            provider.return_value.generate.assert_called_once()
