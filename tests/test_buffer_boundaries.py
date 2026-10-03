import os
import unittest
from unittest.mock import patch
from easybosnian.buffer import Buffer
from easybosnian.http import redact
CHANNEL="a"*24
ORG="b"*24
POST="c"*24
URLS=["https://project.test/"+kind+".jpg" for kind in ("quiz","lesson","word")]

def channel():
    return {"id": CHANNEL, "organizationId": ORG, "serviceId": "confirmed-tiktok-account", "name": "easy.bosnian",
            "service": "tiktok", "isDisconnected": False, "isLocked": False, "isQueuePaused": False,
            "metadata": {"defaultToReminders": False}, "scopes": ["user.info.basic", "user.info.username", "video.publish", "video.list"]}


class BufferBoundaryTests(unittest.TestCase):
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

    def test_api_creation_is_automatic_and_preserves_three_image_order(self):
        buffer = Buffer("fake-test-key", CHANNEL, ORG)
        with patch.object(buffer, "call", return_value={"createPost": {"__typename": "PostActionSuccess", "post": {"id":POST}}}) as call:
            buffer.create("Reviewed caption", URLS)
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
