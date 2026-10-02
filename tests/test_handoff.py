import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.core import REPO, digest
from easybosnian.handoff import main, reviewed_result
from easybosnian.pipeline import pipeline


DATE="2026-10-02"


def result():
    return {"date":DATE,"status":"reviewed JSON saved and read back","package_hash":"a"*64,
            "queue_url":f"https://github.com/{REPO}/blob/main/queue/{DATE}.json",
            "scheduled_pipeline_enabled":True}


class HandoffTests(unittest.TestCase):
    def test_only_actual_current_reviewed_result_is_eligible(self):
        self.assertEqual(reviewed_result(result(),DATE),{"batch_date":DATE,"package_hash":"a"*64})
        self.assertIsNone(reviewed_result({"status":"already verified published; preparation unchanged"},DATE))
        invalid=[{"chatgpt_authenticated":True},*[{**result(),key:value} for key,value in (
            ("date","2026-10-01"),("scheduled_pipeline_enabled",False),("scheduled_pipeline_enabled","true"),
            ("package_hash","a\nbatch_date=2026-10-01"),("queue_url","https://github.com/other/repo/queue.json"))]]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):
                reviewed_result(item,DATE)

    def test_connection_dispatch_cannot_emit_publication_outputs(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true","GITHUB_EVENT_NAME":"workflow_dispatch"}),patch("easybosnian.handoff.verify_repository"):
            with self.assertRaises(ValueError): main()

    def test_scheduled_handoff_passes_exact_date_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"build").mkdir()
            (root/"build/preparation-result.json").write_text(json.dumps(result()))
            event=root/"event.json";event.write_text(json.dumps({"schedule":"0 20 * * *"}))
            output=root/"outputs"
            env={"GITHUB_ACTIONS":"true","GITHUB_EVENT_NAME":"schedule","GITHUB_EVENT_PATH":str(event),"GITHUB_OUTPUT":str(output)}
            with patch.dict(os.environ,env),patch("easybosnian.handoff.ROOT",root),patch("easybosnian.handoff.today",return_value=DATE),patch("easybosnian.handoff.verify_repository"):
                main()
            self.assertEqual(output.read_text(),f"batch_date={DATE}\npackage_hash={'a'*64}\n")

    def test_recovery_requires_both_explicit_selection_and_authorization(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"build").mkdir()
            (root/"build/preparation-result.json").write_text(json.dumps(result()))
            event=root/"event.json";output=root/"outputs"
            env={"GITHUB_ACTIONS":"true","GITHUB_EVENT_NAME":"workflow_dispatch","GITHUB_EVENT_PATH":str(event),"GITHUB_OUTPUT":str(output),"PREPARATION_RECOVERY_AUTHORIZED":"true"}
            with patch.dict(os.environ,env),patch("easybosnian.handoff.ROOT",root),patch("easybosnian.handoff.today",return_value=DATE),patch("easybosnian.handoff.verify_repository"):
                event.write_text(json.dumps({"inputs":{"mode":"verify"}}))
                with self.assertRaises(ValueError): main()
                self.assertFalse(output.exists())
                event.write_text(json.dumps({"inputs":{"mode":"recover_today"}}))
                main()
            self.assertEqual(output.read_text(),f"batch_date={DATE}\npackage_hash={'a'*64}\n")

    def test_mismatched_handoff_stops_before_artwork_or_publication(self):
        package={"date":DATE}
        record={"state":{},"package":package,"hash":digest(package)}
        with patch.dict(os.environ,{"EXPECTED_PACKAGE_HASH":"a"*64}),patch("easybosnian.pipeline.verify_repository"),patch("easybosnian.pipeline.Store") as store,patch("easybosnian.pipeline.provider") as provider,patch("easybosnian.pipeline.Instagram") as instagram,patch("easybosnian.pipeline.failure",return_value="handoff rejected"):
            store.return_value.batch.return_value=record
            with self.assertRaises(RuntimeError): pipeline(DATE,"live")
            provider.assert_not_called();instagram.assert_not_called()
            self.assertEqual(record["state"]["failed_stage"],"validation")


if __name__=="__main__": unittest.main()
