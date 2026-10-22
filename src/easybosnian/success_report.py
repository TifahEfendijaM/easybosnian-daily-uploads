"""Private successful-publication reports for GitHub summaries and artifacts."""
import argparse
import html
import json
import os
import re
from urllib.parse import urlparse

from .batches import output_key
from .designs import (DESIGNS, BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES,
                      MARKER_STYLES, CATEGORY_STYLES, PHOTO_TONES,
                      STYLE_CATALOGUE, CATEGORY_CATALOGUE, PHOTO_TONE_CATALOGUE, TITLE_TONE_CATALOGUE, panel_alpha, PANEL_STYLES,
                      PANEL_TONES, FADE_STYLES)
from .visual_diagnostics import safe_rejection, rendering_outcome, rendering_provenance, approved_proposal
from .core import PROJECT, REPO, ROOT, read_json, write_json

LABELS={'quiz':'Pitanje dana','lesson':'Znaš li?','word':'Riječ dana'}
PLATFORMS={'instagram':'Instagram','facebook':'Facebook','tiktok':'TikTok','instagram_stories':'Instagram Stories','facebook_stories':'Facebook Stories'}


def content_data(package,run_url):
    if package['project']!=PROJECT or not re.fullmatch(r'https://github\.com/'+re.escape(REPO)+r'/actions/runs/\d+',run_url):
        raise ValueError('Report belongs to another project/run')
    return {'project':PROJECT,'date':package['date'],'batch_id':output_key(package),'theme':package['theme']['name'],
            'difficulty':package.get('bosnian_level','not recorded'),'palette':package['design_palette'],'run_url':run_url,
            'backgrounds_reused':os.getenv('CONTENT_SELECTION')=='same_images',
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
                               'outcome':rendering_outcome(result,placement.get('status')),
                               'provenance':rendering_provenance(result,placement.get('status'))}
        for field,allowed in (('category_style',CATEGORY_STYLES),('heading_tone',PHOTO_TONES),('example_tone',(*PHOTO_TONES,None))):
            if field in result:
                if result[field] not in allowed:raise ValueError('Invalid safe colour/category metadata')
                rendered[LABELS[kind]][field]=result[field]
        if 'heading_backing' in result:
            if result['heading_backing'] not in (None,'#000000','#ffffff'):raise ValueError('Invalid safe title backing metadata')
            rendered[LABELS[kind]]['heading_backing']=result['heading_backing']
        if result.get('layout_adjustment') is not None:
            from .visual_adjustment import safe_adjustment
            rendered[LABELS[kind]]['layout_adjustment']=safe_adjustment(result['layout_adjustment'])
        if result.get('composition') is not None:
            composition=approved_proposal(result['composition'])
            if composition is None:
                raise ValueError('Invalid safe final composition metadata')
            if (composition['design']!=design or
                    {block['role']:block['style'] for block in composition['blocks']}!=styles or
                    composition.get('palette',result['palette'])!=result['palette']):
                raise ValueError('Final composition differs from rendered design metadata')
            rendered[LABELS[kind]]['composition']=composition
        if 'render_policy' in result:
            from .visual_policy import safe_policy
            composition=rendered[LABELS[kind]].get('composition')
            if composition is None:raise ValueError('Rendering policy requires the final composition')
            rendered[LABELS[kind]]['render_policy']=safe_policy(result['render_policy'],composition)
            if (result['render_policy'].get('version') in (3,4) and result.get('heading_backing')=='#ffffff'
                    and composition.get('heading_fade')!='defined'):
                raise ValueError('White title edge differs from the fixed rendering policy')
        if result.get('layout_adjustment') is not None:
            final=rendered[LABELS[kind]].get('composition')
            if final is None:raise ValueError('Placement adjustment differs from rendered composition')
            for move in rendered[LABELS[kind]]['layout_adjustment']['moves']:
                target=final['photo_window'] if move['element']=='photo_window' else next(
                    (b for b in final['blocks'] if b['role']==move['element']),None)
                if target is None or any(target[k]!=v for k,v in move['to'].items()):
                    raise ValueError('Placement adjustment differs from rendered composition')
        if result.get('rejection') is not None:rendered[LABELS[kind]]['rejection']=safe_rejection(result['rejection'])
        if result.get('palette_rejection') is not None:rendered[LABELS[kind]]['palette_rejection']=safe_rejection(result['palette_rejection'])

    return {**data,'final_palette':next(iter(palettes)) if len(palettes)==1 else 'per card',
            'cards':[{**card,'rendering':rendered[card['category']]} for card in data['cards']]}


