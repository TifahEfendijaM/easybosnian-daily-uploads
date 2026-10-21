"""Beginner captions remain natural, secret-safe and exact across publishers."""
import copy
import unittest
from easybosnian.validate import caption_language,validate
from easybosnian.instagram_poll import instagram_caption,quiz_poll
from easybosnian.facebook import caption as facebook_caption
from easybosnian.buffer import caption as tiktok_caption
from test_run_difficulty_language import fresh
from test_project import reviewed_fixture


class EnglishCaptionTests(unittest.TestCase):
    def test_fresh_caption_language_and_natural_level_are_checked_for_every_level(self):
        for level in ('A1','A2','B1','B2','C1','C2'):
            with self.subTest(level=level):
                package=fresh(level)
                self.assertEqual(caption_language(package),'en' if level in ('A1','A2') else 'bs')
                validate(package,require_language_policy=True,require_caption_level=True,require_website_footer=True)
                for field in (None,'bs' if level in ('A1','A2') else 'en'):
                    bad=copy.deepcopy(package)
                    if field is None:bad.pop('caption_language')
                    else:bad['caption_language']=field
                    with self.assertRaisesRegex(ValueError,'Caption language'):validate(bad,require_language_policy=True)

    def test_actual_retained_levels_control_language_including_mixed_and_unknown_levels(self):
        package=fresh('A1');package['bosnian_level']='C2'
        self.assertEqual(caption_language(package),'en')  # Do not relabel retained A1 copy C2.
        package['words'][1]['bosnian_level']='A2'
        self.assertEqual(caption_language(package),'en')
        package['words'][1]['bosnian_level']='B1'
        self.assertEqual(caption_language(package),'bs')
        with self.assertRaisesRegex(ValueError,'Caption language'):validate(package)
        package=fresh('A2');package['words'][0]['bosnian_level']=None
        package['cards'][0]['question_language']='bs'
        self.assertEqual(caption_language(package),'en')  # Existing unknown-rating target fallback.
        validate(package,require_language_policy=True,require_caption_level=True)
        self.assertIsNone(package['words'][0]['bosnian_level'])
        package['words'][1]['bosnian_level']='B1'
        self.assertEqual(caption_language(package),'bs')  # Unknown ratings cannot hide known advanced content.

    def test_bare_incorrect_and_wrong_language_level_mentions_remain_invalid(self):
        package=fresh('A2')
        for text in ('Level A2','CEFR: A2','Practise conversations at level B2.',
                     'Practise conversations at level A2.\nA2',
                     'Danas vježbamo bosanski na nivou A2.'):
            bad=copy.deepcopy(package);bad['caption']=text+'\nContinue learning on EasyBosnian.\n👉easybosnian.com'
            with self.subTest(text=text),self.assertRaises(ValueError):validate(bad,require_caption_level=True)
        validate(package,require_caption_level=True,require_website_footer=True)

    def test_english_prose_and_website_are_preserved_with_ordered_bosnian_poll_choices(self):
        package=fresh('A1');before=copy.deepcopy(package)
        ig=instagram_caption(package)
        self.assertTrue(ig.startswith('Question of the day: '+package['cards'][0]['question']))
        self.assertNotIn('Pitanje dana:',ig);self.assertTrue(ig.endswith('👉easybosnian.com'))
        for text in (ig,facebook_caption(package),tiktok_caption(package)):
            self.assertIn('Bosnian at level A1',text)
            self.assertIn('Continue learning with free lessons on EasyBosnian.',text)
            self.assertEqual(text.count('easybosnian.com'),1)
        self.assertEqual(list(quiz_poll(package)[0].values()),[x['text'] for x in package['cards'][0]['options']])
        self.assertEqual(package,before)

    def test_english_answer_and_previous_post_leaks_fail_without_rejecting_answer_a_question(self):
        package=fresh('A2')
        for suffix in ('The correct answer is B.','The answer is a.','Answer: B.','Answer:B.','Answer:b.','B is correct.','Answer B.',
                       'A small correction to the previous post.', 'This is a new version of the post.'):
            bad=copy.deepcopy(package);bad['caption']+=' '+suffix
            with self.subTest(suffix=suffix),self.assertRaises(ValueError):validate(bad)
        package['caption']='Practise Bosnian at level A2 and answer a question about rainy days.\nKeep learning with EasyBosnian.\n👉easybosnian.com'
        validate(package,require_caption_level=True,require_website_footer=True)
        ordinary=copy.deepcopy(package);ordinary['caption']=ordinary['caption'].replace('and answer a question about rainy days','with a question whose answer is a word about rainy days')
        validate(ordinary,require_caption_level=True,require_website_footer=True)
        for response in ('yes','no','Da','Ne'):
            bad=copy.deepcopy(package)
            bad['cards'][0]['options']=[{'label':'A','text':'Da'},{'label':'B','text':'Ne'}]
            bad['private_review'].update(correct_option='A',correct_text='Da',answer_aliases=['da'],identifying_hints=['tacno je da'])
            bad['private_review']['quiz_choice_review']['binary']=True
            bad['caption']+=' The answer: '+response+'.'
            with self.subTest(response=response),self.assertRaisesRegex(ValueError,'yes/no answer'):validate(bad)

    def test_legacy_saved_caption_is_readable_without_new_language_metadata(self):
        package=reviewed_fixture();before=copy.deepcopy(package)
        validate(package)
        self.assertTrue(instagram_caption(package).startswith('Pitanje dana: '))
        self.assertEqual(package,before)
