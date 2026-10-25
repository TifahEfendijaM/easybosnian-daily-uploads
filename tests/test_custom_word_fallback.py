"""Invalid custom seeds are corrected/reselected, never a waiver of final review."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.cli import fit_check
from easybosnian.core import PROJECT, write_json, read_json
from easybosnian.selection import check_selection, novelty_history, selection_context, word_levels
from easybosnian.validate import validate,caption_language
from test_project import reviewed_fixture


class CustomWordFallbackTests(unittest.TestCase):
    def market(self):
        # Test-only reviewed fixture, not source research or permission to publish.
        package=reviewed_fixture();package['bosnian_level']='A2'
        package['theme']={'name':'Pijaca i kupovina','equivalence_keys':['market shopping']}
        package['words']=[{'lemma':'tezga','equivalence_keys':['market stall'],'bosnian_level':'A2'},
                          {'lemma':'cjenkati se','equivalence_keys':['bargain'],'bosnian_level':'B1'},
                          {'lemma':'kusur','equivalence_keys':['change money'],'bosnian_level':'A2'}]
        package['cards'][0].update(word='tezga',quiz_format='visual_identification',
            question='Kako se zove prodajno mjesto prikazano na slici?',
            options=[{'label':'A','text':'tezga'},{'label':'B','text':'ormar'},{'label':'C','text':'balkon'}])
        package['cards'][1].update(word='cjenkati se',heading='Dogovor oko cijene',
            body='Cjenkati se znači pokušati dogovoriti povoljniju cijenu s prodavačem.',
            example='Na pijaci se možemo cjenkati oko cijene.')
        package['cards'][2].update(word='kusur',heading='Kusur',
            body='Novac koji nam prodavač vraća ako smo platili više od cijene.',
            example='Prodavač mi je vratio dvije marke kusura.')
        package['caption']='Kupovina pruža priliku za razgovor: današnji primjeri povezuju nivoe A2 i B1.\nVježbaj bosanski da razgovor o cijeni bude lakši.\n👉easybosnian.com'
        package['private_review'].update(correct_option='A',correct_text='tezga',
            answer_aliases=['market stall'],identifying_hints=['tačan odgovor je tezga'])
        return package

    def choice(self,words,actions,history=None,theme='Pijaca i kupovina'):
        return selection_context(history or {'project':PROJECT,'days':[]},'2026-10-02','custom',theme,words,actions)

    def change(self,package,index,requested,cause,chosen=None):
        package['private_review']['word_replacements']=[{
            'word_index':index,'requested_word':requested,
            'chosen_word':chosen or package['words'][index]['lemma'],'cause':cause,
            'reason':'Test-only researched decision: the requested seed failed its word check.'}]

    def test_exact_misspelling_is_corrected_before_alternative_and_uses_own_level(self):
        package=self.market();chosen=self.choice(['Tezga','Cijenkati se',''],['entered','entered','chatgpt'])
        with self.assertRaises(ValueError):check_selection(package,chosen)
        self.change(package,1,'Cijenkati se','spelling_correction')
        check_selection(package,chosen)
        targets=word_levels(package,chosen,'A2');self.assertEqual(targets,['A2','B1','A2'])
        validate(package,novelty_history({'days':[]},package['date'],chosen,package),include_today=True,
                 require_website_footer=True,require_caption_level=True,require_quiz_format=True,
                 target_cefr='A2',word_level_targets=targets)
        fit_check(package)
        # No replacement is permitted to invent a rating for the intended word.
        package['words'][1]['bosnian_level']=None
        with self.assertRaisesRegex(ValueError,'corrected custom word'):word_levels(package,chosen,'A2')

    def test_invalid_entered_word_can_fall_back_with_all_final_checks(self):
        package=self.market();package['words'][1]['bosnian_level']='A2'
        package['caption']=package['caption'].replace('nivoe A2 i B1','nivo A2')
        chosen=self.choice(['Tezga','nepostojecarijec',''],['entered','entered','chatgpt'])
        self.change(package,1,'nepostojecarijec','invalid_bosnian')
        check_selection(package,chosen);targets=word_levels(package,chosen,'A2')
        self.assertEqual(targets,['A2']*3)
        validate(package,require_caption_level=True,word_level_targets=targets)
        for field in ('caption','sources','body'):
            bad=copy.deepcopy(package)
            if field=='caption':bad['caption']+=' Tačan odgovor je tezga.'
            elif field=='sources':bad['private_review']['sources_checked']=False
            else:bad['cards'][1]['body']='Duga rečenica. '*100
            with self.subTest(field=field),self.assertRaises(ValueError):validate(bad)

    def test_kept_invalid_word_falls_back_without_changing_other_retained_words(self):
        old=self.market();old['words'][1]={'lemma':'biblioteka','equivalence_keys':['library'],'bosnian_level':'C1'}
        old['cards'][1]['word']='biblioteka'
        history={'days':[{'date':old['date'],'batch_id':'b-'+'a'*32,'content':old}]}
        chosen=selection_context(history,old['date'],'custom',source_batch_id='b-'+'a'*32)
        package=self.market();package['caption']+=' Danas.'
        for card in package['cards']:
            card['background_prompt']+=' Fresh natural light.'
            card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
        package['words'][1]['bosnian_level']='A2'
        self.change(package,1,'biblioteka','theme_mismatch')
        check_selection(package,chosen)
        self.assertEqual(word_levels(package,chosen,'A2'),['A2']*3)
        remaining=novelty_history(history,old['date'],chosen,package)
        self.assertEqual(set(remaining['reused_word_keys']),{'tezga','market stall','kusur','change money'})
        package['private_review']['word_replacements'][0].pop('cause')
        with self.assertRaises(ValueError):check_selection(package,chosen)

    def test_replaced_kept_seed_loses_exemption_and_cannot_repeat_any_other_batch(self):
        package=self.market();package['words'][1]['bosnian_level']='A2'
        source=copy.deepcopy(package);source['words'][1]={'lemma':'biblioteka','equivalence_keys':['library'],'bosnian_level':'A2'}
        source['cards'][1]['word']='biblioteka'
        history={'days':[{'date':source['date'],'batch_id':'b-'+'a'*32,'content':source},
                         {'date':'2026-10-01','batch_id':'b-'+'b'*32,'content':package}]}
        chosen=selection_context(history,source['date'],'custom',source_batch_id='b-'+'a'*32)
        package['caption']+=' Danas.'
        for card in package['cards']:
            card['background_prompt']+=' Fresh natural light.'
            card['question' if card['kind']=='quiz' else 'body']+=' Danas.'
        self.change(package,1,'biblioteka','theme_mismatch')
        remaining=novelty_history(history,source['date'],chosen,package)
        self.assertNotIn('cjenkati se',remaining['reused_word_keys'])
        with self.assertRaisesRegex(ValueError,'repeats history'):validate(package,remaining,include_today=True)

    def test_structurally_bad_seed_delegates_only_its_slot_before_research(self):
        for raw in ('','!'*30,'x'*181):
            chosen=self.choice(['tezga',raw,''],['entered','entered','chatgpt'])
            self.assertEqual(chosen['requested_words'],['tezga',None,None])
            self.assertEqual(chosen['word_actions'],['entered','chatgpt','chatgpt'])
            self.assertEqual(chosen['word_input_fallbacks'],[{'word_index':1,'cause':'unusable_seed'}])
        chosen=self.choice(['tezga','TEZGA',''],['entered','entered','chatgpt'])
        self.assertEqual(chosen['requested_words'],['tezga',None,None])
        self.assertEqual(chosen['word_input_fallbacks'],[{'word_index':1,'cause':'word_overlap'}])
        chosen=self.choice(['','',''],['keep_today']*3)
        self.assertEqual(chosen['word_actions'],['chatgpt']*3)
        self.assertEqual(len(chosen['word_input_fallbacks']),3)

    def test_unrelated_theme_or_form_errors_are_not_word_fallbacks(self):
        for theme in ('','x'*181):
            with self.assertRaises(ValueError):self.choice(['tezga','',''],['entered','chatgpt','chatgpt'],theme=theme)
        with self.assertRaises(ValueError):self.choice(['tezga','',''],['chatgpt']*3)
        with self.assertRaises(ValueError):self.choice(['tezga','',''],['unknown','chatgpt','chatgpt'])
        package=self.market();self.change(package,1,'Cijenkati se','spelling_correction')
        chosen=self.choice(['tezga','Cijenkati se',''],['entered','entered','chatgpt'])
        package['theme']['name']='Druga tema'
        with self.assertRaisesRegex(ValueError,'Custom theme'):check_selection(package,chosen)

    def test_reviews_must_match_actual_custom_slot_and_never_waive_noncustom_checks(self):
        package=self.market();chosen=self.choice(['tezga','Cijenkati se',''],['entered','entered','chatgpt'])
        self.change(package,1,'Cijenkati se','spelling_correction')
        for mutation in ({'cause':'difficulty'},{'cause':'text_fit'},{'cause':'history_repeat'},{'word_index':2},
                         {'requested_word':'other'},{'chosen_word':'other'},{'reason':'short'}):
            bad=copy.deepcopy(package);bad['private_review']['word_replacements'][0].update(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):check_selection(bad,chosen)
        with self.assertRaisesRegex(ValueError,'only to custom'):check_selection(package,{'choice':'new','previous':None})
        package['private_review']['word_replacements'][0]['cause']='not-allowed'
        with self.assertRaisesRegex(ValueError,'schema check'):validate(package)

    def test_trusted_preparation_accepts_correction_for_every_batch_target_without_retry(self):
        from easybosnian.cloud_prepare import cloud_run
        for target in ('latest','none','all_today'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(*args):
                    package=self.market();self.change(package,1,'Cijenkati se','spelling_correction')
                    package['private_review']['language_policy_checked']=True
                    package['caption_language']=caption_language(package)
                    for c,w in zip(package['cards'],package['words']):
                        c['question_language' if c['kind']=='quiz' else 'body_language']='en' if w.get('bosnian_level',package.get('bosnian_level')) in ('A1','A2') else 'bs'
                    if package['cards'][0]['question_language']=='en':package['cards'][0]['question']='What is the place where a seller displays goods at the market?'
                    package['cards'][2]['body']='The money a seller returns when you paid more than the price.'
                    package['private_review']['quiz_choice_review']={'target':3,'binary':False,
                        'reason':'This is a non-binary multiple-choice question with three distinct options.'}
                    package['cards'][0]['quiz_format']=read_json(root/'build/preparation-context.json')['selection']['quiz_format_target']
                    write_json(root/'build/preparation/2026-10-02.json',package)
                    return '{"status":"ready","reason":"none"}'
                with patch('easybosnian.cloud_prepare.ROOT',root),patch('easybosnian.cloud_prepare.secrets.choice',return_value=3),patch('easybosnian.cloud_prepare.today',return_value='2026-10-02'),patch('easybosnian.cloud_prepare.select_run_level',return_value='A2'),patch('easybosnian.cloud_prepare.require_publishing'),patch('easybosnian.cloud_prepare.check_infrastructure'),patch('easybosnian.cloud_prepare.Store') as store,patch('easybosnian.cloud_prepare.run_codex',side_effect=agent) as child,patch('easybosnian.cloud_prepare.prepare') as save:
                    store.return_value.history.return_value={'project':PROJECT,'days':[]}
                    store.return_value.publications_for_date.return_value=[]
                    result=cloud_run('daily','custom','Pijaca i kupovina',['Tezga','Cijenkati se',''],['entered','entered','chatgpt'],batch_target=target)
                    self.assertEqual(result['status'],'reviewed content staged privately')
                    child.assert_called_once();save.assert_called_once()
                    self.assertEqual(save.call_args.kwargs['batch_target'],target)
                    store.return_value.remove_content.assert_not_called()


if __name__=='__main__':unittest.main()
