import copy
import io
import os
import smtplib
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from easybosnian.core import REPO,ROOT
from easybosnian.http import SafeError
from easybosnian.success_report import content_data, gmail_operation, main, render_report, report_data, saved_report_data, write_report
from test_project import reviewed_fixture

RUN='https://github.com/'+REPO+'/actions/runs/123'
PASSWORD='abcdefghijklmnop'


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

    def test_smtp_uses_tls_and_sends_exactly_once_to_authorized_own_address(self):
        data=report_data(reviewed_fixture(),results(),RUN)
        with patch.dict(os.environ,{'REPORT_EMAIL_TO':'owner@gmail.com','REPORT_GMAIL_APP_PASSWORD':'abcd efgh ijkl mnop'}),patch('easybosnian.success_report.verify_repository'),patch('easybosnian.success_report.smtplib.SMTP_SSL') as smtp:
            client=smtp.return_value.__enter__.return_value;client.send_message.return_value={}
            self.assertIn('accepted',gmail_operation(data)['status'])
            self.assertEqual(smtp.call_args.args,('smtp.gmail.com',465));self.assertEqual(smtp.call_args.kwargs['timeout'],30)
            client.login.assert_called_once_with('owner@gmail.com',PASSWORD)
            client.send_message.assert_called_once()
            message=client.send_message.call_args.args[0]
            self.assertEqual(message['To'],'owner@gmail.com');self.assertEqual(message['From'],'owner@gmail.com')
            self.assertIn(data['cards'][0]['prompt'],message.get_body(preferencelist=('plain',)).get_content())

    def test_authentication_check_never_sends_and_errors_never_echo_credentials_or_retry(self):
        env={'REPORT_EMAIL_TO':'owner@gmail.com','REPORT_GMAIL_APP_PASSWORD':PASSWORD}
        with patch.dict(os.environ,env),patch('easybosnian.success_report.verify_repository'),patch('easybosnian.success_report.smtplib.SMTP_SSL') as smtp:
            client=smtp.return_value.__enter__.return_value
            self.assertIn('no email sent',gmail_operation()['status']);client.send_message.assert_not_called()
            client.login.reset_mock();client.login.side_effect=smtplib.SMTPAuthenticationError(535,PASSWORD.encode())
            with self.assertRaises(SafeError) as error:gmail_operation()
            self.assertIn('535',str(error.exception));self.assertNotIn(PASSWORD,str(error.exception));client.login.assert_called_once()

    def test_ambiguous_send_failure_is_not_retried_or_logged_verbatim(self):
        with patch.dict(os.environ,{'REPORT_EMAIL_TO':'owner@gmail.com','REPORT_GMAIL_APP_PASSWORD':PASSWORD}),patch('easybosnian.success_report.verify_repository'),patch('easybosnian.success_report.smtplib.SMTP_SSL') as smtp:
            client=smtp.return_value.__enter__.return_value;client.send_message.side_effect=TimeoutError(PASSWORD)
            with self.assertRaises(SafeError) as error:gmail_operation(report_data(reviewed_fixture(),results(),RUN))
            self.assertNotIn(PASSWORD,str(error.exception));client.send_message.assert_called_once()

    def test_disabled_mail_does_not_connect_or_send(self):
        with patch.dict(os.environ,{'SUCCESS_REPORT_EMAIL_ENABLED':'false'}),patch('sys.argv',['report','send']),patch('easybosnian.cli.prepared_batch',return_value=('2026-10-04','b-'+'a'*32,False)),patch('easybosnian.success_report.gmail_operation') as smtp,redirect_stdout(io.StringIO()):
            main();smtp.assert_not_called()

    def test_workflow_success_only_mail_and_credential_isolation(self):
        workflow=yaml.load((ROOT/'.github/workflows/preparation.yml').read_text(),Loader=yaml.BaseLoader)
        job=workflow['jobs']['run'];self.assertNotIn('REPORT_GMAIL_APP_PASSWORD',job['env'])
        report=next(s for s in job['steps'] if s.get('id')=='report')
        self.assertIn("inputs.mode == 'daily'",report['if']);self.assertEqual(report['continue-on-error'],'true')
        email=job['steps'][-1];self.assertEqual(email['run'],'python -m easybosnian.success_report send')
        self.assertIn("steps.publication.outcome == 'success'",email['if']);self.assertIn("steps.report.outcome == 'success'",email['if'])
        self.assertEqual(email['continue-on-error'],'true')
        check=next(s for s in job['steps'] if s.get('run')=='python -m easybosnian.success_report check')
        self.assertIn("inputs.mode == 'verify'",check['if'])
