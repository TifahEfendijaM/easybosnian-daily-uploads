import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.core import ROOT, REPO
from easybosnian.levels import KEEP_CURRENT, LEVELS, load_level, set_level, settings_level
from easybosnian.selection import selection_context, novelty_history, check_selection, word_levels
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

    def test_keep_current_reads_actual_main_setting_without_resetting_or_writing(self):
        for level in LEVELS:
            with self.subTest(level=level),patch('easybosnian.levels.gh',return_value=remote(level)) as github:
                self.assertEqual(set_level(KEEP_CURRENT),{'bosnian_level':level,'updated':False})
                github.assert_called_once_with('api',f'repos/{REPO}/contents/data/preparation-settings.json?ref=main')

    def test_configuration_summary_reports_actual_saved_level_not_menu_default(self):
        from easybosnian.cli import main
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.cli.load_env'),patch('sys.argv',['easybosnian','set-level','--level',KEEP_CURRENT]),patch('easybosnian.levels.gh',return_value=remote('B2')) as github,patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':str(Path(temp)/'summary.md')}):
            main()
            text=(Path(temp)/'summary.md').read_text()
            self.assertIn('Current saved difficulty: **B2**',text)
            self.assertIn('no file was changed',text)
            self.assertEqual(github.call_count,1)

    def test_new_content_records_global_level_while_same_words_retains_individual_levels(self):
        p=reviewed_fixture();validate(p)
        with self.assertRaisesRegex(ValueError,'difficulty'):validate(p,target_cefr='A2')
        p['bosnian_level']='A2';validate(p,target_cefr='A2')
        with self.assertRaises(ValueError):validate(p,target_cefr='B2')
        history={'days':[{'date':p['date'],'content':p}]};selection=selection_context(history,p['date'],'same_words')
        fresh=copy.deepcopy(p);fresh['bosnian_level']='B2';fresh['caption']+=' Danas.'
        for word in fresh['words']:word['bosnian_level']='A2'
        for card in fresh['cards']:
            card['background_prompt']+=' Fresh light.'
            card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
        check_selection(fresh,selection)
        targets=word_levels(fresh,selection,'B2');self.assertEqual(targets,['A2']*3)
        validate(fresh,novelty_history(history,p['date'],selection),include_today=True,target_cefr='B2',word_level_targets=targets)

    def test_custom_word_actions_keep_enter_or_delegate_independently(self):
        old=reviewed_fixture();history={'days':[{'date':old['date'],'content':old}]}
        chosen=selection_context(history,old['date'],'custom','',['','','vjetar'],['keep_today','chatgpt','entered'])
        self.assertEqual(chosen['requested_words'],['kišobran',None,'vjetar'])
        self.assertEqual(chosen['pinned_words'][0],old['words'][0]);self.assertIsNone(chosen['pinned_words'][1])
        remaining=novelty_history(history,old['date'],chosen)
        self.assertEqual(remaining['days'],history['days'])
        self.assertIn('kisobran',remaining['reused_word_keys'])
        self.assertIn('vjetar',remaining['reused_word_keys'])
        self.assertNotIn('oblak',remaining['reused_word_keys'])
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
        for words,actions in ((['x','',''],['keep_today']*3),(['x','',''],['chatgpt']*3),(['','',''],['unknown']*3)):
            with self.assertRaises(ValueError):selection_context(history,old['date'],'custom','',words,actions)
        chosen=selection_context({'days':[]},old['date'],'custom','Kišni dan',['','',''],['chatgpt']*3)
        self.assertEqual(chosen['requested_words'],[None]*3)
        chosen=selection_context({'days':[]},old['date'],'custom','Kišni dan',['','',''],['keep_today']*3)
        self.assertEqual(chosen['requested_words'],[None]*3)
        self.assertEqual(chosen['word_actions'],['chatgpt']*3)

    def test_configuration_workflow_has_no_publishing_or_provider_secrets(self):
        text=(ROOT/'.github/workflows/configure-level.yml').read_text()
        self.assertIn('options: [Keep current, A1, A2, B1, B2, C1, C2]',text)
        self.assertIn('default: Keep current',text);self.assertNotIn('default: A2',text)
        self.assertIn('contents: read',text);self.assertIn('false &&',text);self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertNotIn('secrets.',text);self.assertNotIn('cloud_prepare',text);self.assertNotIn('easybosnian run',text)
        pipeline=(ROOT/'.github/workflows/preparation.yml').read_text()
        self.assertIn('contents: read',pipeline);self.assertNotIn('contents: write',pipeline)