def markdown_text(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>\-])',r'\\\1',html.escape(str(value),quote=False))


def decision_lines(rendering):
    """Describe the applied enums/geometry, never invent the model's reasoning."""
    lines=['Palette: '+rendering['palette']+'.', 'Design family: '+rendering['design']+'.']
    composition=rendering.get('composition')
    policy=rendering.get('render_policy')
    if policy:
        answers=composition and any(b['role'] in ('A','B','C','D') for b in composition['blocks'])
        if policy.get('version') in (2,3,4) and answers:
            lines.append('Answer panel opacity: fixed at 100%; every option surface is fully opaque.')
        else:
            limits='85–100%' if policy.get('version') in (2,3,4) else '70–100%'
            lines.append(f"Shared panel opacity: {policy['panel_opacity']:g}%; uniformly sampled by the pipeline from "+limits+', '+
                         ('applied to every bounded panel in this image.' if policy['panel_opacity_applied'] else 'inactive for unboxed editorial text.'))
        if policy['example_fade'] is not None:
            if policy.get('version')==4:
                source={'chatgpt':'ChatGPT-selected preset — ','fallback':'deterministic fallback preset — '}.get(
                    rendering.get('provenance',{}).get('layout',{}).get('source'),'source not recorded — ')
            else:
                source='fixed crisp-edged preset — ' if policy.get('version')==3 else 'independent random 50/50 draw — '
            lines.append('PRIMJER shade selection: '+source+policy['example_fade']+
                         (' applied.' if policy['example_fade_applied'] else ' inactive for this unshaded/paper example.'))
    window=composition.get('photo_window') if composition else None
    if composition:
        lines.append('Photo layout: '+('separate '+window['fit']+' photo window' if window else 'full photographic background')+'.')
    category=rendering.get('category_style')
    if category:lines.append('Category: '+CATEGORY_CATALOGUE[category])
    tone=rendering.get('heading_tone')
    if tone:lines.append('Title: '+(TITLE_TONE_CATALOGUE if 'heading_backing' in rendering else PHOTO_TONE_CATALOGUE)[tone])
    if 'heading_backing' in rendering:
        lines.append('Applied title backing: '+{None:'none needed','#000000':'neutral black','#ffffff':'neutral white'}[rendering['heading_backing']]+'.')
        if rendering['heading_backing']=='#ffffff' and policy and policy.get('version') in (3,4):
            lines.append('White title edge: fixed defined treatment; very gentle outer shade with measured contrast.')
    if composition:
        lines.append('Title fade: '+composition.get('heading_fade','standard')+'.')
        lines.append('Category colour pairing: '+composition.get('category_tone','auto').replace('_',' on ')+'.')
        if (composition.get('palette_exception')=='no_other_suitable_palette'
                and rendering.get('provenance',{}).get('palette',{}).get('source')=='chatgpt'):
            lines.append('Repeated-palette exception: ChatGPT declared no other approved palette suitable.')
    for role,style in rendering['block_styles'].items():
        label='PRIMJER' if role=='example' else 'Explanation' if role=='body' else 'Answer '+role
        lines.append(label+': '+STYLE_CATALOGUE[style])
        if role in rendering['answer_badges']:
            lines.append(label+' badge: '+rendering['answer_badges'][role].replace('_',' ')+'.')
        if role=='example' and rendering.get('example_tone'):
            lines.append('PRIMJER colours: '+PHOTO_TONE_CATALOGUE[rendering['example_tone']])
        if composition:
            block=next(b for b in composition['blocks'] if b['role']==role)
            if style in PANEL_STYLES:
                preset=block.get('panel_opacity')
                alpha=panel_alpha(preset) if preset is not None else (235 if style=='overlay_light' else 255)
                description=(f'{preset:g}%.' if type(preset) in (int,float) else
                             (preset or 'legacy preset')+f' ({round(alpha/255*100)}%).')
                lines.append(label+' surface opacity: '+description)
                lines.append(label+' text/surface pairing: '+block.get('panel_tone','auto').replace('_',' on ')+'.')
            if role=='example':lines.append('PRIMJER fade: '+block.get('fade_style','standard')+'.')
            vertical='upper' if block['y']<450 else 'middle' if block['y']<900 else 'lower'
            centre=block['x']+block['width']/2
            horizontal='left' if centre<450 else 'right' if centre>630 else 'centre'
            lines.append(label+' placement: '+vertical+' '+horizontal+
                         f"; x={block['x']}, y={block['y']}, width={block['width']}; "
                         f"target font {block['font_size']}px, line spacing {block['line_spacing']}×.")
    if rendering.get('layout_adjustment'):
        from .visual_adjustment import safe_adjustment
        for move in safe_adjustment(rendering['layout_adjustment'])['moves']:
            label='Pillow single-line PRIMJER adjustment' if 'width' in move['to'] else 'Pillow placement adjustment'
            lines.append(label+' — '+move['element']+': '+
                         json.dumps(move['from'],sort_keys=True)+' → '+json.dumps(move['to'],sort_keys=True)+'.')
    return lines


