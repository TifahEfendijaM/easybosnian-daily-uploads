import copy
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from easybosnian.core import REPO,ROOT
from easybosnian.success_report import content_data, main, render_report, report_data, saved_report_data, write_report
from test_project import reviewed_fixture

RUN='https://github.com/'+REPO+'/actions/runs/123'


def results():
    return {'instagram':{'published':True,'status':'published','permalink':'https://www.instagram.com/p/example/'},
            'facebook':{'published':False,'status':'disabled'},'tiktok':{'published':False,'status':'disabled'},
            'instagram_stories':{'published':False,'status':'disabled or Instagram feed publication not confirmed in this run'},
            'facebook_stories':{'published':False,'status':'disabled or Facebook feed publication not confirmed in this run'}}


class SuccessReportTests(unittest.TestCase):
    def test_captured_rendering_input_survives_history_replacement_and_refuses_other_run_batch(self):
        package=reviewed_fixture();source=content_data(package,RUN)
        outcome={'batch':package['date'],'batch_id':package['date'],'platforms':results()}
        original=source['cards'][0]['prompt'];package['cards'][0]['background_prompt']='Later replacement prompt'
        data=saved_report_data(source,outcome,package['date'],package['date'],RUN)
        self.assertEqual(data['cards'][0]['prompt'],original)
        for field,value in [('batch_id','b-'+'a'*32),('batch','2026-10-05')]:
            bad=copy.deepcopy(outcome);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):saved_report_data(source,bad,package['date'],package['date'],RUN)
        with self.assertRaises(ValueError):saved_report_data(source,outcome,package['date'],package['date'],RUN+'4')

    def test_report_build_reads_local_exact_run_input_without_cloud_history_access(self):
        package=reviewed_fixture();source=content_data(package,RUN)
        outcome={'batch':package['date'],'batch_id':package['date'],'platforms':results()}
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.success_report.ROOT',Path(temp)),patch('sys.argv',['report','build']),patch.dict(os.environ,{'GITHUB_RUN_URL':RUN}),patch('easybosnian.cli.prepared_batch',return_value=(package['date'],package['date'],False)),patch('easybosnian.store.Store') as store,redirect_stdout(io.StringIO()):
            from easybosnian.core import write_json
            directory=Path(temp)/'build'/package['date']
            write_json(directory/'report-source.json',source);write_json(directory/'platforms-result.json',outcome)
            main();store.assert_not_called()
            self.assertIn(source['cards'][0]['prompt'],(directory/'success-report.md').read_text())

    def test_reports_include_exact_prompts_design_and_links_but_no_answer_key_or_review(self):
        package=reviewed_fixture();data=report_data(package,results(),RUN)
        text,markup=render_report(data)
        for card in package['cards']:self.assertIn(card['background_prompt'],text)
        for private in ('correct_option','correct_text','answer_aliases','private_review','sources_checked'):
            self.assertNotIn(private,str(data));self.assertNotIn(private,markup)
        self.assertIn('https://www.instagram.com/p/example/',text)
        self.assertEqual([c['layout'] for c in data['cards']],[c['design_template'] for c in package['cards']])

    def test_html_escapes_content_and_report_files_remain_in_its_batch_directory(self):
        package=reviewed_fixture();package['cards'][1]['background_prompt']='<script>alert(1)</script>'
        data=report_data(package,results(),RUN);text,markup=render_report(data)
        self.assertNotIn('<script>',markup);self.assertIn('&lt;script&gt;',markup)
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.success_report.ROOT',Path(temp)):
            directory=write_report(data)
            self.assertEqual(directory,Path(temp)/'build'/package['date'])
            self.assertEqual((directory/'success-report.md').read_text(),text)

    def test_failed_partial_or_foreign_results_do_not_create_success_reports(self):
        for change in ('ig','fb','story','foreign'):
            p=reviewed_fixture();r=results();url=RUN
            if change=='ig':r['instagram']['published']=False
            elif change=='fb':r['facebook']={'published':False,'status':'failed','error':'private'}
            elif change=='story':r['instagram_stories']={'published':False,'status':'partial'}
            else:url='https://github.com/other/repo/actions/runs/123'
            with self.subTest(change=change),self.assertRaises(ValueError):report_data(p,r,url)

    def test_github_summary_has_copyable_prompts_and_no_email_setup_or_send(self):
        data=report_data(reviewed_fixture(),results(),RUN)
        with tempfile.TemporaryDirectory() as temp,patch('easybosnian.success_report.ROOT',Path(temp)),patch.dict(os.environ,{'GITHUB_STEP_SUMMARY':str(Path(temp)/'summary.md')}):
            write_report(data)
            text=(Path(temp)/'summary.md').read_text()
            self.assertIn('## EasyBosnian — successful-run report',text)
            self.assertEqual(text.count('```text'),3)
            self.assertIn('### Publication results',text)
            self.assertIn('Open published content',text)
        workflow=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
        steps=workflow['jobs']['run']['steps'];report=next(s for s in steps if s.get('id')=='report')
        self.assertIn("inputs.mode == 'daily'",report['if'])
        self.assertIn("steps.publication.outcome == 'success'",report['if'])
        self.assertEqual(report['continue-on-error'],'true')
        self.assertLess(steps.index(report),next(i for i,s in enumerate(steps) if s.get('uses')=='actions/upload-artifact@v4'))
        self.assertNotIn('GMAIL',str(workflow));self.assertNotIn('EMAIL',str(workflow))

    def test_prompt_fences_cannot_break_out_or_change_the_original_prompt(self):
        p=reviewed_fixture();p['cards'][0]['background_prompt']='Exact prompt with ``` and <script> tagged content'
        text,markup=render_report(report_data(p,results(),RUN))
        self.assertIn('````text\n'+p['cards'][0]['background_prompt']+'\n````',text)
        self.assertNotIn('<script>',markup)
