"""Parse real workflow files so menu punctuation cannot disable dispatch."""
import unittest
import yaml
from easybosnian.core import ROOT


class WorkflowSyntaxTests(unittest.TestCase):
    def test_every_workflow_parses_as_yaml_with_jobs_and_triggers(self):
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            with self.subTest(workflow=path.name):
                document=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
                self.assertIsInstance(document,dict)
                self.assertIsInstance(document['jobs'],dict)
                self.assertIn('on',document)

    def test_rerun_form_has_explicit_modes_and_custom_only_word_actions(self):
        document=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
        inputs=document['on']['workflow_dispatch']['inputs']
        self.assertNotIn('tiktok_previous_removed',inputs)
        self.assertNotIn('TIKTOK_PREVIOUS_REMOVED',document['jobs']['run']['env'])
        self.assertEqual(inputs['mode']['options'],['verify','preview','daily'])
        self.assertEqual(inputs['content_selection']['options'],['same_words','same_images','same_theme','new','custom'])
        self.assertEqual(inputs['batch_target']['options'],['latest','none','all_today'])
        self.assertEqual(inputs['batch_target']['default'],'latest')
        self.assertLessEqual(len(inputs),25)
        self.assertEqual(inputs['difficulty']['options'],['random','A1','A2','B1','B2','C1','C2'])
        self.assertEqual(inputs['difficulty']['default'],'random')
        self.assertIn('--prepared',next(step['run'] for step in document['jobs']['run']['steps'] if step.get('id')=='publication'))
        for i in (1,2,3):
            action=inputs[f'custom_word_{i}_action']
            self.assertTrue(action['description'].startswith('CUSTOM ONLY'))
            self.assertEqual(action['options'],['keep_today','same_image','same_image&design','chatgpt','entered'])
            self.assertEqual(inputs[f'custom_word_{i}']['type'],'string')
        for value in inputs.values():
            if value['type']=='choice':self.assertIn(value['default'],value['options'])