class PerWordLevelTests(unittest.TestCase):
    def setUp(self):
        self.old=reviewed_fixture();self.old['bosnian_level']='A2'
        for word in self.old['words']:word['bosnian_level']='A2'
        self.history={'days':[{'date':self.old['date'],'content':self.old}]}

    def fresh(self):
        new=copy.deepcopy(self.old);new['bosnian_level']='B2';new['caption']+=' Danas.'
        for card in new['cards']:
            card['background_prompt']+=' Fresh light.'
            card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
        return new

    def test_retained_copy_keeps_individual_level_after_global_change(self):
        chosen=selection_context(self.history,self.old['date'],'custom')
        new=self.fresh();check_selection(new,chosen)
        targets=word_levels(new,chosen,'B2');self.assertEqual(targets,['A2']*3)
        validate(new,novelty_history(self.history,new['date'],chosen,new),include_today=True,target_cefr='B2',word_level_targets=targets)
        new['words'][0]['bosnian_level']='B2'
        with self.assertRaises(ValueError):check_selection(new,chosen)
        with self.assertRaisesRegex(ValueError,'difficulty'):validate(new,word_level_targets=targets)

    def test_changed_theme_delegates_keep_today_and_keeps_history_authoritative(self):
        chosen=selection_context(self.history,self.old['date'],'custom','Zimska šetnja')
        self.assertTrue(chosen['theme_changed']);self.assertEqual(chosen['word_actions'],['chatgpt']*3)
        self.assertEqual(chosen['requested_words'],[None]*3);self.assertEqual(chosen['pinned_words'],[None]*3)
        remaining=novelty_history(self.history,self.old['date'],chosen)
        self.assertEqual(remaining['days'],self.history['days'])
        self.assertEqual(remaining['reused_theme_keys'],['zimska setnja'])
        self.assertEqual(remaining['reused_word_keys'],[])
        self.assertEqual(word_levels(self.fresh(),chosen,'B2'),['B2']*3)

    def test_compatible_entered_word_has_its_own_level_and_needs_no_replacement(self):
        chosen=selection_context(self.history,self.old['date'],'custom','',['','','vjetar'],['keep_today','chatgpt','entered'])
        new=self.fresh();new['words'][1]={'lemma':'sunce','equivalence_keys':['sun'],'bosnian_level':'B2'}
        new['words'][2]={'lemma':'vjetar','equivalence_keys':['wind'],'bosnian_level':'A1'}
        for card,word in zip(new['cards'],new['words']):card['word']=word['lemma']
        check_selection(new,chosen);self.assertEqual(word_levels(new,chosen,'B2'),['A2','B2','A1'])
        new['words'][2].pop('bosnian_level')
        with self.assertRaisesRegex(ValueError,'reviewed difficulty'):word_levels(new,chosen,'B2')

    def test_incompatible_entered_word_requires_matching_private_review_and_global_level(self):
        chosen=selection_context(self.history,self.old['date'],'custom','',['','','knjiga'],['keep_today','chatgpt','entered'])
        new=self.fresh();new['words'][1]={'lemma':'sunce','equivalence_keys':['sun'],'bosnian_level':'B2'}
        new['words'][2]={'lemma':'vjetar','equivalence_keys':['wind'],'bosnian_level':'B2'}
        for card,word in zip(new['cards'],new['words']):card['word']=word['lemma']
        with self.assertRaises(ValueError):check_selection(new,chosen)
        change={'word_index':2,'requested_word':'knjiga','chosen_word':'vjetar','reason':'Knjiga ne odgovara izabranoj temi kišnog dana; vjetar je vezan za vrijeme.'}
        new['private_review']['word_replacements']=[change]
        check_selection(new,chosen);self.assertEqual(word_levels(new,chosen,'B2'),['A2','B2','B2'])
        for mutation in ({'word_index':0},{'requested_word':'wrong'},{'chosen_word':'wrong'},{'reason':'short'}):
            new['private_review']['word_replacements']=[{**change,**mutation}]
            with self.assertRaises(ValueError):check_selection(new,chosen)
        for malformed in ([None],{},[change,change]):
            new['private_review']['word_replacements']=malformed
            with self.assertRaises(ValueError):check_selection(new,chosen)

    def test_replaced_entered_word_is_not_exempted_from_novelty(self):
        chosen=selection_context(self.history,self.old['date'],'custom','Zimska šetnja',['kišobran','',''],['entered','keep_today','keep_today'])
        new=self.fresh();new['theme']={'name':'Zimska šetnja','equivalence_keys':['winter walk']}
        new['words'][0]={'lemma':'kaput','equivalence_keys':['coat'],'bosnian_level':'B2'}
        new['cards'][0]['word']='kaput'
        new['private_review']['word_replacements']=[{'word_index':0,'requested_word':'kišobran','chosen_word':'kaput','reason':'U ovoj uskoj temi odjeće za snijeg izabrana riječ ne odgovara opisu.'}]
        remaining=novelty_history(self.history,new['date'],chosen,new)
        self.assertEqual(remaining['days'],self.history['days'])
        self.assertEqual(set(remaining['reused_theme_keys']),{'zimska setnja','winter walk'})
        self.assertEqual(remaining['reused_word_keys'],[])
        check_selection(new,chosen);self.assertEqual(word_levels(new,chosen,'B2'),['B2']*3)

    def test_legacy_retained_levels_stay_unknown_and_old_replacement_reviews_are_not_reused(self):
        legacy=reviewed_fixture();history={'days':[{'date':legacy['date'],'content':legacy}]}
        chosen=selection_context(history,legacy['date'],'custom');new=copy.deepcopy(legacy)
        for word in new['words']:word['bosnian_level']=None
        self.assertEqual(word_levels(new,chosen,'B2'),[None]*3)
        new['bosnian_level']='B2'
        newer=selection_context({'days':[{'date':new['date'],'content':new}]},new['date'],'custom')
        self.assertEqual(word_levels(new,newer,'C1'),[None]*3)
        legacy['bosnian_level']='A2';chosen=selection_context(history,legacy['date'],'custom')
        for word in new['words']:word['bosnian_level']='A2'
        self.assertEqual(word_levels(new,chosen,'B2'),['A2']*3)
        self.old['private_review']['word_replacements']=[{'word_index':0,'requested_word':'kaput','chosen_word':'kišobran','reason':'Ranije provjerena promjena zbog neusaglašene teme.'}]
        chosen=selection_context(self.history,self.old['date'],'same_words');new=self.fresh()
        with self.assertRaisesRegex(ValueError,'only to custom'):check_selection(new,chosen)
        new['private_review'].pop('word_replacements');check_selection(new,chosen)
        self.assertEqual(word_levels(new,chosen,'B2'),['A2']*3)
