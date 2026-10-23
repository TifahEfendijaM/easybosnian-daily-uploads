"""Palette additions must reach preparation/review and real feed/Story renderers."""
import copy
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from easybosnian.core import ROOT,read_json
from easybosnian.hybrid import default_plan,render_hybrid
from easybosnian.render import contrast
from easybosnian.stories import artwork_palette
from easybosnian.story_layouts import tall_story_image
from easybosnian.validate import validate
from easybosnian.visual_diagnostics import select_palette
from easybosnian.visual_history import accepted_choices,palette_policies
from easybosnian.visual_placement import MODEL_CARD_SCHEMA
from easybosnian.visual_policy import apply_policy
from test_project import reviewed_fixture

NEW_PALETTES=('burgundy-oat','olive-stone','indigo-mist','copper-linen',
    'teal-seaglass','aubergine-apricot','espresso-almond','graphite-chalk',
    'cobalt-peach','ochre-parchment','pine-rose',
    'royal-blue-sun','emerald-lime','ruby-cream','violet-citrus','ocean-tangerine',
    'magenta-porcelain','scarlet-vanilla','peacock-coral','sapphire-lime',
    'grape-lemon','paprika-aqua','ultramarine-orchid')


class ExpandedPaletteCatalogueTests(unittest.TestCase):
    def test_preparation_review_and_repeat_policy_share_the_approved_registry(self):
        catalogue=read_json(ROOT/'data/design-palettes.json')
        self.assertTrue(set(NEW_PALETTES)<=set(catalogue))
        self.assertEqual(set(read_json(ROOT/'data/content.schema.json')['properties']['design_palette']['enum']),set(catalogue))
        self.assertEqual(set(MODEL_CARD_SCHEMA['properties']['palette']['enum']),set(catalogue))
        self.assertEqual(set(palette_policies([])),set(catalogue))
        package=reviewed_fixture()
        for name,palette in catalogue.items():
            with self.subTest(palette=name):
                self.assertEqual(set(palette),{'ink','panel','accent','scrim'})
                self.assertTrue(all(re.fullmatch(r'#[0-9a-f]{6}',c) for c in palette.values()))
                for background in (palette['panel'],palette['accent'],'#ffffff'):
                    self.assertGreaterEqual(contrast(palette['ink'],background),4.5)
                package['design_palette']=name;validate(package)
                selected,outcome=select_palette({'palette':name},'gold-cream')
                self.assertEqual(selected,name);self.assertEqual(outcome['source'],'chatgpt')
        _,outcome=select_palette({'palette':'unapproved-custom-colours'},'gold-cream')
        self.assertEqual(outcome['source'],'fallback')

    def test_each_new_palette_renders_with_opaque_panels_and_carries_to_stories(self):
        catalogue=read_json(ROOT/'data/design-palettes.json');package=reviewed_fixture()
        card=package['cards'][2];source=copy.deepcopy(card)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);photo=root/'background.jpg';Image.new('RGB',(1080,1350),'#777777').save(photo)
            for name in NEW_PALETTES:
                with self.subTest(palette=name):
                    plan=default_plan(card);plan.update(palette=name,heading_tone='accent_dark',category_style='ribbon')
                    plan['blocks'][-1]['photo_tone']='paper_ink'
                    plan=apply_policy(plan,panel_opacity=100)
                    feed=root/f'{name}-post.jpg';story=root/f'{name}-story.jpg'
                    rendered=render_hybrid(card,name,photo,feed,plan)
                    self.assertGreaterEqual(rendered['heading_contrast'],3)
                    self.assertGreaterEqual(rendered['body_contrast'],4.5)
                    self.assertGreaterEqual(rendered['example_contrast'],4.5)
                    self.assertEqual(rendered['composition'],plan)
                    palette=artwork_palette(package,{'word':{'metrics':rendered}},'word')
                    self.assertEqual(palette,catalogue[name])
                    result=tall_story_image(card,photo,story,palette,category_style='ribbon')
                    self.assertEqual(result['size'],[1080,1920])
                    self.assertGreaterEqual(result['example_contrast'],4.5)
                    self.assertEqual(card,source)
                    accepted={**rendered,'status':'accepted','palette_outcome':{'source':'chatgpt'}}
                    self.assertEqual(accepted_choices({'cards':{'word':accepted}})['word']['palette'],name)
                    with Image.open(feed) as image:self.assertEqual(image.size,(1080,1350))
                    with Image.open(story) as image:self.assertEqual(image.size,(1080,1920))
