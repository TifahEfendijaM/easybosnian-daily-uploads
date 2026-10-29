"""The local policy draft reaches the visual reviewer without weakening safeguards."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from easybosnian.visual_placement import review_compositions
import test_visual_provenance as harness

class PaletteSelectionReviewTests(unittest.TestCase):
    def test_similarity_brightness_and_surface_independence_are_in_the_live_task(self):
        h=harness.VisualProvenanceTests();h.setUp();proposal=h.proposal(h.package)
        with patch('easybosnian.cloud_prepare.run_codex',return_value=json.dumps(proposal)) as model:
            review_compositions(h.package,{c['kind']:{'sheet':Path(c['kind']+'.jpg')} for c in h.package['cards']})
        prompt=model.call_args.args[0]
        for phrase in ('SAME limits COLLECTIVELY to visually SIMILAR palettes',
                       'renaming the palette or switching to a near-duplicate',
                       'Sharing one hue or merely both being light/dark is NOT enough',
                       'consider light and dark surfaces EQUALLY',
                       'ONLY when the light and dark alternatives work EQUALLY WELL',
                       'Do not sacrifice ANY better fit for brightness variety',
                       'NEVER favour or lighten/darken the panel',
                       'Quiz-specific surface rules still take precedence',
                       'no_other_suitable_palette'):
            self.assertIn(phrase,prompt)

    def test_current_high_opacity_surfaces_count_but_missing_or_old_low_opacity_stay_unknown(self):
        from easybosnian.visual_history import panel_theme
        for value in (90,95,100):
            card={'palette':'forest-cream','composition':{'blocks':[{'role':'body','style':'rounded','panel_tone':'paper_ink','panel_opacity':value}]}}
            self.assertEqual(panel_theme(card),'dark')
            card['composition']['blocks'][0]['panel_tone']='ink_paper'
            self.assertEqual(panel_theme(card),'light')
        for value in (None,85,101,True):
            card={'palette':'forest-cream','composition':{'blocks':[{'role':'body','style':'rounded','panel_tone':'paper_ink','panel_opacity':value}]}}
            self.assertEqual(panel_theme(card),'unknown')
