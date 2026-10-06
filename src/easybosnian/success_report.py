"""Private successful-publication reports for GitHub summaries and artifacts."""
import argparse
import html
import json
import os
import re
from urllib.parse import urlparse

from .batches import output_key
from .designs import DESIGNS, BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES, MARKER_STYLES, CATEGORY_STYLES, PHOTO_TONES
from .visual_diagnostics import safe_rejection, rendering_outcome
from .core import PROJECT, REPO, ROOT, read_json, write_json

LABELS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}
PLATFORMS={'instagram':'Instagram','facebook':'Facebook','tiktok':'TikTok','instagram_stories':'Instagram Stories','facebook_stories':'Facebook Stories'}


def content_data(package,run_url):
    if package['project']!=PROJECT or not re.fullmatch(r'https://github\.com/'+re.escape(REPO)+r'/actions/runs/\d+',run_url):
        raise ValueError('Report belongs to another project/run')
    return {'project':PROJECT,'date':package['date'],'batch_id':output_key(package),'theme':package['theme']['name'],
            'difficulty':package.get('bosnian_level','not recorded'),'palette':package['design_palette'],'run_url':run_url,
            'cards':[{'category':LABELS[c['kind']],'heading':c.get('heading',c.get('question')),'prompt':c['background_prompt']} for c in package['cards']]}


def publication_data(results):
    if results.get('instagram',{}).get('published') is not True or any('error' in result for result in results.values()):
        raise ValueError('Only successful publication results can create a success report')
    if results['instagram'].get('poll',{}).get('failed'):
        raise ValueError('Native poll failed; do not claim a fully successful run')
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
        if key=='instagram' and result.get('poll'):
            from .instagram_poll import POLL_MESSAGES
            reason=result['poll'].get('reason')
            if reason not in POLL_MESSAGES:raise ValueError('Invalid safe native poll report status')
            platforms[-1]['poll_status']=POLL_MESSAGES[reason]
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
    return {**source,'platforms':publication_data(outcome['platforms']),
            'history_cleanup_warning':outcome.get('history_cleanup',{}).get('status','').startswith('failed')}


def with_rendering(data,placement):
    if placement['batch']!=data['date'] or placement.get('batch_id')!=data['batch_id'] or set(placement['cards'])!=set(LABELS):
        raise ValueError('Rendering report differs from the prepared batch')
    palettes=set()
    catalogue=read_json(ROOT/'data/design-palettes.json')
    rendered={}
    for kind,result in placement['cards'].items():
        if result['palette'] not in catalogue or result['position'] not in ('free','normal','separate_photo'):
            raise ValueError('Invalid safe rendering metadata')
        design=result.get('design','hybrid')  # Older private reports remain readable.
        styles=result.get('block_styles',{})
        if design not in DESIGNS or not isinstance(styles,dict) or any(
                role not in ('body','example','A','B','C','D') or style not in (EXAMPLE_STYLES if role=='example' else BODY_STYLES if role=='body' else ANSWER_STYLES)
                for role,style in styles.items()):
            raise ValueError('Invalid safe design metadata')
        badges=result.get('answer_badges',{})
        if not isinstance(badges,dict) or any(role not in ('A','B','C','D') or style not in MARKER_STYLES for role,style in badges.items()):
            raise ValueError('Invalid safe answer badge metadata')
        palettes.add(result['palette'])
        safe_typography={}
        from .designs import typography
        for role,values in result.get('block_typography',{}).items():
            if role not in styles or not isinstance(values,dict) or set(values)!= {'font_size','line_spacing','max_lines','wrapping'}:
                raise ValueError('Invalid safe typography metadata')
            typography(role,values['font_size'],values['line_spacing'],values['max_lines'],values['wrapping'])
            safe_typography[role]=dict(values)
        rendered[LABELS[kind]]={'palette':result['palette'],'position':result['position'],'design':design,
                               'block_styles':styles,'answer_badges':badges,'block_typography':safe_typography,
                               'outcome':rendering_outcome(result,placement.get('status'))}
        for field,allowed in (('category_style',CATEGORY_STYLES),('heading_tone',PHOTO_TONES),('example_tone',(*PHOTO_TONES,None))):
            if field in result:
                if result[field] not in allowed:raise ValueError('Invalid safe colour/category metadata')
                rendered[LABELS[kind]][field]=result[field]
        if result.get('rejection') is not None:rendered[LABELS[kind]]['rejection']=safe_rejection(result['rejection'])

    return {**data,'final_palette':next(iter(palettes)) if len(palettes)==1 else 'per card',
            'cards':[{**card,'rendering':rendered[card['category']]} for card in data['cards']]}


def markdown_text(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>\-])',r'\\\1',html.escape(str(value),quote=False))


