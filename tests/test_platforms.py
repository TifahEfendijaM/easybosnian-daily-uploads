import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from easybosnian.daily import daily
from easybosnian.facebook import verify_post, reconcile, pipeline_facebook
from easybosnian.meta import Facebook


DATE = "2026-10-03"


def record():
    return {"package": {"caption": "Reviewed caption", "hashtags": ["#bosnian"], "cards": [{"kind": k} for k in ("quiz", "lesson", "word")]}, "state": {"platforms": {"facebook": {"publish_intent": True, "publish_intent_at": "2026-10-03T18:04:00+00:00", "post_id": "42_99", "cards": {k: {"photo_id": str(i)} for i, k in enumerate(("quiz", "lesson", "word"), 1)}}}}, "revision": 0}


def post():
    return {"id": "42_99", "from": {"id": "42"}, "message": "Reviewed caption\n\n#bosnian", "is_published": True, "permalink_url": "https://www.facebook.com/42/posts/99", "attachments": {"data": [{"type": "album", "subattachments": {"data": [{"type": "photo", "target": {"id": str(i)}} for i in range(1, 4)]}}]}}


class PlatformTests(unittest.TestCase):
    def test_facebook_verifies_page_caption_each_photo_and_permalink(self):
        fb = Mock(page_id="42")
        fb.post.return_value = post()
        saved = record()
        verify_post(fb, saved)
        self.assertTrue(saved["state"]["platforms"]["facebook"]["verified"])
        for field, bad in (("from", {"id": "other"}), ("message", "Different"), ("is_published", False), ("permalink_url", "https://facebook.com.attacker.test/post"), ("attachments", {"data": []})):
            actual = post(); actual[field] = bad; fb.post.return_value = actual
            with self.subTest(field=field), self.assertRaises(ValueError): verify_post(fb, record())
        actual = post(); actual["attachments"]["data"][0]["subattachments"]["data"][1]["target"]["id"] = "wrong"
        fb.post.return_value = actual
        with self.assertRaises(ValueError): verify_post(fb, record())

    def test_uncertain_facebook_publication_cannot_repost(self):
        with patch("easybosnian.facebook.verify_repository"), patch("easybosnian.facebook.checked_batch", return_value=record()), patch("easybosnian.facebook.Store") as store, patch("easybosnian.facebook.Facebook") as fb, patch("easybosnian.facebook.failure", return_value="uncertain"), patch.dict(os.environ, {"FACEBOOK_POSTING_ENABLED": "true"}):
            store.return_value.call.return_value = {"daily_enabled": True, "daily_authorized": True, "monitoring_ready": True}
            with self.assertRaises(RuntimeError): pipeline_facebook(DATE, "live")
            fb.assert_not_called()

    def test_readonly_facebook_reconciliation_without_match_stops(self):
        saved = record(); saved["state"]["platforms"]["facebook"].pop("post_id")
        fb = Mock(page_id="42"); fb.recent.return_value = {"data": []}
        with self.assertRaises(ValueError): reconcile(fb, Mock(), DATE, saved)
        fb.publish.assert_not_called()
        fb.photo.assert_not_called()

    def test_instagram_failure_does_not_prevent_facebook_or_manual_exports(self):
        with tempfile.TemporaryDirectory() as directory, patch("easybosnian.daily.ROOT", Path(directory)), patch("easybosnian.daily.pipeline", side_effect=RuntimeError("IG failed")), patch("easybosnian.daily.pipeline_facebook", return_value={"verified": True, "permalink": "https://www.facebook.com/42/posts/99"}) as fb, patch("easybosnian.daily.export_tiktok", return_value={"status": "manual publication required", "published": False}) as tt, patch.dict(os.environ, {"FACEBOOK_POSTING_ENABLED": "true", "TIKTOK_EXPORT_ENABLED": "true"}):
            with self.assertRaises(RuntimeError): daily(DATE, "live")
            fb.assert_called_once(); tt.assert_called_once()
            result = (Path(directory) / "build" / DATE / "platforms-result.json").read_text()
            self.assertIn("confirmed published", result)
            self.assertIn("manual publication required", result)

    def test_instagram_token_cannot_authorize_facebook(self):
        with patch.dict(os.environ, {"META_GRAPH_VERSION": "v26.0"}), patch("easybosnian.meta.request", return_value={"id": "17841429077454658", "name": "EasyBosnian"}):
            with self.assertRaises(ValueError): Facebook("fake-test-token", "42").verify_page()


if __name__ == "__main__": unittest.main()
