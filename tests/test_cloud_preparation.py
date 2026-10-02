import json
import os
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from easybosnian.cli import activate
from easybosnian.cloud_prepare import bootstrap, cloud_run, managed_auth, persist, publication_state, require_agent_ready, run_codex
from easybosnian.core import PROJECT, REPO, write_json


def auth(token="fresh"):
    return json.dumps({"auth_mode":"chatgpt", "last_refresh":"2026-10-02T16:00:00Z", "tokens":{
        "access_token":token, "refresh_token":"refresh", "id_token":"identity"}})


class CloudPreparationTests(unittest.TestCase):
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
            with patch("easybosnian.cloud_prepare.ROOT",root), patch("easybosnian.cloud_prepare.auth_file",return_value=path), patch("easybosnian.cloud_prepare.verify_repository"), patch("easybosnian.cloud_prepare.subprocess.run",side_effect=fake_run), patch.dict(os.environ,{"GH_TOKEN":"private","INSTAGRAM_ACCESS_TOKEN":"private","OPENAI_API_KEY":"paid"}):
                self.assertEqual(run_codex("Reply READY"),"READY")
                self.assertFalse(any(k in seen[0] for k in ("GH_TOKEN","INSTAGRAM_ACCESS_TOKEN","OPENAI_API_KEY")))
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

    def test_connection_check_never_reserves_activates_or_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            def fake_agent(*args, **kwargs):
                write_json(Path(temp)/"build/cloud-file-probe.json",{"status":"ready","reason":"none"})
                return '{"status":"ready","reason":"none"}'
            with patch("easybosnian.cloud_prepare.ROOT",Path(temp)), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex",side_effect=fake_agent), patch("easybosnian.cloud_prepare.save_proof") as proof, patch("easybosnian.cloud_prepare.prepare") as prepare, patch("easybosnian.cloud_prepare.activate") as activate_mock, patch.dict(os.environ,{"GITHUB_RUN_URL":"https://github.com/"+REPO+"/actions/runs/1"}):
                store.return_value.history.return_value={"project":PROJECT,"batches":[]}
                store.return_value.call.return_value={"healthchecks_deferred":True,"github_monitoring_ready":True}
                cloud_run("verify")
                proof.assert_called_once()
                self.assertTrue(proof.call_args.args[0]["chatgpt_workspace_read_write"])
                prepare.assert_not_called(); activate_mock.assert_not_called()
                self.assertTrue(all(x.args[0]=="GET" for x in store.return_value.call.call_args_list))

    def test_cloud_activation_needs_armed_schedule_but_no_variable_write(self):
        for enabled in ("false","true"):
            config={"preparation_verified":True,"healthchecks_deferred":True,"github_monitoring_ready":True}
            with patch.dict(os.environ,{"GITHUB_ACTIONS":"true","DAILY_POSTING_ENABLED":enabled}), patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Store") as store, patch("easybosnian.cli.gh") as gh:
                store.return_value.call.return_value=config
                if enabled=="false":
                    with self.assertRaises(ValueError): activate("enable-daily")
                    self.assertEqual(store.return_value.call.call_count,1)
                else:
                    activate("enable-daily")
                    self.assertEqual(store.return_value.call.call_count,2)
                gh.assert_not_called()

    def test_existing_publication_state_is_reported_honestly(self):
        for state, expected in (({},"nothing published by preparation; inspect the separate pipeline run"),
                                ({"publish_intent":True},"publication uncertain; reconcile existing batch"),
                                ({"verified":True},"already verified published")):
            self.assertEqual(publication_state({"batches":[{"date":"2026-10-02","state":state}]},"2026-10-02"),expected)

    def test_same_date_reservation_resumes_exact_package_without_research(self):
        date="2026-10-02"; package={"date":date,"immutable":"same reserved content"}
        with tempfile.TemporaryDirectory() as temp:
            with patch("easybosnian.cloud_prepare.ROOT",Path(temp)), patch("easybosnian.cloud_prepare.today",return_value=date), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex") as agent, patch("easybosnian.cloud_prepare.validate"), patch("easybosnian.cloud_prepare.fit_check"), patch("easybosnian.cloud_prepare.prepare") as prepare, patch("easybosnian.cloud_prepare.activate"):
                store.return_value.history.return_value={"project":PROJECT,"batches":[{"date":date,"state":{}}]}
                store.return_value.batch.return_value={"package":package}
                store.return_value.call.side_effect=[{"healthchecks_deferred":True,"github_monitoring_ready":True},{"daily_enabled":True,"preparation_verified":True}]
                cloud_run("prepare")
                agent.assert_not_called()
                path=prepare.call_args.args[0]
                self.assertEqual(json.loads(path.read_text()),package)

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

    def test_fresh_research_blocks_before_reservation_on_missing_or_unreviewed_draft(self):
        date="2026-10-03"
        for response in ('{"status":"ready","reason":"none"}',
                         '{"status":"blocked","reason":"research_sources"}'):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as temp:
                root=Path(temp); (root/"docs").mkdir()
                (root/"docs/cloud-agent-task.md").write_text("Prepare {{DATE}}")
                with patch("easybosnian.cloud_prepare.ROOT",root), patch("easybosnian.cloud_prepare.today",return_value=date), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex",return_value=response), patch("easybosnian.cloud_prepare.validate") as validation, patch("easybosnian.cloud_prepare.prepare") as prepare, patch("easybosnian.cloud_prepare.activate") as activation, patch("easybosnian.cloud_prepare.failure",return_value="safe failure") as report:
                    store.return_value.history.return_value={"project":PROJECT,"batches":[]}
                    store.return_value.call.return_value={"healthchecks_deferred":True,"github_monitoring_ready":True}
                    # A stale unreserved file must not be mistaken for this agent's result.
                    write_json(root/f"build/preparation/{date}.json",{"date":date})
                    with self.assertRaises(RuntimeError): cloud_run("prepare")
                    self.assertEqual(report.call_args.args[1],"cloud ChatGPT research/review")
                    validation.assert_not_called(); prepare.assert_not_called(); activation.assert_not_called()
                    self.assertFalse((root/"build/preparation-result.json").exists())

    def test_fresh_reviewed_draft_passes_validation_before_saving_and_handoff(self):
        date="2026-10-03"; package={"date":date,"reviewed":"fixture"}; order=[]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/"docs").mkdir()
            (root/"docs/cloud-agent-task.md").write_text("Prepare {{DATE}}")
            def fake_agent(prompt, **kwargs):
                self.assertIn(date,prompt)
                write_json(root/f"build/preparation/{date}.json",package)
                return '{"status":"ready","reason":"none"}'
            with patch("easybosnian.cloud_prepare.ROOT",root), patch("easybosnian.cloud_prepare.today",return_value=date), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex",side_effect=fake_agent), patch("easybosnian.cloud_prepare.validate",side_effect=lambda *args:order.append("validate")), patch("easybosnian.cloud_prepare.fit_check",side_effect=lambda *args:order.append("fit")), patch("easybosnian.cloud_prepare.prepare",side_effect=lambda *args:order.append("save")), patch("easybosnian.cloud_prepare.activate",side_effect=lambda *args:order.append("activate")):
                store.return_value.history.return_value={"project":PROJECT,"batches":[]}
                store.return_value.call.side_effect=[{"healthchecks_deferred":True,"github_monitoring_ready":True},{"daily_enabled":True,"preparation_verified":True}]
                cloud_run("prepare")
                self.assertEqual(order,["validate","fit","save","activate"])
                result=json.loads((root/"build/preparation-result.json").read_text())
                self.assertEqual(result["date"],date)
                self.assertEqual(len(result["package_hash"]),64)

    def test_connection_ready_message_without_actual_probe_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch("easybosnian.cloud_prepare.ROOT",Path(temp)), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex",return_value='{"status":"ready","reason":"none"}'), patch("easybosnian.cloud_prepare.save_proof") as proof, patch("easybosnian.cloud_prepare.failure",return_value="safe failure") as report:
                store.return_value.history.return_value={"project":PROJECT,"batches":[]}
                store.return_value.call.return_value={"healthchecks_deferred":True,"github_monitoring_ready":True}
                with self.assertRaises(RuntimeError): cloud_run("verify")
                proof.assert_not_called()
                self.assertEqual(report.call_args.args[1],"cloud ChatGPT workspace verification")


if __name__=="__main__": unittest.main()
