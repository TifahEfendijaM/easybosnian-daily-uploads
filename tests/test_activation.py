import os
import unittest
from unittest.mock import patch

from easybosnian.cli import activate
from easybosnian.core import REPO, publication_monitoring_ready
from easybosnian.notify import heartbeat


class DeferredMonitoringTests(unittest.TestCase):
    def test_deferral_requires_verified_github_monitoring(self):
        self.assertFalse(publication_monitoring_ready({"healthchecks_deferred": True}))
        self.assertFalse(publication_monitoring_ready({"healthchecks_deferred": "true", "github_monitoring_ready": True}))
        self.assertTrue(publication_monitoring_ready({"healthchecks_deferred": True, "github_monitoring_ready": True}))
        self.assertTrue(publication_monitoring_ready({"monitoring_ready": True}))

    def test_deferred_email_never_contacts_healthchecks(self):
        with patch("easybosnian.notify.Store") as store, patch("easybosnian.notify.request") as request:
            store.return_value.call.return_value={"healthchecks_deferred": True}
            for status in ("start", "success", "fail"):
                self.assertIn("deferred", heartbeat("preparation", status))
            request.assert_not_called()

    def test_deferral_does_not_bypass_real_queue_save(self):
        with patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Store") as store, patch("easybosnian.cli.gh") as gh:
            store.return_value.call.return_value={"healthchecks_deferred": True, "github_monitoring_ready": True, "preparation_verified": False}
            with self.assertRaises(ValueError): activate("enable-daily")
            gh.assert_not_called()
            self.assertEqual(store.return_value.call.call_count,1)

    def test_deferral_preserves_unconfirmed_email_state(self):
        config={"daily_enabled": False, "monitoring_ready": False, "preparation_verified": False}
        with patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Store") as store, patch("easybosnian.cli.gh") as gh:
            store.return_value.call.side_effect=[config, {"repository":REPO, "github_notification_check":"accepted"}, {}]
            activate("defer-healthchecks")
            self.assertTrue(config["healthchecks_deferred"])
            self.assertTrue(config["github_monitoring_ready"])
            self.assertFalse(config["monitoring_ready"])
            self.assertFalse(config["daily_enabled"])
            gh.assert_not_called()

    def test_wrong_repository_monitoring_check_cannot_enable_deferral(self):
        config={"daily_enabled": False}
        with patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Store") as store:
            store.return_value.call.side_effect=[config, {"repository":"another/repository", "github_notification_check":"accepted"}]
            with self.assertRaises(ValueError): activate("defer-healthchecks")
            self.assertNotIn("healthchecks_deferred",config)
            self.assertEqual(store.return_value.call.call_count,2)

    def test_verified_package_can_activate_with_user_deferral(self):
        config={"preparation_verified":True, "monitoring_ready":False, "healthchecks_deferred":True, "github_monitoring_ready":True}
        with patch.dict(os.environ,{"GITHUB_ACTIONS":""}), patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Store") as store, patch("easybosnian.cli.gh") as gh:
            store.return_value.call.side_effect=[config, {}]
            activate("enable-daily")
            gh.assert_called_once_with("variable","set","DAILY_POSTING_ENABLED","--repo",REPO,"--body","true")
            self.assertTrue(config["daily_enabled"])
            self.assertFalse(config["monitoring_ready"])


if __name__=="__main__": unittest.main()
