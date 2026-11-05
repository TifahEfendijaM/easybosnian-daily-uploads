import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from easybosnian.core import ROOT, read_json
from easybosnian.render import draw_rows
from easybosnian.hybrid import render_hybrid as render
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

    def test_story_examples_are_exact_true_italic_unboxed_footers_for_all_palettes(self):
        from easybosnian.core import read_json
        from easybosnian.render import font
        from easybosnian.hybrid import serif
        for palette in read_json(ROOT/'data/design-palettes.json').values():
            card=copy.deepcopy(self.package['cards'][2]);before=copy.deepcopy(card)
            with patch('easybosnian.story_layouts.draw_rows',wraps=draw_rows) as drawing:
                metrics=tall_story_image(card,self.photo,self.root/'story.jpg',palette)
            example_call=next(call for call in drawing.call_args_list if ' '.join(call.args[2])==card['example'])
            self.assertTrue(str(example_call.args[3].path).endswith('Lora-Italic.ttf'))
            self.assertEqual(card,before);self.assertEqual(len(metrics['panel_bounds']),1)
            self.assertIn('Italic',metrics['example_style']);self.assertGreaterEqual(metrics['example_contrast'],4.5)
            self.assertGreater(metrics['example_bounds'][1],metrics['panel_bounds'][0][3])
            self.assertLessEqual(metrics['example_bounds'][3],1650)
            rule=metrics['example_rule_bounds']
            label_call=next(call for call in drawing.call_args_list if call.args[2]==['PRIMJER'])
            self.assertGreater(rule[1],metrics['panel_bounds'][0][3])
            self.assertLess(rule[3],label_call.args[1][1])
            self.assertEqual((rule[0],rule[2]),(64,1016))
            with Image.open(self.root/'story.jpg') as rendered:
                pixel=rendered.getpixel((540,rule[1]))
            accent=tuple(int(palette['accent'][i:i+2],16) for i in (1,3,5))
            self.assertLessEqual(max(abs(a-b) for a,b in zip(pixel,accent)),12)
            # The example's right padding is bare page colour, never a white panel.
            with Image.open(self.root/'story.jpg') as image:
                sample=image.getpixel((1000,metrics['example_bounds'][1]+5))
                paper=tuple(int(palette['panel'][i:i+2],16) for i in (1,3,5))
                self.assertTrue(all(abs(a-b)<=3 for a,b in zip(sample,paper)))

    def test_only_explicit_visual_naming_quizzes_use_b_in_feed(self):
        card=copy.deepcopy(self.package['cards'][0]);card['question']='Kako se zove predmet na slici?'
        for format in ('other',None):
            if format:card['quiz_format']=format
            else:card.pop('quiz_format',None)
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
                self.assertLessEqual(metrics['question_bounds'][3],metrics['photo_bounds'][1])
                self.assertLess(metrics['photo_bounds'][3],metrics['panel_bounds'][0][1])
                with Image.open(output) as image:self.assertEqual(image.size,(1080,height))

    def test_every_quiz_story_uses_b_with_question_above_complete_photo_and_exact_choices(self):
        for format in ('other','visual_identification',None):
            for count in (2,3,4):
                card=copy.deepcopy(self.package['cards'][0]);card['question']='Koji je odgovor tačan?'
                if format:card['quiz_format']=format
                else:card.pop('quiz_format',None)
                texts=['Da','Ne'] if count==2 else ['torba','kišobran','knjiga','šešir'][:count]
                card['options']=[{'label':letter,'text':text} for letter,text in zip('ABCD',texts)]
                before=copy.deepcopy(card)
                with patch('easybosnian.story_layouts.draw_rows',wraps=draw_rows) as drawing:
                    metrics=story_image(self.card,self.root/'story.jpg',self.palette,self.photo,card)
                rendered=[' '.join(call.args[2]) for call in drawing.call_args_list]
                self.assertIn(card['question'],rendered)
                for text in texts:self.assertIn(text,rendered)
                self.assertEqual(card,before);self.assertEqual(metrics['treatment'],'B')
                self.assertEqual(len(metrics['panel_bounds']),count);self.assertFalse(metrics['photo_cropped'])
                self.assertAlmostEqual(metrics['photo_size'][0]/metrics['photo_size'][1],1.5,places=2)
                self.assertLessEqual(metrics['question_bounds'][3],metrics['photo_bounds'][1])
                self.assertLess(metrics['photo_bounds'][3],metrics['panel_bounds'][0][1])
                with Image.open(self.root/'story.jpg') as image:self.assertEqual(image.size,(1080,1920))

    def test_nonvisual_quiz_cannot_use_the_visual_feed_entry_and_bad_story_copy_fails_without_changes(self):
        card=copy.deepcopy(self.package['cards'][0]);card['quiz_format']='other'
        with self.assertRaises(ValueError):visual_quiz_image(card,self.photo,self.root/'feed.jpg',self.palette,height=1350)
        with self.assertRaises(ValueError):story_image(self.card,self.root/'story.jpg',self.palette,None,card)
        bad_palette={**self.palette,'ink':self.palette['panel']}
        with self.assertRaises(ValueError):story_image(self.card,self.root/'story.jpg',bad_palette,self.photo,card)
        card['question']='Čć šž đak. '*70;before=copy.deepcopy(card)
        with self.assertRaises(ValueError):story_image(self.card,self.root/'story.jpg',self.palette,self.photo,card)
        self.assertEqual(card,before)

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

    def test_stories_retain_feed_category_surface_and_lettering_for_every_card_kind(self):
        from easybosnian.hybrid import category_label
        from easybosnian.designs import category_colours
        from easybosnian.stories import story_category_options
        for card in self.package['cards']:
            for style in ('rounded','pill','ribbon','outlined','tab'):
                for tone in ('ink_secondary','paper_ink'):
                    with self.subTest(kind=card['kind'],style=style,tone=tone):
                        feed=Image.new('RGBA',(1080,1350),'#666666')
                        from easybosnian.render import LABELS
                        category=category_label(feed,LABELS[card['kind']],self.palette,style,tone=tone)
                        metrics={'category_style':style,'category_colour':category['colour'],
                                 'composition':{'category_tone':tone}}
                        result=story_image(self.card,self.root/'story.jpg',self.palette,self.photo,card,
                                           **story_category_options(metrics))
                        self.assertEqual(result['category_tone'],tone)
                        self.assertEqual(result['category_colour'],category['colour'])
                        self.assertIsNone(result['category_support'])
                        _,surface=category_colours(self.palette,tone,style)
                        expected=tuple(int(surface[i:i+2],16) for i in (1,3,5))
                        with Image.open(self.root/'story.jpg') as story:
                            actual=story.getpixel((80,211))
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),4)

    def test_unboxed_story_retains_resolved_light_feed_lettering_with_local_solid_support(self):
        from easybosnian.hybrid import category_label
        from easybosnian.render import LABELS
        from easybosnian.stories import story_category_options
        label=LABELS['word'];feed=Image.new('RGBA',(1080,1350),'#111111')
        accepted=category_label(feed,label,self.palette,'underlined')
        self.assertEqual(accepted['colour'],self.palette['panel'])
        options=story_category_options({'category_style':'underlined','category_colour':accepted['colour'],
                                        'composition':{'category_tone':'auto'}})
        result=story_image(self.card,self.root/'story.jpg',self.palette,self.photo,self.package['cards'][2],**options)
        self.assertEqual(result['category_colour'],accepted['colour'])
        self.assertEqual(result['category_support'],self.palette['ink'])
        with Image.open(self.root/'story.jpg') as story:
            # Only the label gains contrast support; the surrounding page remains exact paper.
            for xy,colour in (((60,205),self.palette['ink']),((540,175),self.palette['panel'])):
                actual=story.getpixel(xy);expected=tuple(int(colour[i:i+2],16) for i in (1,3,5))
                self.assertLessEqual(max(abs(a-b) for a,b in zip(actual,expected)),5)

    def test_unprepared_story_receives_final_category_choices_but_saved_story_stays_exact(self):
        from easybosnian.stories import prepared_story
        from unittest.mock import Mock
        metrics={'category_style':'ribbon','category_colour':self.palette['ink'],
                 'composition':{'category_tone':'ink_secondary'}}
        asset={'path':self.card,'background_path':self.photo,'metrics':metrics}
        renderer=Mock();path=self.root/'new-story.jpg'
        prepared_story(asset,path,self.palette,self.package['cards'][2],renderer)
        self.assertEqual(renderer.call_args.kwargs,{'category_style':'ribbon','category_tone':'ink_secondary',
                                                   'category_colour':self.palette['ink']})
        saved=self.root/'saved-story.jpg';Image.new('RGB',(1080,1920),'#abcd12').save(saved)
        asset['story_path']=saved;renderer.reset_mock()
        prepared_story(asset,path,self.palette,self.package['cards'][2],renderer)
        renderer.assert_not_called();self.assertEqual(path.read_bytes(),saved.read_bytes())
