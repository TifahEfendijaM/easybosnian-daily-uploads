import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.core import ROOT, REPO
from easybosnian.levels import LEVELS, load_level, set_level, settings_level
from easybosnian.selection import selection_context, novelty_history, check_selection
from easybosnian.validate import validate
from test_project import reviewed_fixture


def remote(level,sha='file-sha'):
    return json.dumps({'sha':sha,'content':base64.b64encode(json.dumps({'bosnian_level':level}).encode()).decode()})


class LevelTests(unittest.TestCase):
    def test_settings_accept_only_one_valid_shared_level(self):
        for level in LEVELS:self.assertEqual(settings_level({'bosnian_level':level}),level)
        for value in ({},{'bosnian_level':'C3'},{'bosnian_level':'A2','extra':True},None):
            with self.assertRaises(ValueError):settings_level(value)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'data/preparation-settings.json').write_text('{"bosnian_level":"B2"}')
            with patch('easybosnian.levels.ROOT',root):self.assertEqual(load_level(),'B2')

    def test_setting_update_writes_only_target_main_file_and_reads_back(self):
        with patch('easybosnian.levels.gh',side_effect=[remote('A2'),'{}',remote('B2')]) as github:
            self.assertEqual(set_level('B2'),{'bosnian_level':'B2','updated':True})
        read,write,readback=github.call_args_list
        self.assertEqual(read.args,('api',f'repos/{REPO}/contents/data/preparation-settings.json?ref=main'))
        self.assertEqual(readback.args,read.args)
        payload=json.loads(write.kwargs['input_text'])
        self.assertEqual(payload['branch'],'main');self.assertEqual(payload['sha'],'file-sha')
        self.assertEqual(json.loads(base64.b64decode(payload['content'])),{'bosnian_level':'B2'})
        self.assertEqual(write.args[1],f'repos/{REPO}/contents/data/preparation-settings.json')

    def test_same_level_no_write_and_bad_input_or_uncertain_readback_no_retry(self):
        with patch('easybosnian.levels.gh',return_value=remote('A2')) as github:
            self.assertFalse(set_level('A2')['updated']);self.assertEqual(github.call_count,1)
        with patch('easybosnian.levels.gh') as github,self.assertRaises(ValueError):set_level('C3')
        github.assert_not_called()
        with patch('easybosnian.levels.gh',side_effect=[remote('A2'),'{}',remote('A2')]) as github,self.assertRaises(ValueError):set_level('B2')
        self.assertEqual(sum('--method' in call.args for call in github.call_args_list),1)

    def test_new_content_requires_actual_target_level_but_preserved_copy_keeps_old_level(self):
        p=reviewed_fixture();validate(p)
        with self.assertRaisesRegex(ValueError,'difficulty'):validate(p,target_cefr='A2')
        p['bosnian_level']='A2';validate(p,target_cefr='A2')
        with self.assertRaises(ValueError):validate(p,target_cefr='B2')
        history={'days':[{'date':p['date'],'content':p}]};selection=selection_context(history,p['date'],'same_words')
        image_only=copy.deepcopy(p)
        for c in image_only['cards']:c['background_prompt']+=' Fresh light.'
        check_selection(image_only,selection);validate(image_only,novelty_history(history,p['date'],selection),include_today=True)
        self.assertEqual(image_only['bosnian_level'],'A2')

    def test_custom_word_actions_keep_enter_or_delegate_independently(self):
        old=reviewed_fixture();history={'days':[{'date':old['date'],'content':old}]}
        chosen=selection_context(history,old['date'],'custom','',['','','vjetar'],['keep_today','chatgpt','entered'])
        self.assertEqual(chosen['requested_words'],['kišobran',None,'vjetar'])
        self.assertEqual(chosen['pinned_words'][0],old['words'][0]);self.assertIsNone(chosen['pinned_words'][1])
        remaining=novelty_history(history,old['date'],chosen)['days'][0]['content']['words']
        self.assertEqual(remaining,old['words'][1:])
        new=copy.deepcopy(old);new['caption']+=' Danas.'
        new['words'][1]={'lemma':'sunce','equivalence_keys':['sun']};new['words'][2]={'lemma':'vjetar','equivalence_keys':['wind']}
        for i,c in enumerate(new['cards']):
            c['word']=new['words'][i]['lemma'];c['background_prompt']+=' Fresh light.'
            c['question' if c['kind']=='quiz' else 'body']+=' Danas.'
        check_selection(new,chosen)
        new['words'][0]={'lemma':'kaput','equivalence_keys':['coat']}
        with self.assertRaises(ValueError):check_selection(new,chosen)

    def test_custom_actions_reject_conflicts_and_support_no_history_when_delegated(self):
        old=reviewed_fixture();history={'days':[{'date':old['date'],'content':old}]}
        for words,actions in ((['x','',''],['keep_today']*3),(['','',''],['entered','keep_today','keep_today']),(['x','',''],['chatgpt']*3),(['','',''],['unknown']*3)):
            with self.assertRaises(ValueError):selection_context(history,old['date'],'custom','',words,actions)
        chosen=selection_context({'days':[]},old['date'],'custom','Kišni dan',['','',''],['chatgpt']*3)
        self.assertEqual(chosen['requested_words'],[None]*3)
        with self.assertRaises(ValueError):selection_context({'days':[]},old['date'],'custom','Kišni dan',['','',''],['keep_today']*3)

    def test_configuration_workflow_has_no_publishing_or_provider_secrets(self):
        text=(ROOT/'.github/workflows/configure-level.yml').read_text()
        self.assertIn('options: [A1, A2, B1, B2, C1, C2]',text)
        self.assertIn('contents: write',text);self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertNotIn('secrets.',text);self.assertNotIn('cloud_prepare',text);self.assertNotIn('easybosnian run',text)
        pipeline=(ROOT/'.github/workflows/preparation.yml').read_text()
        self.assertIn('contents: read',pipeline);self.assertNotIn('contents: write',pipeline)
