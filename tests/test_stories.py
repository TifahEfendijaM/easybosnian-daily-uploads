import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from easybosnian.stories import story_image, verify_story, pipeline_stories, HIGHLIGHTS


class StoriesTests(unittest.TestCase):
    def test_story_keeps_every_published_slide_pixel_and_watermark_inside_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "slide.jpg"; result = Path(folder) / "story.jpg"
            Image.new("RGB", (1080, 1350), "#244466").save(source)
            story_image(source, result, {"panel": "#ffffff"})
            with Image.open(result) as image:
                self.assertEqual(image.size, (1080, 1920))
                self.assertTrue(all(c > 245 for c in image.getpixel((500, 100))))
                for x, y in ((5, 300), (500, 900), (1065, 1610)):
                    self.assertLess(sum(abs(a-b) for a, b in zip(image.getpixel((x, y)), (36, 68, 102))), 12)

    def test_story_verification_requires_owned_published_story_and_permalink(self):
        ig = Mock()
        actual = {"id": "55", "media_type": "IMAGE", "media_product_type": "STORY", "permalink": "https://www.instagram.com/stories/easy_bosnian/55/"}
        ig.story_media.return_value = actual
        ig.stories.return_value = {"data": [{"id": "55"}]}
        item = {"media_id": "55"}
        verify_story(ig, item)
        self.assertTrue(item["verified"])
        for key, value in (("media_product_type", "FEED"), ("permalink", "https://example.com/55"), ("id", "other")):
            ig.story_media.return_value = {**actual, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError): verify_story(ig, {"media_id": "55"})
        ig.story_media.return_value = actual
        ig.stories.return_value = {"data": []}
        with self.assertRaises(ValueError): verify_story(ig, {"media_id": "55"})

    def test_stories_wait_for_actual_feed_publication(self):
        record = {"state": {}}
        with patch("easybosnian.stories.verify_repository"), patch("easybosnian.stories.checked_batch", return_value=record), patch("easybosnian.stories.Store"), patch("easybosnian.stories.Instagram") as ig, patch("easybosnian.stories.failure", return_value="feed not published"):
            with self.assertRaises(RuntimeError): pipeline_stories("2026-10-03", "live")
            ig.assert_not_called()

    def test_uncertain_story_does_not_send_another_publish_request(self):
        record = {"package": {"design_palette": "blue-ice", "cards": [{"kind": "quiz"}]}, "state": {"verified": True, "platforms": {"instagram_stories": {"publish_intent": True, "cards": {"quiz": {"publish_intent": True}}}}}}
        with patch("easybosnian.stories.verify_repository"), patch("easybosnian.stories.checked_batch", return_value=record), patch("easybosnian.stories.Store") as store, patch("easybosnian.stories.Instagram") as ig, patch("easybosnian.stories.artwork"), patch("easybosnian.stories.failure", return_value="uncertain"), patch.dict(os.environ, {"INSTAGRAM_STORIES_ENABLED": "true"}):
            store.return_value.call.return_value = {"daily_enabled": True, "daily_authorized": True, "monitoring_ready": True}
            with self.assertRaises(RuntimeError): pipeline_stories("2026-10-03", "live")
            ig.return_value.publish.assert_not_called()
            ig.return_value.story.assert_not_called()

    def test_highlight_mapping_is_explicit_and_no_answer_is_exported(self):
        self.assertEqual(HIGHLIGHTS, {"quiz": "Pitanje dana", "lesson": "Znaš li?", "word": "Riječ dana"})


if __name__ == "__main__": unittest.main()
