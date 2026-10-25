"""Per-run level draws, frozen staging and bilingual explanations; no live calls."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch,MagicMock

from easybosnian.core import PROJECT,ROOT,read_json,write_json
from easybosnian.levels import LEVELS,random_level,select_run_level
from easybosnian.validate import validate
from easybosnian.cloud_prepare import cloud_run
from test_project import reviewed_fixture


def fresh(level='A2'):
    p=reviewed_fixture();p['bosnian_level']=level
    p['cards'][0]['quiz_format']='other'
    p['private_review'].update(language_policy_checked=True,quiz_choice_review={
        'target':3,'binary':False,'reason':'The quiz asks an objective non-binary question with three plausible choices.'})
    for c,w in zip(p['cards'],p['words']):
        w['bosnian_level']=level
        c['question_language' if c['kind']=='quiz' else 'body_language']='en' if level in ('A1','A2') else 'bs'
    if level in ('A1','A2'):
        p['cards'][0]['question']='Which object protects you from the rain?'
        p['cards'][1]['body']='A cloud is a visible mass of tiny water droplets in the sky.'
        p['cards'][2]['body']='A puddle is a small area of water on the ground after rain.'
    p['caption_language']='en' if level in ('A1','A2') else 'bs'
    p['caption']=(f'Practise talking about rainy days in Bosnian at level {level}.\nContinue learning with free lessons on EasyBosnian.\n👉easybosnian.com'
                  if p['caption_language']=='en' else f'Danas uz jednostavne primjere vježbamo bosanski na nivou {level}.\nZa jasniji razgovor o vremenu učite s nama.\n👉easybosnian.com')
    return p


class RunDifficultyLanguageTests(unittest.TestCase):
    def test_every_random_ticket_has_the_exact_requested_weight_without_redraw(self):
        counts=Counter()
        for ticket in range(64):
            with patch('easybosnian.levels.secrets.randbelow',return_value=ticket) as draw:
                counts[random_level()]+=1;draw.assert_called_once_with(64)
        self.assertEqual([counts[level] for level in LEVELS],[32,16,8,4,2,2])

    def test_explicit_levels_and_retained_words_ignore_legacy_settings(self):
        with patch('easybosnian.levels.load_level',side_effect=AssertionError('Legacy setting is inactive')):
            for choice in ('new','same_theme','custom'):
                for level in LEVELS:
                    with patch('easybosnian.levels.random_level') as draw:
                        self.assertEqual(select_run_level({'choice':choice},level),level);draw.assert_not_called()
                with patch('easybosnian.levels.random_level',return_value='A1') as draw:
                    self.assertEqual(select_run_level({'choice':choice},'random'),'A1');draw.assert_called_once()
            for choice in ('same_words','same_images'):
                with patch('easybosnian.levels.random_level') as draw:
                    self.assertEqual(select_run_level({'choice':choice,'previous':{'bosnian_level':'B2'}},'A1'),'B2');draw.assert_not_called()
            with patch('easybosnian.levels.random_level',return_value='A2') as draw:
                self.assertEqual(select_run_level({'choice':'same_words','previous':{}},'random'),'A2');draw.assert_called_once()
        with self.assertRaises(ValueError):select_run_level({'choice':'new'},'C3')

    def test_fresh_language_metadata_matches_individual_levels_and_old_content_is_readable(self):
        validate(reviewed_fixture())
        for level in LEVELS:
            p=fresh(level);validate(p,require_language_policy=True)
            bad=copy.deepcopy(p);bad['cards'][1]['body_language']='bs' if level in ('A1','A2') else 'en'
            with self.assertRaisesRegex(ValueError,'Explanation language'):validate(bad,require_language_policy=True)
            for value in (None,'bs' if level in ('A1','A2') else 'en'):
                bad=copy.deepcopy(p)
                if value is None:bad['cards'][0].pop('question_language')
                else:bad['cards'][0]['question_language']=value
                with self.assertRaisesRegex(ValueError,'Quiz question language'):validate(bad,require_language_policy=True)
            bad=copy.deepcopy(p);bad['private_review'].pop('language_policy_checked')
            with self.assertRaisesRegex(ValueError,'reviewed beginner'):validate(bad,require_language_policy=True)
        p=fresh('B2');p['words'][1]['bosnian_level']='A1';p['cards'][1].update(body_language='en',body='A cloud is made of tiny water droplets.')
        validate(p,require_language_policy=True)
        p['words'][1]['bosnian_level']=None;p['cards'][1]['body_language']='bs';validate(p,require_language_policy=True)
        p['cards'][2]['body']='An umbrella is useful in rain.'
        with self.assertRaisesRegex(ValueError,'leaks'):validate(p,require_language_policy=True)

    def test_quiz_uses_its_own_level_and_poll_keeps_english_question_and_bosnian_options(self):
        from easybosnian.instagram_poll import instagram_caption,quiz_poll
        p=fresh('B2');quiz=p['cards'][0];original=copy.deepcopy(quiz['options'])
        p['words'][0]['bosnian_level']='A1'
        quiz.update(question_language='en',question='Which object protects you from the rain?')
        validate(p,require_language_policy=True)
        self.assertIn(quiz['question'],instagram_caption(p))
        self.assertEqual(list(quiz_poll(p)[0].values()),[option['text'] for option in original])
        self.assertEqual(quiz['options'],original)
        p['words'][0]['bosnian_level']=None;quiz['question_language']='bs'
        quiz['question']='Kako se zove predmet na slici?'
        validate(p,require_language_policy=True)
        bad=copy.deepcopy(p);bad['cards'][1]['question_language']='en'
        with self.assertRaisesRegex(ValueError,'schema check'):validate(bad)

    def test_research_and_trusted_staging_share_one_level_snapshot_without_settings_read(self):
        from easybosnian.cli import prepare
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            root=Path(temp);(root/'docs').mkdir();(root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
            (root/'data').mkdir();(root/'data/design-palettes.json').write_bytes((ROOT/'data/design-palettes.json').read_bytes())
            def agent(*args):
                ctx=read_json(root/'build/preparation-context.json');self.assertEqual(ctx['target_cefr'],'A2')
                self.assertEqual(ctx['selection']['target_cefr'],'A2')
                p=fresh();p.update(date=ctx['batch_date'],batch_id=ctx['batch']['batch_id'])
                p['cards'][0]['quiz_format']=ctx['selection']['quiz_format_target']
                write_json(root/f'build/preparation/{p["date"]}.json',p)
                return '{"status":"ready","reason":"none"}'
            for name in ('cloud_prepare','cli'):stack.enter_context(patch('easybosnian.'+name+'.ROOT',root))
            stack.enter_context(patch('easybosnian.levels.load_level',side_effect=AssertionError('Inactive setting')))
            draw=stack.enter_context(patch('easybosnian.levels.secrets.randbelow',return_value=32))
            stack.enter_context(patch('easybosnian.cloud_prepare.secrets.choice',return_value=3))
            store=MagicMock();store.history.return_value={'project':PROJECT,'days':[]}
            for name in ('cloud_prepare','cli'):stack.enter_context(patch('easybosnian.'+name+'.Store',return_value=store))
            for name in ('require_publishing','check_infrastructure'):stack.enter_context(patch('easybosnian.cloud_prepare.'+name))
            stack.enter_context(patch('easybosnian.cloud_prepare.failure',side_effect=lambda date,stage,error,*a:str(error)))
            stack.enter_context(patch('easybosnian.cli.verify_repository'))
            child=stack.enter_context(patch('easybosnian.cloud_prepare.run_codex',side_effect=agent))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result=cloud_run('daily','new',batch_target='none',difficulty='random')
            self.assertEqual(result['target_cefr'],'A2');draw.assert_called_once_with(64);child.assert_called_once()
            self.assertEqual(read_json(root/'build/reviewed-content.secret')['content']['bosnian_level'],'A2')
            store.save_content.assert_not_called();store.delete_content.assert_not_called()


if __name__=='__main__':unittest.main()
