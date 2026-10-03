import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from easybosnian.buffer import Buffer, caption, checked_post, reconcile, verify_post, pipeline_tiktok
from easybosnian.cli import authorize_buffer
from easybosnian.daily import daily
from easybosnian.http import redact


DATE = "2026-10-03"
CHANNEL = "a" * 24
ORG = "b" * 24
POST = "c" * 24
URLS = ["https://project.test/" + kind + ".jpg" for kind in ("quiz", "lesson", "word")]
ENV = {"TIKTOK_POSTING_ENABLED": "true", "TIKTOK_EXPORT_ENABLED": "false", "HC_PIPELINE_URL": ""}


def channel():
    return {"id": CHANNEL, "organizationId": ORG, "serviceId": "confirmed-tiktok-account", "name": "easy.bosnian",
            "service": "tiktok", "isDisconnected": False, "isLocked": False, "isQueuePaused": False,
            "metadata": {"defaultToReminders": False}, "scopes": ["user.info.basic", "user.info.username", "video.publish", "video.list"]}


def record():
    return {"package": {"caption": "Reviewed public caption", "hashtags": ["#one", "#two", "#three", "#four", "#five", "#six"],
                        "cards": [{"kind": k} for k in ("quiz", "lesson", "word")]},
            "state": {"cards": {k: {"public_url": url} for k, url in zip(("quiz", "lesson", "word"), URLS)},
                      "platforms": {"tiktok": {"publish_intent": True, "publish_intent_at": "2026-10-03T03:00:00+00:00",
                          "channel_id": CHANNEL, "service_id": "confirmed-tiktok-account", "post_id": POST,
                          "image_urls": URLS, "asset_ids": ["1", "2", "3"]}}}, "revision": 0}


def post():
    return {"id": POST, "channelId": CHANNEL, "channelService": "tiktok", "text": caption(record()["package"]),
            "status": "sent", "schedulingType": "automatic", "sentAt": "2026-10-03T03:04:00Z",
            "createdAt": "2026-10-03T03:01:00Z", "externalLink": "https://www.tiktok.com/@easy.bosnian/photo/1234567",
            "assets": [{"id": str(i), "mimeType": "image/jpeg", "source": url} for i, url in enumerate(URLS, 1)]}


