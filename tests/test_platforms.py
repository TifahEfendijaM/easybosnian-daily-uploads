import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from easybosnian.daily import daily
from easybosnian.facebook import verify_post, reconcile, pipeline_facebook
from easybosnian.meta import Facebook
from easybosnian.cli import authorize_facebook


DATE = "2026-10-03"


def record():
    return {"package": {"caption": "Reviewed caption", "hashtags": ["#bosnian"], "cards": [{"kind": k} for k in ("quiz", "lesson", "word")]}, "state": {"platforms": {"facebook": {"publish_intent": True, "publish_intent_at": "2026-10-03T18:04:00+00:00", "post_id": "42_99", "cards": {k: {"photo_id": str(i)} for i, k in enumerate(("quiz", "lesson", "word"), 1)}}}}, "revision": 0}


def post():
    return {"id": "42_99", "from": {"id": "42"}, "message": "Reviewed caption\n\n#bosnian", "is_published": True, "permalink_url": "https://www.facebook.com/42/posts/99", "attachments": {"data": [{"type": "album", "subattachments": {"data": [{"type": "photo", "target": {"id": str(i)}} for i in range(1, 4)]}}]}}


class PlatformTests(unittest.TestCase):
    def test_authorized_page_uses_its_actual_name_and_exact_id(self):
        with patch.dict(os.environ, {"META_GRAPH_VERSION": "v26.0"}), patch("easybosnian.meta.request", return_value={"id": "1284422991426579", "name": "Easy Bosnian"}) as request:
            fb = Facebook("fake-test-token", "1284422991426579")
            self.assertEqual(fb.verify_page()["name"], "Easy Bosnian")
            request.return_value = {"id": "different", "name": "Easy Bosnian"}
            with self.assertRaises(ValueError): fb.verify_page()
            request.return_value = {"id": "1284422991426579", "name": "Other Page"}
            with self.assertRaises(ValueError): fb.verify_page()

    def test_facebook_credentials_alone_do_not_arm_public_publishing(self):
        with patch("easybosnian.cli.verify_repository"), patch("builtins.input", side_effect=["", "", ""]), patch("easybosnian.cli.getpass.getpass", return_value="fake-test-credential"), patch("easybosnian.cli.facebook_page_token", return_value=("fake-test-page-token", {})), patch("easybosnian.cli.gh") as gh, patch("easybosnian.cli.write_json"), patch("builtins.print"):
            authorize_facebook()
            self.assertEqual(gh.call_count, 2)
            self.assertTrue(all(call.args[0] == "secret" for call in gh.call_args_list))

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

    def test_native_story_requests_never_upload_image_stories_or_block_feed_posts(self):
        with tempfile.TemporaryDirectory() as directory, patch("easybosnian.daily.ROOT", Path(directory)), patch("easybosnian.daily.pipeline", return_value={"verified": True, "permalink": "https://www.instagram.com/p/confirmed/"}) as ig, patch("easybosnian.daily.pipeline_facebook", return_value={"verified": True}) as fb, patch("easybosnian.daily.pipeline_tiktok", return_value={"verified": True, "permalink": "https://tiktok.com/@easy.bosnian/photo/123"}) as tt, patch("easybosnian.daily.pipeline_stories") as stories, patch.dict(os.environ, {"FACEBOOK_POSTING_ENABLED": "true", "TIKTOK_POSTING_ENABLED": "true", "INSTAGRAM_STORIES_ENABLED": "true"}, clear=True):
            results = daily(DATE, "live")
            ig.assert_called_once(); fb.assert_called_once(); tt.assert_called_once()
            stories.assert_not_called()
            saved = json.loads((Path(directory) / "build" / DATE / "platforms-result.json").read_text())
            for name in ("instagram_stories", "tiktok_stories"):
                self.assertFalse(saved["platforms"][name]["published"])
                self.assertFalse(saved["platforms"][name]["automatic_supported"])
            self.assertEqual(results["instagram_stories"]["post_permalink"], "https://www.instagram.com/p/confirmed/")
            self.assertEqual(results["tiktok_stories"]["slides"], ["quiz-card.jpg", "lesson-card.jpg", "word-card.jpg"])

    def test_instagram_token_cannot_authorize_facebook(self):
        with patch.dict(os.environ, {"META_GRAPH_VERSION": "v26.0"}), patch("easybosnian.meta.request", return_value={"id": "17841429077454658", "name": "EasyBosnian"}):
            with self.assertRaises(ValueError): Facebook("fake-test-token", "42").verify_page()


if __name__ == "__main__": unittest.main()
