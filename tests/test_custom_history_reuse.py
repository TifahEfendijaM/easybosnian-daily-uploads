"""Manual concepts can repeat; model-selected slots still compare full history."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from easybosnian.cli import fit_check, prepare
from easybosnian.core import PROJECT, read_json, write_json
from easybosnian.selection import check_selection, novelty_history, selection_context
from easybosnian.validate import validate
import test_custom_word_fallback as fallback
from test_project import reviewed_fixture


class CustomHistoryReuseTests(unittest.TestCase):
    def setUp(self):
        self.package = fallback.CustomWordFallbackTests().market()
        self.previous = reviewed_fixture()
        self.source_id = 'b-' + 'a' * 32
        self.history = {'project': PROJECT, 'days': [
            {'batch_id': self.source_id, 'date': self.previous['date'], 'content': self.previous},
            {'batch_id': 'legacy-2026-09-30', 'date': '2026-09-30', 'content': {
                'theme': {'name': 'Kupovina', 'equivalence_keys': ['market shopping']},
                'words': [{'lemma': 'prodajno mjesto', 'equivalence_keys': ['market stall']},
                          {'lemma': 'pregovarati o cijeni', 'equivalence_keys': ['bargain']},
                          {'lemma': 'vraćeni novac', 'equivalence_keys': ['change money']}]
            }}]}

    def choice(self, words=None, actions=None, theme='Pijaca i kupovina'):
        return selection_context(self.history, self.package['date'], 'custom', theme,
            words or [w['lemma'] for w in self.package['words']], actions or ['entered'] * 3,
            source_batch_id=self.source_id)

    def test_entered_theme_and_words_can_repeat_older_legacy_aliases_without_erasing_history(self):
        chosen = self.choice()
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, self.history, include_today=True)
        before = copy.deepcopy(self.history)
        reviewed = novelty_history(self.history, self.package['date'], chosen, self.package)
        validate(self.package, reviewed, include_today=True)
        fit_check(self.package)
        self.assertEqual(reviewed['days'], before['days'])
        self.assertEqual(self.history, before)
        self.assertIn('market shopping', reviewed['reused_theme_keys'])
        self.assertIn('bargain', reviewed['reused_word_keys'])
        # The same policy applies when older clients provide no source batch ID.
        chosen.pop('source_batch_id')
        validate(self.package, novelty_history(self.history, self.package['date'], chosen, self.package), include_today=True)

    def test_repeated_custom_theme_does_not_exempt_chatgpt_words(self):
        # Same input shape as the failed run: an entered theme, three delegated words.
        chosen = self.choice(['', '', ''], ['chatgpt'] * 3)
        reviewed = novelty_history(self.history, self.package['date'], chosen, self.package)
        self.assertEqual(reviewed['reused_word_keys'], [])
        self.assertIn('market shopping', reviewed['reused_theme_keys'])
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, reviewed, include_today=True)
        self.history['days'][1]['content']['words'] = self.previous['words']
        validate(self.package, novelty_history(self.history, self.package['date'], chosen, self.package), include_today=True)

    def test_mixed_custom_only_exempts_entered_slots(self):
        chosen = self.choice(['tezga', '', 'kusur'], ['entered', 'chatgpt', 'entered'])
        reviewed = novelty_history(self.history, self.package['date'], chosen, self.package)
        self.assertIn('market stall', reviewed['reused_word_keys'])
        self.assertNotIn('bargain', reviewed['reused_word_keys'])
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, reviewed, include_today=True)

    def test_researched_spelling_correction_keeps_manual_repeat_permission(self):
        chosen = self.choice(['tezga', 'Cijenkati se', 'kusur'])
        fallback.CustomWordFallbackTests().change(self.package, 1, 'Cijenkati se', 'spelling_correction')
        reviewed = novelty_history(self.history, self.package['date'], chosen, self.package)
        self.assertIn('bargain', reviewed['reused_word_keys'])
        validate(self.package, reviewed, include_today=True)

    def test_different_fallback_still_cannot_repeat_historical_word(self):
        chosen = self.choice(['tezga', 'nepostojecarijec', 'kusur'])
        fallback.CustomWordFallbackTests().change(self.package, 1, 'nepostojecarijec', 'invalid_bosnian')
        reviewed = novelty_history(self.history, self.package['date'], chosen, self.package)
        self.assertNotIn('bargain', reviewed['reused_word_keys'])
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, reviewed, include_today=True)

    def test_repeat_permission_cannot_change_requested_selection_or_waive_other_checks(self):
        for field in ('theme', 'word', 'alias_overlap', 'review', 'answer_leak', 'fit'):
            package = copy.deepcopy(self.package)
            chosen = self.choice()
            if field == 'theme': package['theme']['name'] = 'Druga tema'
            elif field == 'word': package['words'][1]['lemma'] = 'druga riječ'
            elif field == 'alias_overlap': package['words'][1]['equivalence_keys'] += ['market stall']
            elif field == 'review': package['private_review']['standard_bosnian_checked'] = False
            elif field == 'answer_leak': package['caption'] += ' Tačan odgovor je tezga.'
            else: package['cards'][1]['body'] = 'Preduga rečenica. ' * 80
            with self.subTest(field=field), self.assertRaises(ValueError):
                reviewed = novelty_history(self.history, package['date'], chosen, package)
                validate(package, reviewed, include_today=True)
                fit_check(package)

    def test_changed_manual_theme_keeps_delegated_old_words_subject_to_novelty(self):
        chosen = self.choice(['', '', ''], ['keep_today'] * 3)
        self.assertEqual(chosen['word_actions'], ['chatgpt'] * 3)
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, novelty_history(self.history, self.package['date'], chosen, self.package), include_today=True)

    def test_new_mode_has_no_manual_exemptions_even_with_custom_fields(self):
        chosen = selection_context(self.history, self.package['date'], 'new',
            self.package['theme']['name'], [w['lemma'] for w in self.package['words']], ['entered'] * 3)
        contaminated = dict(self.history, reused_theme_keys=['market shopping'],
                            reused_word_keys=['market stall', 'bargain', 'change money'])
        with self.assertRaisesRegex(ValueError, 'repeats history'):
            validate(self.package, novelty_history(contaminated, self.package['date'], chosen, self.package), include_today=True)

    def test_cloud_and_trusted_save_accept_manual_history_repeats_for_every_target(self):
        from easybosnian.cloud_prepare import cloud_run
        for target in ('latest', 'none', 'all_today'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root/'docs').mkdir()
                (root/'docs/cloud-agent-task.md').write_text('Prepare {{DATE}}')
                def agent(*args):
                    context = read_json(root/'build/preparation-context.json')
                    package = copy.deepcopy(self.package)
                    package.update(batch_id=context['batch']['batch_id'], date=context['batch']['date'])
                    package['private_review']['language_policy_checked']=True
                    for c,w in zip(package['cards'],package['words']):
                        if c['kind']!='quiz':c['body_language']='en' if w.get('bosnian_level',package.get('bosnian_level')) in ('A1','A2') else 'bs'
                    package['cards'][2]['body']='The money a seller returns when you paid more than the price.'
                    package['private_review']['quiz_choice_review']={'target':3,'binary':False,
                        'reason':'This is a non-binary multiple-choice question with three distinct options.'}
                    write_json(root/f"build/preparation/{package['date']}.json", package)
                    return '{"status":"ready","reason":"none"}'
                with patch('easybosnian.cloud_prepare.ROOT', root), patch('easybosnian.cloud_prepare.secrets.choice',return_value=3), patch('easybosnian.cloud_prepare.today', return_value='2026-10-04'), patch('easybosnian.cloud_prepare.select_run_level', return_value='A2'), patch('easybosnian.levels.load_level', return_value='A2'), patch('easybosnian.cloud_prepare.failure'), patch('easybosnian.cloud_prepare.require_publishing'), patch('easybosnian.cloud_prepare.check_infrastructure'), patch('easybosnian.cloud_prepare.Store') as store, patch('easybosnian.cli.Store', store), patch('easybosnian.cli.verify_repository'), patch('easybosnian.cloud_prepare.run_codex', side_effect=agent) as child, patch('easybosnian.cloud_prepare.prepare', wraps=prepare) as save:
                    store.return_value.history.return_value = self.history
                    store.return_value.publications_for_date.return_value = []
                    result = cloud_run('daily', 'custom', self.package['theme']['name'],
                        [w['lemma'] for w in self.package['words']], ['entered'] * 3, batch_target=target)
                    self.assertEqual(result['status'], 'reviewed content staged privately')
                    child.assert_called_once()
                    save.assert_called_once()
                    store.return_value.save_content.assert_not_called()
                    store.return_value.remove_content.assert_not_called()


if __name__ == '__main__': unittest.main()
