"""Full-history review must survive a large, Unicode-rich local context."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from unittest.mock import patch

from easybosnian.core import PROJECT,write_json
from easybosnian.research_context import context_pages,context_index,main,reading_instructions,review_context
from easybosnian.selection import novelty_history
from easybosnian.validate import validate
from test_project import reviewed_fixture


class ResearchContextTests(unittest.TestCase):
    def context(self):
        content=reviewed_fixture()
        content['sources']=[{'url':'https://example.test/old-source','supports':'historical source paperwork'*300}]
        content['private_review'].update(notes='historical audit notes'*300)
        content['private_review']['future_semantic_field']=['čuvati neobičnu riječ']
        imported={'date':'2026-09-01','content':{'record_type':'legacy_word_history',
                  'theme':{'name':'Imported theme','equivalence_keys':['imported-alias']},
                  'words':[{'lemma':'đak','equivalence_keys':['pupil']}],
                  'provenance':{'note':'original import evidence'}}}
        history={'project':PROJECT,'storage_version':2,'days':[imported]+[
            {'batch_id':'b-'+f'{i:032x}','date':'2026-10-01','theme':content['theme'],
             'words':content['words'],'content':copy.deepcopy(content)} for i in range(33)]}
        return {'history':history,'selection':{'choice':'same_words','previous':copy.deepcopy(content)},
                'target_cefr':'A2','batch':{'batch_id':'b-'+'f'*32},'frozen_card_kinds':['quiz']}

    def test_large_review_preserves_every_row_exact_copy_metadata_and_selected_previous(self):
        original=self.context();before=copy.deepcopy(original)
        review=json.loads(''.join(context_pages(original)))
        self.assertEqual(original,before)
        self.assertEqual(len(review['history']['days']),34)
        self.assertEqual(review['history']['days'][0],original['history']['days'][0])
        self.assertEqual(review['selection'],original['selection'])
        self.assertEqual(review['frozen_card_kinds'],['quiz'])
        for row,source in zip(review['history']['days'][1:],original['history']['days'][1:]):
            for key in ('batch_id','date','theme','words'):self.assertEqual(row[key],source[key])
            for key in ('theme','words','cards','caption','hashtags'):
                self.assertEqual(row['content'][key],source['content'][key])
            for key in ('correct_text','explanation','answer_aliases','identifying_hints','future_semantic_field'):
                self.assertEqual(row['content']['private_review'][key],source['content']['private_review'][key])
            self.assertNotIn('sources',row['content'])
            self.assertNotIn('notes',row['content']['private_review'])
        self.assertLess(len(''.join(context_pages(original))),len(''.join(context_pages(original,full=True)))/2)

    def test_full_pages_are_lossless_even_across_a_very_long_unicode_field(self):
        original=self.context();original['extra']='čćšžđ😀'*12000
        pages=context_pages(original,full=True)
        self.assertGreater(len(pages),10)
        self.assertEqual(json.loads(''.join(pages)),original)
        index=context_index(original)
        self.assertEqual(index['full_pages'],len(pages))
        self.assertTrue(all(len(p.encode('utf-8'))<=index['page_bytes'] for p in pages))
        self.assertIn('čćšžđ😀',''.join(pages))
        self.assertEqual(json.loads(''.join(context_pages(original)))['extra'],original['extra'])

    def test_cli_reads_only_one_bounded_page_and_rejects_missing_or_out_of_range_pages(self):
        context=self.context()
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.research_context.ROOT',Path(temp)):
            write_json(Path(temp)/'build/preparation-context.json',context)
            output=io.StringIO()
            with patch('sys.argv',['context','index']),redirect_stdout(output):main()
            index=json.loads(output.getvalue());self.assertEqual(index['history_batches'],34)
            for full in (False,True):
                pages=context_pages(context,full=full)
                for number in (1,len(pages)):
                    output=io.StringIO()
                    with patch('sys.argv',['context','page',str(number)]+(['--full'] if full else [])),redirect_stdout(output):main()
                    lines=output.getvalue().splitlines()
                    self.assertEqual(lines[1],pages[number-1])
                    self.assertLess(len(output.getvalue().encode()),8500)
                    self.assertIn(str(number)+'/'+str(len(pages)),lines[0])
            for args in (['page'],['page','0'],['page','-1'],['page','99999'],['index','1'],['index','--full']):
                with patch('sys.argv',['context',*args]),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main()

    def test_original_full_history_still_rejects_repetition_in_the_oldest_import(self):
        context=self.context();package=reviewed_fixture();package['theme']=copy.deepcopy(context['history']['days'][0]['content']['theme'])
        original=copy.deepcopy(context['history'])
        review_context(context)
        with self.assertRaisesRegex(ValueError,'repeats history'):
            validate(package,novelty_history(context['history'],package['date'],{'choice':'new'}),include_today=True)
        self.assertEqual(context['history'],original)

    def test_prompt_states_page_count_and_requires_inspection_rather_than_only_parsing(self):
        instructions=reading_instructions(self.context())
        self.assertIn('"review_pages":',instructions)
        self.assertIn('one page per tool call',instructions)
        self.assertIn('max_output_tokens=10000',instructions)
        self.assertIn('read through review_pages',instructions)
