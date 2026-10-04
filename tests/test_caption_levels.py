import unittest

from easybosnian.validate import caption_levels,validate
from test_project import reviewed_fixture


class CaptionLevelTests(unittest.TestCase):
    def package(self,levels=('B2','B2','B2')):
        package=reviewed_fixture();package['bosnian_level']='C2'
        for word,level in zip(package['words'],levels):word['bosnian_level']=level
        return package

    def test_natural_level_mentions_match_actual_retained_copy_not_new_global_setting(self):
        p=self.package();p['caption']+=' Kroz svakodnevne situacije danas vježbamo bosanski na nivou B2.'
        validate(p,require_caption_level=True)
        p['caption']=p['caption'].replace('B2','C2')
        with self.assertRaises(ValueError):validate(p,require_caption_level=True)

    def test_mixed_word_levels_use_a_truthful_range(self):
        p=self.package(('A1','B1','C2'))
        self.assertEqual(caption_levels(p),['A1','C2'])
        p['caption']+=' Današnji primjeri povezuju gradivo od nivoa A1 do C2.'
        validate(p,require_caption_level=True)
        p['caption']=p['caption'].replace('A1','A2')
        with self.assertRaises(ValueError):validate(p,require_caption_level=True)

    def test_missing_abrupt_and_incorrect_labels_are_rejected_only_for_fresh_content(self):
        for suffix in ('','\nNivo B2','\nNivo: B2.',' Ova vježba je prilagođena nivou A2.'):
            p=self.package();p['caption']+=suffix
            validate(p)
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):validate(p,require_caption_level=True)

    def test_unrated_legacy_words_use_the_shared_target_without_inventing_word_ratings(self):
        p=self.package((None,None,None));before=[word['bosnian_level'] for word in p['words']]
        self.assertEqual(caption_levels(p),['C2'])
        p['caption']+=' Učite bosanski na nivou C2? Provjerite svoje razumijevanje svakodnevnih izraza.'
        validate(p,require_caption_level=True)
        self.assertEqual([word['bosnian_level'] for word in p['words']],before)

    def test_bare_level_line_is_rejected_even_alongside_a_natural_sentence(self):
        p=self.package();p['caption']+=' Učite bosanski na nivou B2?\nB2'
        with self.assertRaises(ValueError):validate(p,require_caption_level=True)