class BufferTests(unittest.TestCase):
    def test_exact_account_and_automatic_connection_are_required(self):
        buffer = Buffer("fake-test-key", CHANNEL, ORG)
        with patch.object(buffer, "call", return_value={"channel": channel()}):
            self.assertEqual(buffer.verify_channel()["name"], "easy.bosnian")
        bad_values = [("name", "other-account"), ("service", "instagram"), ("organizationId", "wrong"),
                      ("isDisconnected", True), ("isLocked", True), ("isQueuePaused", True),
                      ("metadata", {"defaultToReminders": True}), ("metadata", None), ("scopes", [])]
        for field, value in bad_values:
            actual = channel(); actual[field] = value
            with self.subTest(field=field), patch.object(buffer, "call", return_value={"channel": actual}), self.assertRaises(ValueError):
                buffer.verify_channel()

    def test_caption_only_uses_reviewed_text_and_five_hashtags(self):
        self.assertEqual(caption(record()["package"]), "Reviewed public caption\n\n#one #two #three #four #five")
        package = record()["package"]; package["caption"] = "a" * 2200
        with self.assertRaises(ValueError): caption(package)

    def test_api_creation_is_automatic_and_preserves_three_image_order(self):
        buffer = Buffer("fake-test-key", CHANNEL, ORG)
        with patch.object(buffer, "call", return_value={"createPost": {"__typename": "PostActionSuccess", "post": post()}}) as call:
            buffer.create(caption(record()["package"]), URLS)
            payload = call.call_args.args[1]["input"]
            self.assertEqual(payload["schedulingType"], "automatic")
            self.assertEqual(payload["mode"], "shareNow")
            self.assertFalse(payload["needsApproval"])
            self.assertFalse(payload["saveToDraft"])
            self.assertEqual([a["image"]["url"] for a in payload["assets"]], URLS)
            self.assertNotIn("private_review", str(payload))

    def test_graphql_errors_never_expose_echoed_credentials_or_content(self):
        buffer = Buffer("fake-test-key", CHANNEL, ORG)
        with patch("easybosnian.buffer.request", return_value={"errors": [{"message": "secret answer fake-test-key"}]}) as request:
            with self.assertRaises(RuntimeError) as error: buffer.call("query { account { id } }")
            self.assertNotIn("secret answer", str(error.exception))
            self.assertNotIn("fake-test-key", str(error.exception))
            self.assertEqual(request.call_args.args[1], "https://api.buffer.com")
        with patch.dict(os.environ, {"BUFFER_API_KEY": "fake-test-key"}):
            self.assertNotIn("fake-test-key", redact("Buffer failed with fake-test-key"))

    def test_accepted_or_reminder_posts_do_not_count_as_publication(self):
        buffer = Mock(channel_id=CHANNEL)
        for status in ("scheduled", "sending"):
            actual = post(); actual["status"] = status; actual["externalLink"] = None
            saved = record()
            self.assertFalse(verify_post(buffer, Mock(), DATE, saved, actual))
            self.assertFalse(saved["state"]["platforms"]["tiktok"].get("verified", False))
        for field, value in (("schedulingType", "notification"), ("channelId", "other"), ("text", "mutated"),
                             ("status", "draft"), ("status", "error"),
                             ("externalLink", "https://www.tiktok.com.attacker.test/@easy.bosnian/photo/1234567"),
                             ("externalLink", "https://www.tiktok.com/@other/photo/1234567")):
            actual = post(); actual[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): verify_post(buffer, Mock(), DATE, record(), actual)
        saved = record(); actual = post(); actual["assets"].reverse()
        with self.assertRaises(ValueError): verify_post(buffer, Mock(), DATE, saved, actual)
        saved = record()
        self.assertTrue(verify_post(buffer, Mock(), DATE, saved, post()))
        self.assertTrue(saved["state"]["platforms"]["tiktok"]["verified"])

    def test_capture_requires_exact_submitted_asset_sources_in_order(self):
        actual = post(); actual["assets"][0]["source"] = "https://wrong.test/secret.jpg"
        with self.assertRaises(ValueError): checked_post(Mock(channel_id=CHANNEL), record(), actual, capture=True)

    def test_remote_media_without_optional_ids_uses_exact_source_identity(self):
        actual = post()
        for asset in actual["assets"]: asset["id"] = None
        saved = record(); buffer = Mock(channel_id=CHANNEL)
        checked_post(buffer, saved, actual, capture=True)
        self.assertTrue(verify_post(buffer, Mock(), DATE, saved, actual))
        actual["assets"].reverse()
        with self.assertRaises(ValueError): checked_post(buffer, saved, actual)

    def test_uncertain_submission_without_id_never_submits_again(self):
        saved = record(); saved["state"]["platforms"]["tiktok"].pop("post_id")
        with tempfile.TemporaryDirectory() as temp, patch("easybosnian.buffer.ROOT", Path(temp)), patch("easybosnian.buffer.verify_repository"), patch("easybosnian.buffer.checked_batch", return_value=saved), patch("easybosnian.buffer.Store") as store, patch("easybosnian.buffer.Buffer") as buffer, patch("easybosnian.buffer.failure", return_value="uncertain"), patch.dict(os.environ, ENV):
            store.return_value.call.return_value = {"daily_enabled": True, "daily_authorized": True, "monitoring_ready": True}
            buffer.return_value.verify_channel.return_value = channel(); buffer.return_value.channel_id = CHANNEL
            with self.assertRaises(RuntimeError): pipeline_tiktok(DATE, "live")
            buffer.return_value.create.assert_not_called()

    def test_reconciliation_checks_only_reads_and_refuses_ambiguous_matches(self):
        saved = record(); saved["state"]["platforms"]["tiktok"].pop("post_id")
        buffer = Mock(channel_id=CHANNEL)
        buffer.recent.return_value = {"edges": [{"node": post()}, {"node": post()}], "pageInfo": {"hasNextPage": False}}
        with self.assertRaises(ValueError): reconcile(buffer, Mock(), DATE, saved)
        buffer.create.assert_not_called()
        buffer.recent.return_value = {"edges": [{"node": post()}], "pageInfo": {"hasNextPage": False}}
        buffer.post.return_value = post()
        self.assertTrue(reconcile(buffer, Mock(), DATE, saved))
        buffer.create.assert_not_called()

    def test_intent_is_persisted_before_timed_out_create(self):
        saved = record(); saved["state"]["platforms"]["tiktok"] = {}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for kind in ("quiz", "lesson", "word"): (root / (kind + "-card.jpg")).write_bytes(b"approved card")
            snapshots = []
            store = Mock(); store.save.side_effect = lambda date, value: snapshots.append(copy.deepcopy(value["state"]))
            store.call.return_value = {"daily_enabled": True, "daily_authorized": True, "monitoring_ready": True}
            buffer = Mock(channel_id=CHANNEL); buffer.verify_channel.return_value = channel()
            def timeout(*args):
                self.assertTrue(snapshots[-1]["platforms"]["tiktok"]["publish_intent"])
                self.assertEqual(snapshots[-1]["platforms"]["tiktok"]["image_urls"], URLS)
                raise TimeoutError("outcome uncertain")
            buffer.create.side_effect = timeout
            with patch("easybosnian.buffer.ROOT", root), patch("easybosnian.buffer.verify_repository"), patch("easybosnian.buffer.checked_batch", return_value=saved), patch("easybosnian.buffer.Store", return_value=store), patch("easybosnian.buffer.Buffer", return_value=buffer), patch("easybosnian.buffer.artwork", return_value=root), patch("easybosnian.buffer.request", return_value=b"approved card"), patch("easybosnian.buffer.failure", return_value="uncertain"), patch.dict(os.environ, ENV):
                with self.assertRaises(RuntimeError): pipeline_tiktok(DATE, "live")
            buffer.create.assert_called_once()
            self.assertTrue(saved["state"]["platforms"]["tiktok"]["publish_intent"])
            self.assertNotIn("post_id", saved["state"]["platforms"]["tiktok"])

    def test_accepted_id_resumes_only_readonly_verification(self):
        saved = record()
        buffer = Mock(channel_id=CHANNEL); buffer.verify_channel.return_value = channel(); buffer.post.return_value = post()
        with tempfile.TemporaryDirectory() as temp, patch("easybosnian.buffer.ROOT", Path(temp)), patch("easybosnian.buffer.verify_repository"), patch("easybosnian.buffer.checked_batch", return_value=saved), patch("easybosnian.buffer.Store") as store, patch("easybosnian.buffer.Buffer", return_value=buffer), patch("easybosnian.buffer.artwork") as artwork, patch.dict(os.environ, ENV):
            store.return_value.call.return_value = {"daily_enabled": True, "daily_authorized": True, "monitoring_ready": True}
            self.assertTrue(pipeline_tiktok(DATE, "live")["verified"])
            buffer.create.assert_not_called(); artwork.assert_not_called()

    def test_tiktok_failure_does_not_prevent_verified_instagram_stories(self):
        with tempfile.TemporaryDirectory() as temp, patch("easybosnian.daily.ROOT", Path(temp)), patch("easybosnian.daily.pipeline", return_value={"verified": True}), patch("easybosnian.daily.pipeline_facebook", return_value={"verified": True}) as fb, patch("easybosnian.daily.pipeline_tiktok", side_effect=RuntimeError("Buffer failed")) as tt, patch("easybosnian.daily.pipeline_stories", return_value={"verified": True, "status": "confirmed Stories"}) as stories, patch.dict(os.environ, {**ENV, "FACEBOOK_POSTING_ENABLED": "true", "INSTAGRAM_STORIES_ENABLED": "true"}):
            with self.assertRaises(RuntimeError): daily(DATE, "live")
            fb.assert_called_once(); tt.assert_called_once(); stories.assert_called_once()

    def test_credentials_storage_alone_does_not_arm_tiktok(self):
        with patch("easybosnian.cli.verify_repository"), patch("easybosnian.cli.Buffer") as buffer, patch("easybosnian.cli.gh") as gh, patch("easybosnian.cli.write_json"), patch("builtins.print"):
            buffer.return_value.discover.return_value = channel()
            authorize_buffer("fake-test-key")
            self.assertEqual(gh.call_count, 3)
            self.assertFalse(any("TIKTOK_POSTING_ENABLED" in call.args for call in gh.call_args_list))


if __name__ == "__main__": unittest.main()
