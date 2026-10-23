"""A failed subscription call must be diagnosable without leaking its private trace."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.codex_diagnostics import CodexExecutionError, execution_diagnostic
from easybosnian.cloud_prepare import AgentIntegrityError, run_codex
from easybosnian.core import read_json
from easybosnian.notify import next_step
from easybosnian.visual_diagnostics import review_failure, REVIEW_FAILURES
from test_cloud_preparation import auth


class CodexDiagnosticTests(unittest.TestCase):
    def diagnostic(self, events, exit_code=1, **kwargs):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'trace.secret'
            path.write_text('\n'.join(e if isinstance(e,str) else json.dumps(e) for e in events))
            return execution_diagnostic(path,exit_code,**kwargs)

    def test_terminal_errors_are_classified_without_exporting_prose_or_tokens(self):
        for message, reason, status in (
            ('You have hit your usage limit. private-token', 'usage_limit', None),
            ('unexpected status 429 Too Many Requests private-token', 'rate_limit', 429),
            ('stream disconnected: unexpected status 401 Unauthorized private-token', 'authentication', 401),
            ('refresh_token_reused: private-token', 'refresh_token_reused', None),
            ('stream disconnected before completion private-token', 'connection', None),
            ('unexpected status 503 Service Unavailable private-token', 'service', 503),
            ('invalid_json_schema private-token', 'configuration', None),
            ('private-token unknown provider text', 'unknown', None),
        ):
            with self.subTest(reason=reason):
                data=self.diagnostic([{'type':'turn.started'}, {'type':'turn.failed','error':{'message':message}}])
                self.assertEqual((data['reason'],data['http_status']),(reason,status))
                error=CodexExecutionError(data)
                self.assertNotIn('private-token',str(data)+str(error)+next_step('cloud ChatGPT research/review',error))
                self.assertIn(review_failure(error),REVIEW_FAILURES)

    def test_model_messages_and_tool_output_cannot_forge_failure_diagnosis(self):
        data=self.diagnostic([
            {'type':'item.completed','item':{'type':'agent_message','text':'usage_limit_reached'}},
            {'type':'item.completed','item':{'type':'command_execution','aggregated_output':'refresh_token_reused'}},
            {'type':'turn.started'},
            'Error: unexpected status 401 private-model-prose',
            {'type':'turn.failed','error':{'message':'unrecognized private failure'}},
        ])
        self.assertEqual(data['reason'],'unknown')
        self.assertIsNone(data['http_status'])

    def test_final_error_takes_priority_over_intermediate_reconnect_error(self):
        data=self.diagnostic([
            {'type':'error','message':'stream disconnected; reconnecting'},
            {'type':'turn.failed','error':{'message':'usage_limit_reached'}},
        ])
        self.assertEqual(data['reason'],'usage_limit')
        data=self.diagnostic([{'type':'error','message':'stream disconnected; reconnecting'},
                              {'type':'turn.completed'}],exit_code=0)
        self.assertEqual(data['reason'],'success')
        self.assertTrue(data['turn_completed'])

    def test_startup_errors_timeout_and_malformed_events_remain_safe(self):
        self.assertEqual(self.diagnostic(['error: unexpected argument private-token'])['reason'],'configuration')
        data=self.diagnostic(['not JSON','[]','null',{'type':'turn.failed','error':[]}],exit_code=None,timed_out=True)
        self.assertEqual(data['reason'],'timeout')
        self.assertFalse(data['turn_started'])

    def invoke(self, root, *, timeout=False, changed=False):
        path=root/'credentials/auth.json';path.parent.mkdir();path.write_text(auth())
        calls=[]
        def child(args,**kwargs):
            if args[0]=='codex':
                calls.append(args)
                self.assertIn('--json',args)
                kwargs['stdout'].write(json.dumps({'type':'turn.failed','error':{'message':'unexpected status 401 Unauthorized private-token'}})+'\n')
                if timeout:raise subprocess.TimeoutExpired(args,420)
                return subprocess.CompletedProcess(args,1)
            return subprocess.CompletedProcess(args,0,stdout='tracked.py' if changed else '')
        with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.auth_file',return_value=path),patch('easybosnian.cloud_prepare.verify_repository'),patch('easybosnian.cloud_prepare.subprocess.run',side_effect=child):
            with self.assertRaises(ValueError) as caught:
                run_codex('private prompt')
        self.assertEqual(len(calls),1)  # Recording the cause never retries the model.
        self.assertNotIn('private-token',str(caught.exception))
        data=read_json(root/'build/cloud-agent-diagnostics/text-result.json')
        return caught.exception,data

    def test_process_failure_records_safe_artifact_and_preserves_integrity_guard(self):
        for changed in (False,True):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as temp:
                error,data=self.invoke(Path(temp),changed=changed)
                self.assertIsInstance(error,AgentIntegrityError if changed else CodexExecutionError)
                self.assertEqual(data['reason'],'authentication')
                self.assertEqual(data['exit_code'],1)
                self.assertEqual(data['http_status'],401)

    def test_timeout_still_records_cause_without_retrying_or_weakening_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            error,data=self.invoke(Path(temp),timeout=True)
            self.assertIn('time allowance',str(error))
            self.assertEqual(data['reason'],'timeout')
            self.assertIsNone(data['exit_code'])

    def test_diagnostic_failure_cannot_skip_the_file_boundary_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'auth.json';path.write_text(auth())
            with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.auth_file',return_value=path),patch('easybosnian.cloud_prepare.verify_repository') as guard,patch('easybosnian.cloud_prepare.execution_diagnostic',side_effect=OSError('disk unavailable')),patch('easybosnian.cloud_prepare.subprocess.run',side_effect=[subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0,stdout='tracked.py')]) as child:
                with self.assertRaises(AgentIntegrityError):run_codex('private prompt')
            guard.assert_called_once_with(remote=True)
            self.assertEqual(child.call_count,2)  # One Codex call and one git diff.
