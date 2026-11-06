"""Title-only tint control preserves archived colours and measured readability."""
import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from jsonschema import Draft202012Validator
from easybosnian.visual_placement import CARD_SCHEMA, MODEL_CARD_SCHEMA
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import default_plan,render_hybrid,title_colours,title_text_colour,validate_current_design
from test_project import reviewed_fixture


class TitleColourRichnessTests(unittest.TestCase):
    def test_neutral_direction_and_legacy_colour_for_every_palette(self):
        for palette in read_json(ROOT/'data/design-palettes.json').values():
            for tone,light in (('paper_ink',True),('accent_dark',True),('ink_paper',False),('accent_light',False)):
                original,backing=title_colours(palette,tone)
                softened,new_backing=title_colours(palette,tone,35)
                self.assertEqual(original,title_colours(palette,tone,100)[0])
                self.assertEqual(new_backing[0][1],backing[0][1])
                for old,new in zip(bytes.fromhex(original[0][1:]),bytes.fromhex(softened[0][1:])):
                    self.assertLessEqual(abs((255 if light else 0)-new),abs((255 if light else 0)-old))
        for value in (True,19,101,35.5,'35'):
            with self.assertRaises(ValueError):
                title_text_colour('#335577',value,light=True)

    def test_fresh_floor_for_both_tones_preserves_older_tints(self):
        card = reviewed_fixture()['cards'][2]
        field = MODEL_CARD_SCHEMA['properties']['heading_richness']
        for tone in ('accent_dark', 'ink_paper'):
            plan = dict(default_plan(card), heading_tone=tone)
            for richness in (20, 39, 40, 45, 100):
                with self.subTest(tone=tone, richness=richness):
                    plan['heading_richness'] = richness
                    Draft202012Validator(CARD_SCHEMA).validate(plan)
                    self.assertEqual(Draft202012Validator(field).is_valid(richness), richness >= 40)
                    if richness < 40:
                        with self.assertRaisesRegex(ValueError, 'title colour richness'):
                            validate_current_design(card, plan)
                    else:
                        validate_current_design(card, plan)

    def test_render_softens_only_title_and_keeps_archived_omission_exact(self):
        card=copy.deepcopy(reviewed_fixture()['cards'][2])
        plan=dict(default_plan(card),heading_tone='accent_dark')
        plan['blocks'][-1]['photo_tone']='paper_dark'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);photo=root/'photo.jpg'
            Image.new('RGB',(1080,1350),'#444444').save(photo)
            old=render_hybrid(card,'gold-cream',photo,root/'old.jpg',plan)
            legacy=copy.deepcopy(plan);legacy.pop('heading_richness')
            render_hybrid(card,'gold-cream',photo,root/'legacy.jpg',legacy)
            self.assertEqual((root/'old.jpg').read_bytes(),(root/'legacy.jpg').read_bytes())
            revised=copy.deepcopy(plan);revised['heading_richness']=35
            new=render_hybrid(card,'gold-cream',photo,root/'new.jpg',revised)
            self.assertNotEqual(new['heading_colour'],old['heading_colour'])
            self.assertEqual(new['composition']['blocks'],old['composition']['blocks'])
            self.assertEqual(new['example_colour'],old['example_colour'])
            self.assertGreaterEqual(new['heading_contrast'],3)
            with Image.open(root/'old.jpg') as a,Image.open(root/'new.jpg') as b:
                self.assertEqual(a.crop((0,500,1080,1350)).tobytes(),b.crop((0,500,1080,1350)).tobytes())