def provenance_lines(rendering):
    return [label+' source: '+rendering['provenance'][key]['source']+' — '+rendering['provenance'][key]['reason']
            for label,key in (('Layout','layout'),('Palette','palette'))]


def prompt_block(prompt):
    fence='`'*max(3,1+max((len(run) for run in re.findall(r'`+',prompt)),default=0))
    return f'{fence}text\n{prompt}\n{fence}\n\n'


def visual_summary(source,placement=None):
    """Exact prepared public prompts and actual choices, also for partial runs."""
    if (source['project']!=PROJECT or
            not re.fullmatch(r'https://github\.com/'+re.escape(REPO)+r'/actions/runs/\d+',source['run_url']) or
            (os.getenv('GITHUB_RUN_URL') and source['run_url']!=os.environ['GITHUB_RUN_URL'])):
        raise ValueError('Visual summary belongs to another project/run')
    data=with_rendering(source,placement) if placement else source
    text='\n### Image design decisions and exact FLUX prompts\n\n'
    if data.get('backgrounds_reused'):text+='Original photographs reused; these are their original FLUX prompts. No new inference was sent.\n\n'
    for card in data['cards']:
        text+='#### '+markdown_text(card['category'])+'\n\n'
        rendering=card.get('rendering')
        if rendering:
            text+=''.join('**'+markdown_text(line)+'**\n\n' for line in provenance_lines(rendering))
            text+='**Applied design:**\n\n'+''.join('- '+markdown_text(line)+'\n' for line in decision_lines(rendering))+'\n'
        else:text+='Visual decisions not available: generation/review may not have completed.\n\n'
        text+=prompt_block(card['prompt'])
    return text


