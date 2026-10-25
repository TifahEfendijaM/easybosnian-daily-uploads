import json
import os
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from easybosnian.cloud_prepare import bootstrap, cloud_run, managed_auth, persist, require_agent_ready, run_codex
from easybosnian.core import PROJECT, REPO, ROOT, write_json, read_json


def auth(token="fresh"):
    return json.dumps({"auth_mode":"chatgpt", "last_refresh":"2026-10-02T16:00:00Z", "tokens":{
        "access_token":token, "refresh_token":"refresh", "id_token":"identity"}})


class CloudPreparationTests(unittest.TestCase):
    def setUp(self):
        guard=patch('easybosnian.notify.gh',return_value='test-only')
        guard.start();self.addCleanup(guard.stop)

    def test_fresh_runner_creates_private_logs_and_child_has_no_provider_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path=root/"credentials/auth.json"
            path.parent.mkdir(); path.write_text(auth())
            seen=[]
            def fake_run(args, **kwargs):
                if args[0]=="codex":
                    seen.append(kwargs["env"])
                    self.assertIn("--output-schema",args)
                    (root/"build/cloud-agent-last.secret").write_text("READY\n")
                return subprocess.CompletedProcess(args,0,stdout="")
            with patch("easybosnian.cloud_prepare.ROOT",root), patch("easybosnian.cloud_prepare.auth_file",return_value=path), patch("easybosnian.cloud_prepare.verify_repository"), patch("easybosnian.cloud_prepare.subprocess.run",side_effect=fake_run), patch.dict(os.environ,{"GH_TOKEN":"private","INSTAGRAM_ACCESS_TOKEN":"private","INSTAGRAM_FACEBOOK_ACCESS_TOKEN":"private","INSTAGRAM_FACEBOOK_USER_ID":"private","INSTAGRAM_FACEBOOK_EXPIRES_AT":"private","OPENAI_API_KEY":"paid"}):
                self.assertEqual(run_codex("Reply READY"),"READY")
                self.assertFalse(any(k in seen[0] for k in ("GH_TOKEN","INSTAGRAM_ACCESS_TOKEN","INSTAGRAM_FACEBOOK_ACCESS_TOKEN","INSTAGRAM_FACEBOOK_USER_ID","INSTAGRAM_FACEBOOK_EXPIRES_AT","OPENAI_API_KEY")))
                self.assertEqual((root/"build/cloud-agent-events.secret").stat().st_mode & 0o777,0o600)

    def test_only_complete_managed_subscription_auth_is_accepted(self):
        self.assertEqual(managed_auth(auth())["auth_mode"], "chatgpt")
        for value in ("invalid", "null", "[]", '{"auth_mode":"chatgptAuthTokens"}',
                      '{"auth_mode":"chatgpt","OPENAI_API_KEY":"paid"}', '{"auth_mode":"chatgpt","tokens":{}}'):
            with self.assertRaises(ValueError): managed_auth(value)

    def test_restore_is_confined_to_dedicated_private_runner_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/"easybosnian-cloud-codex"
            environment={"RUNNER_TEMP":temp,"EASYBOSNIAN_CODEX_DIR":str(directory),"GITHUB_ACTIONS":"true","CODEX_AUTH_JSON":auth()}
            with patch.dict(os.environ,environment), patch("easybosnian.cloud_prepare.verify_repository"):
                bootstrap()
                self.assertEqual((directory/"auth.json").stat().st_mode & 0o777, 0o600)
                os.environ["EASYBOSNIAN_CODEX_DIR"]=temp
                with self.assertRaises(ValueError): bootstrap()

    def test_writeback_uses_refreshed_file_and_restores_native_token(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"auth.json"; path.write_text(auth("updated-after-run"))
            environment={"GH_TOKEN":"native", "GH_SECRETS_TOKEN":"writer", "CODEX_AUTH_JSON":auth("old-seed")}
            seen=[]
            def fake_gh(*args, **kwargs):
                seen.append((args, kwargs, os.environ["GH_TOKEN"]))
                return json.dumps({"name":"CODEX_AUTH_JSON"})
            with patch.dict(os.environ,environment), patch("easybosnian.cloud_prepare.auth_file",return_value=path), patch("easybosnian.cloud_prepare.gh",side_effect=fake_gh):
                persist()
                self.assertEqual(managed_auth(seen[0][1]["input_text"])["tokens"]["access_token"], "updated-after-run")
                self.assertTrue(all(x[2]=="writer" for x in seen))
                self.assertEqual(os.environ["GH_TOKEN"],"native")
                self.assertFalse(path.exists())

    def test_failed_writeback_is_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"auth.json"; path.write_text(auth())
            with patch.dict(os.environ,{"GH_TOKEN":"native","GH_SECRETS_TOKEN":"writer"}), patch("easybosnian.cloud_prepare.auth_file",return_value=path), patch("easybosnian.cloud_prepare.gh",side_effect=RuntimeError("denied")):
                with self.assertRaises(RuntimeError): persist()
                self.assertTrue(path.exists())
                self.assertEqual(os.environ["GH_TOKEN"],"native")

    def test_completion_contract_never_exposes_free_form_agent_output(self):
        require_agent_ready('{"status":"ready","reason":"none"}')
        for value in ('READY', '{"status":"ready","reason":"other"}',
                      '{"status":"blocked","reason":"private-quiz-answer"}',
                      '{"status":"ready","reason":"none","answer":"private-quiz-answer"}'):
            with self.assertRaises(ValueError) as failure:
                require_agent_ready(value)
            self.assertNotIn("private-quiz-answer",str(failure.exception))
        with self.assertRaisesRegex(ValueError,"Reliable source opening"):
            require_agent_ready('{"status":"blocked","reason":"research_sources"}')

    def test_verify_only_reads_history_and_writes_private_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def agent(*args,**kwargs):
                write_json(root/'build/cloud-file-probe.json',{'status':'ready','reason':'none'})
                return '{"status":"ready","reason":"none"}'
            with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex',side_effect=agent),patch('easybosnian.cloud_prepare.prepare') as save,patch('easybosnian.cloud_prepare.require_publishing') as live:
                store.return_value.history.return_value={'project':PROJECT,'days':[]}
                result=cloud_run('verify')
                save.assert_not_called();live.assert_not_called();store.return_value.save_content.assert_not_called()
                self.assertEqual(result['status'],'cloud connection verified')

    def test_active_research_prompt_omits_redundant_layout_selection(self):
        prompt=(ROOT/'docs/cloud-agent-task.md').read_text()
        self.assertIn('omit design_template',prompt)
        self.assertNotIn('reselect palette and per-card layouts',prompt)
        self.assertNotIn('Keep palette/layout IDs',prompt)
        self.assertNotIn('data/design-layouts.json',prompt)
        self.assertIn('never by this research child',prompt)

    def test_preview_reuses_today_without_research_or_live_gate(self):
        date='2026-10-03';package={'date':date,'schema_version':1}
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cloud_prepare.ROOT',Path(temp)),patch('easybosnian.cloud_prepare.today',return_value=date),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex') as agent,patch('easybosnian.cloud_prepare.require_publishing') as live,patch('easybosnian.cloud_prepare.validate'),patch('easybosnian.cloud_prepare.fit_check'):
            store.return_value.history.return_value={'project':PROJECT,'days':[{'date':date,'content':package}]}
            cloud_run('preview');agent.assert_not_called();live.assert_not_called()

    def test_daily_always_researches_replacement_then_validates_and_saves(self):
        date='2026-10-03';order=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
            def agent(*args):
                order.append('research');package={'date':date,'cards':[{'kind':x} for x in ('quiz','lesson','word')]}
                package['cards'][0]['quiz_format']=read_json(root/'build/preparation-context.json')['selection']['quiz_format_target']
                write_json(root/f'build/preparation/{date}.json',package)
                return '{"status":"ready","reason":"none"}'
            with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.today',return_value=date),patch('easybosnian.cloud_prepare.require_publishing'),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex',side_effect=agent),patch('easybosnian.cloud_prepare.validate',side_effect=lambda *a,**k:order.append('validate')),patch('easybosnian.cloud_prepare.fit_check',side_effect=lambda *a:order.append('fit')),patch('easybosnian.cloud_prepare.prepare',side_effect=lambda *a,**k:order.append('save')):
                store.return_value.history.return_value={'project':PROJECT,'days':[{'date':date,'content':{'old':'content'}}]}
                cloud_run('daily');self.assertEqual(order,['research','validate','fit','save'])

    def test_missing_draft_never_saves_or_renders(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
            with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex',return_value='{"status":"ready","reason":"none"}'),patch('easybosnian.cloud_prepare.prepare') as save,patch('easybosnian.cloud_prepare.failure',return_value='safe failure'):
                store.return_value.history.return_value={'project':PROJECT,'days':[]}
                with self.assertRaises(RuntimeError):cloud_run('preview')
                save.assert_not_called()

    def test_same_words_and_custom_defaults_both_enforce_fresh_content_rules(self):
        import copy
        from test_project import reviewed_fixture
        date='2026-10-03';old=reviewed_fixture();old['date']=date;old['bosnian_level']='A2'
        for choice in ('same_words','custom'):
            with self.subTest(choice=choice),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(*args):
                    package=copy.deepcopy(old)
                    for c in package['cards']:c['background_prompt']+=' Fresh natural light.'
                    package['bosnian_level']='B2'
                    for word in package['words']:word['bosnian_level']='A2'
                    package['caption']+=' Danas.';package['cards'][0]['quiz_format']=read_json(root/'build/preparation-context.json')['selection']['quiz_format_target']
                    for c in package['cards']:c['question' if c['kind']=='quiz' else 'body']+=' Danas.'
                    write_json(root/f'build/preparation/{date}.json',package)
                    return '{"status":"ready","reason":"none"}'
                with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.today',return_value=date),patch('easybosnian.cloud_prepare.select_run_level',return_value='B2'),patch('easybosnian.cloud_prepare.require_publishing') as gate,patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex',side_effect=agent),patch('easybosnian.cloud_prepare.validate') as validation,patch('easybosnian.cloud_prepare.fit_check'),patch('easybosnian.cloud_prepare.prepare') as save:
                    store.return_value.history.return_value={'project':PROJECT,'days':[{'date':date,'content':old}]}
                    cloud_run('daily',choice)
                    gate.assert_called_once();save.assert_called_once()
                    self.assertEqual(validation.call_args.kwargs['require_website_footer'],True)
                    self.assertEqual(validation.call_args.kwargs['require_quiz_format'],True)
                    self.assertEqual(validation.call_args.kwargs['target_cefr'],'B2')
                    self.assertEqual(validation.call_args.kwargs['word_level_targets'],['A2']*3)
                    context=read_json(root/'build/preparation-context.json')
                    self.assertEqual(context['target_cefr'],'B2')
                    if choice=='custom':self.assertEqual(context['selection']['requested_words'],[w['lemma'] for w in old['words']])
