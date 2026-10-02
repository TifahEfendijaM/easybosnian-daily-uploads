import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.cli import activate
from easybosnian.cloud_prepare import bootstrap, cloud_run, managed_auth, persist, publication_state
from easybosnian.core import PROJECT, REPO


def auth(token="fresh"):
    return json.dumps({"auth_mode":"chatgpt", "last_refresh":"2026-10-02T16:00:00Z", "tokens":{
        "access_token":token, "refresh_token":"refresh", "id_token":"identity"}})


class CloudPreparationTests(unittest.TestCase):
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
            with patch("easybosnian.cloud_prepare.ROOT",Path(temp)), patch("easybosnian.cloud_prepare.check_infrastructure"), patch("easybosnian.cloud_prepare.Store") as store, patch("easybosnian.cloud_prepare.queued_packages",return_value=[]), patch("easybosnian.cloud_prepare.run_codex",return_value="READY"), patch("easybosnian.cloud_prepare.save_proof") as proof, patch("easybosnian.cloud_prepare.prepare") as prepare, patch("easybosnian.cloud_prepare.activate") as activate_mock, patch.dict(os.environ,{"GITHUB_RUN_URL":"https://github.com/"+REPO+"/actions/runs/1"}):
                store.return_value.history.return_value={"project":PROJECT,"batches":[]}
                store.return_value.call.return_value={"healthchecks_deferred":True,"github_monitoring_ready":True}
                cloud_run("verify")
                proof.assert_called_once()
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


if __name__=="__main__": unittest.main()