def render_report(data):
    text='## EasyBosnian — successful-run report\n\n'
    for label,key in [('Content date','date'),('Batch ID','batch_id'),('Theme','theme'),('Difficulty','difficulty'),('Preparation fallback palette','palette')]:
        text+=f"- **{label}:** {markdown_text(data[key])}\n"
    if data.get('final_palette'):text+=f"- **Final rendered palette:** {markdown_text(data['final_palette'])}\n"
    text+=f"\n[Open this run]({data['run_url']})\n\n### Exact FLUX prompts\n\n"
    if data.get('backgrounds_reused'):text+='Original photographs reused; these are their original FLUX prompts. No new inference was sent.\n\n'
    for card in data['cards']:
        text+=f"#### {markdown_text(card['category'])}\n\n**Card:** {markdown_text(card['heading'])}\n\n"
        if card.get('rendering'):text+=f"**Final rendering:** {markdown_text(card['rendering']['palette'])} / {markdown_text(card['rendering']['design'])} / {markdown_text(card['rendering']['position'])}; {markdown_text(', '.join(role+': '+style for role,style in card['rendering']['block_styles'].items()))}. Lora headings, Inter body.\n\n"
        if card.get('rendering'):
            text+=''.join('**'+markdown_text(line)+'**\n\n' for line in provenance_lines(card['rendering']))
            text+='**Applied design:**\n\n'+''.join('- '+markdown_text(line)+'\n' for line in decision_lines(card['rendering']))+'\n'
        palette_rejection=card.get('rendering',{}).get('palette_rejection')
        if palette_rejection:text+='**Palette fallback:** '+markdown_text(safe_rejection(palette_rejection)['reason'])+'\n\n'
        rejection=card.get('rendering',{}).get('rejection')
        if rejection:
            safe=safe_rejection(rejection)
            text+=('**Placement validation before adjustment:** ' if card['rendering'].get('layout_adjustment') else '**Layout fallback:** ')+markdown_text(safe['reason'])+'\n\n'
            text+='<details><summary>Rejected approved rendering parameters</summary>\n\n```json\n'+json.dumps(safe['proposal'],ensure_ascii=False,indent=2)+'\n```\n\n</details>\n\n'
        text+=prompt_block(card['prompt'])
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
    for label,key in [('Content date','date'),('Batch ID','batch_id'),('Theme','theme'),('Difficulty','difficulty'),('Preparation fallback palette','palette')]:
        markup+='<li><strong>'+label+':</strong> '+html.escape(str(data[key]))+'</li>'
    if data.get('final_palette'):markup+='<li><strong>Final rendered palette:</strong> '+html.escape(data['final_palette'])+'</li>'
    markup+='</ul><p><a href="'+html.escape(data['run_url'],quote=True)+'">Open this run</a></p><h2>Exact FLUX prompts</h2>'
    for card in data['cards']:
        markup+='<section><h3>'+html.escape(card['category'])+'</h3><p>'+html.escape(card['heading'])+'</p>'
        if card.get('rendering'):markup+='<p>Final rendering: '+html.escape(card['rendering']['palette'])+' / '+html.escape(card['rendering']['design'])+' / '+html.escape(card['rendering']['position'])+'; '+html.escape(', '.join(role+': '+style for role,style in card['rendering']['block_styles'].items()))+'. Lora headings, Inter body.</p>'
        if card.get('rendering'):
            markup+=''.join('<p><strong>'+html.escape(line)+'</strong></p>' for line in provenance_lines(card['rendering']))
            markup+='<p><strong>Applied design:</strong></p><ul>'+''.join('<li>'+html.escape(line)+'</li>' for line in decision_lines(card['rendering']))+'</ul>'
        palette_rejection=card.get('rendering',{}).get('palette_rejection')
        if palette_rejection:markup+='<p><strong>Palette fallback:</strong> '+html.escape(safe_rejection(palette_rejection)['reason'])+'</p>'
        rejection=card.get('rendering',{}).get('rejection')
        if rejection:
            safe=safe_rejection(rejection)
            label='Placement validation before adjustment:' if card['rendering'].get('layout_adjustment') else 'Layout fallback:'
            markup+='<p><strong>'+label+'</strong> '+html.escape(safe['reason'])+'</p><details><summary>Rejected approved rendering parameters</summary><pre>'+html.escape(json.dumps(safe['proposal'],ensure_ascii=False,indent=2))+'</pre></details>'
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
