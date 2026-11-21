import json
import unittest
from unittest.mock import Mock

from easybosnian.custom_instructions import resolve
from easybosnian.selection import (REDESIGN, frozen_kinds, retained_copy_kinds,
                                  reused_kinds, selection_context)
from test_project import reviewed_fixture


class CustomInstructionTests(unittest.TestCase):
    def model(self, **overrides):
        return Mock(return_value=json.dumps({
            kind: dict(zip(('action', 'word'), overrides.get(kind, ('unchanged', None))))
            for kind in ('quiz', 'lesson', 'word')
        }))

    def test_design_direction_unfreezes_only_the_affected_render(self):
        previous = reviewed_fixture()
        model = self.model(word=('redesign', None))
        choice, words, actions = resolve('Riječ dana: use a dark plum PRIMJER shade.',
                                         'custom', ['', '', ''], ['same_image&design'] * 3, previous, model)
        self.assertEqual(actions, ['same_image&design', 'same_image&design', REDESIGN])
        self.assertTrue(model.call_args.kwargs['read_only'])
        selection = selection_context({'days': [{'date': previous['date'], 'content': previous}]},
                                      previous['date'], choice, custom_words=words, custom_actions=actions)
        self.assertEqual(reused_kinds(selection), ('quiz', 'lesson', 'word'))
        self.assertEqual(retained_copy_kinds(selection), ('quiz', 'lesson', 'word'))
        self.assertEqual(frozen_kinds(selection), ('quiz', 'lesson'))

    def test_explicit_photo_or_word_choice_overrides_reuse_for_one_card(self):
        model = self.model(quiz=('fresh_photo', None), word=('entered', 'prozor'))
        self.assertEqual(resolve('New quiz photo. Use prozor for Riječ dana.', 'same_images',
                                 None, None, reviewed_fixture(), model),
                         ('custom', ['', '', 'prozor'], ['keep_today', 'same_image', 'entered']))

    def test_blank_ambiguous_and_invented_word_preserve_original_choices(self):
        actions = ['keep_today'] * 3
        model = self.model()
        self.assertEqual(resolve('', 'custom', None, actions, None, model), ('custom', None, actions))
        model.assert_not_called()
        self.assertEqual(resolve('maybe...', 'custom', None, actions, None, model), ('custom', None, actions))
        wrong = self.model(word=('entered', 'prozor'))
        self.assertEqual(resolve('maybe...', 'custom', None, actions, None, wrong), ('custom', None, actions))
