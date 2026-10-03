import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from easybosnian.core import ROOT, read_json
from easybosnian.render import draw_rows, render
from easybosnian.story_layouts import tall_story_image, visual_quiz_image
from easybosnian.stories import story_image
from easybosnian.validate import validate
from test_project import reviewed_fixture


class StoryLayoutTests(unittest.TestCase):
    def setUp(self):
        self.package=reviewed_fixture()
        self.palette=read_json(ROOT/'data/design-palettes.json')['blue-ice']
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.photo=self.root/'photo.jpg'
        Image.new('RGB',(1200,800),'#648699').save(self.photo)
        self.card=self.root/'card.jpg';Image.new('RGB',(1080,1350),'#345678').save(self.card)

    def test_word_and_lesson_stories_preserve_exact_copy_and_the_complete_photo(self):
        for card in self.package['cards'][1:]:
            with patch('easybosnian.story_layouts.draw_rows',wraps=draw_rows) as drawing:
                metrics=story_image(self.card,self.root/'story.jpg',self.palette,self.photo,card)
            text=[' '.join(call.args[2]) for call in drawing.call_args_list]
            self.assertIn(card['heading'],text);self.assertIn(card['body'],text)
            if card.get('example'):self.assertIn(card['example'],text);self.assertIn('PRIMJER',text)
            self.assertFalse(metrics['photo_cropped'])
            self.assertAlmostEqual(metrics['photo_size'][0]/metrics['photo_size'][1],1.5,places=2)
            self.assertLessEqual(metrics['panel_bounds'][-1][3],1650)
            with Image.open(self.root/'story.jpg') as image:self.assertEqual(image.size,(1080,1920))

    def test_only_explicit_visual_naming_quizzes_use_b_in_feed_and_stories(self):
        card=copy.deepcopy(self.package['cards'][0]);card['question']='Kako se zove predmet na slici?'
        for format in ('other',None):
            if format:card['quiz_format']=format
            else:card.pop('quiz_format',None)
            with patch('easybosnian.stories.tall_story_image') as tall:
                story_image(self.card,self.root/'story.jpg',self.palette,self.photo,card)
                tall.assert_not_called()
            with patch('easybosnian.story_layouts.visual_quiz_image') as tall:
                render(card,'blue-ice',self.photo,self.root/'feed.jpg');tall.assert_not_called()
        card['quiz_format']='visual_identification'
        for count in (2,3,4):
            card['options']=[{'label':letter,'text':text} for letter,text in zip('ABCD',['torba','kišobran','knjiga','šešir'])][:count]
            for height in (1350,1920):
                output=self.root/f'{count}-{height}.jpg'
                metrics=render(card,'blue-ice',self.photo,output) if height==1350 else story_image(self.card,output,self.palette,self.photo,card)
                self.assertEqual(metrics['treatment'],'B');self.assertEqual(len(metrics['panel_bounds']),count)
                self.assertFalse(metrics['photo_cropped'])
                with Image.open(output) as image:self.assertEqual(image.size,(1080,height))

    def test_regular_word_and_lesson_posts_keep_their_existing_renderer(self):
        for card in self.package['cards'][1:]:
            with patch('easybosnian.story_layouts.visual_quiz_image') as visual,patch('easybosnian.story_layouts.tall_story_image') as tall:
                result=render(card,'blue-ice',self.photo,self.root/'feed.jpg')
            visual.assert_not_called();tall.assert_not_called();self.assertEqual(result['size'],[1080,1350])

    def test_new_quiz_classification_required_but_legacy_history_stays_valid(self):
        p=self.package;validate(p)
        with self.assertRaisesRegex(ValueError,'metadata'):validate(p,require_quiz_format=True)
        p['cards'][0]['quiz_format']='other';validate(p,require_quiz_format=True)
        p['cards'][0]['quiz_format']='visual_identification';validate(p,require_quiz_format=True)
        p['cards'][0]['quiz_format']='guess';
        with self.assertRaises(ValueError):validate(p)

    def test_bad_contrast_missing_photo_and_excess_copy_fail_without_truncating(self):
        card=copy.deepcopy(self.package['cards'][2]);original=copy.deepcopy(card)
        with self.assertRaises(ValueError):tall_story_image(card,None,self.root/'bad.jpg',self.palette)
        bad_palette={**self.palette,'ink':self.palette['panel']}
        with self.assertRaises(ValueError):tall_story_image(card,self.photo,self.root/'bad.jpg',bad_palette)
        self.assertEqual(card,original)
        card['body']='Čć šž đak. '*120
        with self.assertRaisesRegex(ValueError,'without truncation'):tall_story_image(card,self.photo,self.root/'bad.jpg',self.palette)
        self.assertTrue(card['body'].endswith('Čć šž đak. '))

    def test_story_body_density_retains_measured_font_tiers(self):
        card=copy.deepcopy(self.package['cards'][1]);card.pop('example',None)
        for length,size in ((160,44),(161,38),(240,38),(241,34)):
            card['body']=('Čć šž đak. '*30)[:length].rstrip()
            # Set exact boundary length without unbreakable long tokens.
            card['body'] += 'a'*(length-len(card['body']))
            result=tall_story_image(card,self.photo,self.root/'story.jpg',self.palette)
            self.assertEqual(result['body_font_size'],size)
