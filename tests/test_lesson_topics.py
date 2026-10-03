"""Lesson titles and comparison seeds obey the existing safety/fit contracts."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from easybosnian.core import ROOT
from easybosnian.render import render
from easybosnian.selection import check_selection, selection_context
from easybosnian.story_layouts import tall_story_image
from easybosnian.validate import validate
from test_project import reviewed_fixture


class LessonTopicTests(unittest.TestCase):
    def comparison(self):
        package = reviewed_fixture()
        package['words'][1] = {'lemma': 'peći / kuhati',
                              'equivalence_keys': ['peći', 'kuhati', 'bake', 'cook'],
                              'bosnian_level': 'A2'}
        package['cards'][1].update(word='peći / kuhati', heading='Peći ili kuhati?',
            body='Uporedi ova dva glagola i razmisli o tome kako pripremaš ručak.',
            example='Danas pripremam ručak za porodicu.')
        return package

    def test_custom_comparison_keeps_entered_seed_with_independent_heading(self):
        package = self.comparison()
        old = reviewed_fixture()
        history = {'days': [{'date': old['date'], 'content': old}]}
        selected = selection_context(history, old['date'], 'custom',
            custom_words=['', 'peći / kuhati', ''],
            custom_actions=['keep_today', 'entered', 'keep_today'])
        # A custom draft must still refresh all public instructional copy/prompts.
        package['caption'] += ' Probaj novu rečenicu.'
        for card in package['cards']:
            if card['kind'] == 'quiz': card['question'] = 'Koji predmet biramo za zaštitu od kiše?'
            elif card['kind'] == 'word': card['body'] = 'Kap je mala, zaobljena količina tečnosti.'
            card['background_prompt'] = card['background_prompt'].replace('Natural', 'Gentle natural').replace('Gentle', 'Soft')
        check_selection(package, selected)
        validate(package)

    def test_lesson_topic_heading_allowed_but_word_heading_still_bound(self):
        package = reviewed_fixture()
        package['cards'][1]['heading'] = 'Šta se krije u oblacima?'
        validate(package)
        package['cards'][2]['heading'] = 'Nešto drugo'
        with self.assertRaisesRegex(ValueError, 'Featured heading'):
            validate(package)

    def test_comparison_does_not_bypass_answer_secrecy_or_history(self):
        package = self.comparison()
        bad = copy.deepcopy(package)
        bad['cards'][1]['heading'] = 'Kišobran ili kabanica?'
        with self.assertRaisesRegex(ValueError, 'leaks'):
            validate(bad)
        previous = reviewed_fixture()
        previous['date'] = '2026-10-01'
        previous['words'][1] = {'lemma': 'kuhati', 'equivalence_keys': ['cook']}
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(package, {'days': [{'date': previous['date'], 'content': previous}]})

    def test_comparison_heading_renders_with_exact_copy_in_feed_and_story(self):
        package = self.comparison(); card = package['cards'][1]
        original = copy.deepcopy(card)
        palette = json.loads((ROOT / 'data/design-palettes.json').read_text())[package['design_palette']]
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); background = folder / 'background.jpg'
            Image.new('RGB', (1080, 1350), '#536777').save(background)
            render(card, package['design_palette'], background, folder / 'feed.jpg')
            tall_story_image(card, background, folder / 'story.jpg', palette)
            with Image.open(folder / 'feed.jpg') as feed: self.assertEqual(feed.size, (1080, 1350))
            with Image.open(folder / 'story.jpg') as story: self.assertEqual(story.size, (1080, 1920))
        self.assertEqual(card, original)


if __name__ == '__main__': unittest.main()