def render_report(data):
    text='## EasyBosnian — successful-run report\n\n'
    for label,key in [('Content date','date'),('Batch ID','batch_id'),('Theme','theme'),('Difficulty','difficulty'),('Palette','palette')]:
        text+=f"- **{label}:** {markdown_text(data[key])}\n"
    if data.get('final_palette'):text+=f"- **Photo-reviewed final palette:** {markdown_text(data['final_palette'])}\n"
    text+=f"\n[Open this run]({data['run_url']})\n\n### Exact FLUX prompts\n\n"
    for card in data['cards']:
        fence='`'*max(3,1+max((len(run) for run in re.findall(r'`+',card['prompt'])),default=0))
        text+=f"#### {markdown_text(card['category'])}\n\n**Card:** {markdown_text(card['heading'])}\n\n"
        if card.get('rendering'):text+=f"**Final rendering:** {markdown_text(card['rendering']['palette'])} / {markdown_text(card['rendering']['design'])} / {markdown_text(card['rendering']['position'])}; {markdown_text(', '.join(role+': '+style for role,style in card['rendering']['block_styles'].items()))}. Lora headings, Inter body.\n\n"
        outcome=card.get('rendering',{}).get('outcome')
        if outcome:text+='**Visual decision — '+markdown_text(outcome['source'])+':** '+markdown_text(outcome['reason'])+'\n\n'
        rejection=card.get('rendering',{}).get('rejection')
        if rejection:
            safe=safe_rejection(rejection)
            text+='**Layout fallback:** '+markdown_text(safe['reason'])+'\n\n'
            text+='<details><summary>Rejected approved rendering parameters</summary>\n\n```json\n'+json.dumps(safe['proposal'],ensure_ascii=False,indent=2)+'\n```\n\n</details>\n\n'
        text+=f"{fence}text\n{card['prompt']}\n{fence}\n\n"
    text+='### Publication results\n\n'
    for platform in data['platforms']:
        text+=f"**{markdown_text(platform['name'])}:** {markdown_text(platform['status'])}\n\n"
        if platform.get('poll_status'):text+='Native Pitanje dana poll: '+markdown_text(platform['poll_status'])+'\n\n'
        for link in platform['links']:
            target=link.replace('<','%3C').replace('>','%3E')
            text+=f'- [Open published content](<{target}>)\n'
        text+='\n'
        if platform['cleanup_warning']:text+='> Replacement cleanup warning: earlier content may remain.\n\n'
    text+='\nResults describe this run at completion. Later replacements or expired Stories may change link availability.\n'
    if data.get('history_cleanup_warning'):text+='\n> Earlier current-date history could not be fully removed; some entries may remain.\n'
    # Everything is escaped; no remote images, scripts or answer-key/review fields.
    markup='<!doctype html><html><head><meta charset="utf-8"><title>EasyBosnian report</title></head><body><main style="font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:24px auto;padding:24px;color:#203142"><h1>EasyBosnian — successful-run report</h1><ul>'
    for label,key in [('Content date','date'),('Batch ID','batch_id'),('Theme','theme'),('Difficulty','difficulty'),('Palette','palette')]:
        markup+='<li><strong>'+label+':</strong> '+html.escape(str(data[key]))+'</li>'
    if data.get('final_palette'):markup+='<li><strong>Photo-reviewed final palette:</strong> '+html.escape(data['final_palette'])+'</li>'
    markup+='</ul><p><a href="'+html.escape(data['run_url'],quote=True)+'">Open this run</a></p><h2>Exact FLUX prompts</h2>'
    for card in data['cards']:
        markup+='<section><h3>'+html.escape(card['category'])+'</h3><p>'+html.escape(card['heading'])+'</p>'
        if card.get('rendering'):markup+='<p>Final rendering: '+html.escape(card['rendering']['palette'])+' / '+html.escape(card['rendering']['design'])+' / '+html.escape(card['rendering']['position'])+'; '+html.escape(', '.join(role+': '+style for role,style in card['rendering']['block_styles'].items()))+'. Lora headings, Inter body.</p>'
        outcome=card.get('rendering',{}).get('outcome')
        if outcome:markup+='<p><strong>Visual decision — '+html.escape(outcome['source'])+':</strong> '+html.escape(outcome['reason'])+'</p>'
        rejection=card.get('rendering',{}).get('rejection')
        if rejection:
            safe=safe_rejection(rejection)
            markup+='<p><strong>Layout fallback:</strong> '+html.escape(safe['reason'])+'</p><details><summary>Rejected approved rendering parameters</summary><pre>'+html.escape(json.dumps(safe['proposal'],ensure_ascii=False,indent=2))+'</pre></details>'
        markup+='<pre style="padding:16px;background:#f1f5f9;white-space:pre-wrap;overflow-wrap:anywhere">'+html.escape(card['prompt'])+'</pre></section>'
    markup+='<h2>Publication results</h2>'
    for platform in data['platforms']:
        markup+='<p><strong>'+html.escape(platform['name'])+':</strong> '+html.escape(platform['status'])+'</p><ul>'
        for link in platform['links']:markup+='<li><a href="'+html.escape(link,quote=True)+'">Open published content</a></li>'
        markup+='</ul>'
        if platform.get('poll_status'):markup+='<p>Native Pitanje dana poll: '+html.escape(platform['poll_status'])+'</p>'
        if platform['cleanup_warning']:markup+='<p>Replacement cleanup warning: earlier content may remain.</p>'
    if data.get('history_cleanup_warning'):markup+='<p>Earlier current-date history could not be fully removed; some entries may remain.</p>'
    markup+='<p>Results describe this run at completion. Later replacements or expired Stories may change link availability.</p></main></body></html>'
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['build']);parser.parse_args()
    try:
        from .cli import prepared_batch
        date,batch_id,_=prepared_batch('daily')
        source=read_json(ROOT/'build'/batch_id/'report-source.json')
        outcome=read_json(ROOT/'build'/batch_id/'platforms-result.json')
        data=saved_report_data(source,outcome,date,batch_id,os.environ['GITHUB_RUN_URL'])
        placement=ROOT/'build'/batch_id/'image-placement-result.json'
        if placement.is_file():data=with_rendering(data,read_json(placement))
        write_report(data)
        print('Private success report prepared in the run summary and artifact')
    except Exception as error:
        status=str(error) if isinstance(error,ValueError) else 'Report step failed; inspect private artifact/access'
        # Never print private result data or free-form model output.
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as summary:summary.write('\nSuccess report preparation not confirmed. '+status+'\n')
        print('::warning::'+status)
        raise SystemExit(1) from None


if __name__=='__main__':main()
