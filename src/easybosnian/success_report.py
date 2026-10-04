"""Private successful-publication reports and one Gmail SMTP attempt; no publishing."""
import argparse
import html
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse

import certifi

from .batches import output_key
from .core import PROJECT, REPO, ROOT, read_json, verify_repository, write_json
from .http import SafeError

LABELS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}
PLATFORMS={'instagram':'Instagram','facebook':'Facebook','tiktok':'TikTok','instagram_stories':'Instagram Stories','facebook_stories':'Facebook Stories'}


def content_data(package,run_url):
    if package['project']!=PROJECT or not re.fullmatch(r'https://github\.com/'+re.escape(REPO)+r'/actions/runs/\d+',run_url):
        raise ValueError('Report belongs to another project/run')
    return {'project':PROJECT,'date':package['date'],'batch_id':output_key(package),'theme':package['theme']['name'],
            'difficulty':package.get('bosnian_level','not recorded'),'palette':package['design_palette'],'run_url':run_url,
            'cards':[{'category':LABELS[c['kind']],'heading':c.get('heading',c.get('question')),'layout':c['design_template'],'prompt':c['background_prompt']} for c in package['cards']]}


def publication_data(results):
    if results.get('instagram',{}).get('published') is not True or any('error' in result for result in results.values()):
        raise ValueError('Only successful publication results can create a success report')
    platforms=[]
    for key,label in PLATFORMS.items():
        result=results.get(key,{})
        if result.get('published') is not True and result.get('status') not in ('disabled','disabled or Instagram feed publication not confirmed in this run','disabled or Facebook feed publication not confirmed in this run'):
            raise ValueError('Publication is incomplete; no success report')
        links=[result.get('permalink'),*(item.get('permalink') for item in result.get('stories',[]))]
        allowed={'instagram.com','www.instagram.com','facebook.com','www.facebook.com','m.facebook.com','tiktok.com','www.tiktok.com'}
        links=[link for link in links if isinstance(link,str) and urlparse(link).scheme=='https' and urlparse(link).hostname in allowed]
        cleanup=result.get('replacement_cleanup',{}).get('status','')
        platforms.append({'name':label,'status':result.get('status','disabled'),'links':links,'cleanup_warning':cleanup.startswith('failed')})
    return platforms


def report_data(package,results,run_url):
    return {**content_data(package,run_url),'platforms':publication_data(results)}


def saved_report_data(source,outcome,date,batch_id,run_url):
    if (source['project']!=PROJECT or source['run_url']!=run_url
            or source['date']!=date or source['batch_id']!=batch_id
            or outcome['batch_id']!=batch_id or outcome['batch']!=date):
        raise ValueError('Report content/result differs from the prepared batch/run')
    # The rendering input was captured locally before generation. Never reread
    # a mutable history row that a later replacement might already have changed.
    return {**source,'platforms':publication_data(outcome['platforms'])}


def render_report(data):
    text=f"EasyBosnian — successful publication report\n\nContent date: {data['date']}\nBatch ID: {data['batch_id']}\nTheme: {data['theme']}\nDifficulty: {data['difficulty']}\nPalette: {data['palette']}\nRun: {data['run_url']}\n\n"
    for card in data['cards']:
        text+=f"{card['category']} — {card['heading']}\nLayout: {card['layout']}\n\nExact FLUX prompt:\n{card['prompt']}\n\n"
    text+='Publication results\n\n'
    for platform in data['platforms']:
        text+=f"{platform['name']}: {platform['status']}\n"+'\n'.join(platform['links'])+'\n'
        if platform['cleanup_warning']:text+='Replacement cleanup warning: earlier content may remain.\n'
    text+='\nResults describe this run at completion. Later replacements or expired Stories may change link availability.\n'
    # Everything is escaped; no remote images, scripts or answer-key/review fields.
    markup='<!doctype html><html><head><meta charset="utf-8"></head><body><div style="font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:auto;color:#203142"><h1>EasyBosnian report</h1><pre style="font:inherit;white-space:pre-wrap;overflow-wrap:anywhere">'+html.escape(text)+'</pre></div></body></html>'
    return text,markup


def write_report(data):
    directory=ROOT/'build'/data['batch_id'];directory.mkdir(parents=True,exist_ok=True)
    text,markup=render_report(data)
    write_json(directory/'success-report.json',data)
    (directory/'success-report.md').write_text(text,encoding='utf-8')
    (directory/'success-report.html').write_text(markup,encoding='utf-8')
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as summary:summary.write('\n'+text)
    return directory


def gmail_credentials():
    address=os.getenv('REPORT_EMAIL_TO','').strip()
    password=''.join(os.getenv('REPORT_GMAIL_APP_PASSWORD','').split())
    if not re.fullmatch(r'[A-Za-z0-9._+\-]+@(?:gmail|googlemail)\.com',address):
        raise ValueError('Set REPORT_EMAIL_TO to the authorized Gmail address')
    if not re.fullmatch(r'[A-Za-z0-9]{16}',password):
        raise ValueError('Set the private 16-character REPORT_GMAIL_APP_PASSWORD secret')
    return address,password


def gmail_operation(data=None):
    verify_repository(remote=True);address,password=gmail_credentials()
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=30,context=ssl.create_default_context(cafile=certifi.where())) as client:
            client.login(address,password)
            if data is not None:
                text,markup=render_report(data);message=EmailMessage()
                message['From']=address;message['To']=address
                message['Subject']='EasyBosnian — '+data['date']+' — '+' '.join(data['theme'].split())
                message.set_content(text);message.add_alternative(markup,subtype='html')
                if client.send_message(message):raise RuntimeError('Recipient refused')
    except Exception as error:
        code=getattr(error,'smtp_code',None);code=code if type(code) is int else 'unavailable'
        raise SafeError(f'Report email operation not confirmed; SMTP code {code}; check Gmail authorization; no resend') from None
    return {'status':'SMTP accepted the report; inbox delivery not independently confirmed' if data is not None else 'Gmail TLS/login verified; no email sent'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['build','check','send']);args=parser.parse_args()
    try:
        if args.action=='check':result=gmail_operation()
        else:
            from .cli import prepared_batch
            date,batch_id,_=prepared_batch('daily')
            if args.action=='build':
                source=read_json(ROOT/'build'/batch_id/'report-source.json')
                outcome=read_json(ROOT/'build'/batch_id/'platforms-result.json')
                data=saved_report_data(source,outcome,date,batch_id,os.environ['GITHUB_RUN_URL']);write_report(data)
                result={'status':'Private success report prepared','batch_id':batch_id,'prompts':len(data['cards'])}
            elif os.getenv('SUCCESS_REPORT_EMAIL_ENABLED')!='true':result={'status':'Report email disabled; sending credential setup pending'}
            else:
                data=read_json(ROOT/'build'/batch_id/'success-report.json')
                if (data['date']!=date or data['batch_id']!=batch_id or data['project']!=PROJECT
                        or data['run_url']!=os.environ['GITHUB_RUN_URL']):raise ValueError('Wrong report batch/run')
                result=gmail_operation(data)
        if args.action!='build' and os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as summary:summary.write('\nReport email: '+result['status']+'\n')
        print(result['status'])
    except Exception as error:
        status=str(error) if isinstance(error,(ValueError,SafeError)) else 'Report step failed; inspect private artifact/access; no resend'
        # Known messages only; never SMTP response prose or credentials.
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as summary:summary.write('\nReport email/report preparation not confirmed. '+status+'\n')
        print('::warning::'+status)
        raise SystemExit(1) from None


if __name__=='__main__':main()
