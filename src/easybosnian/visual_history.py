"""Read recent accepted choices from protected reports/legacy artifacts; no visual references."""
import io
import json
import re
import zipfile

from .core import REPO, gh, gh_binary
from .designs import DESIGNS, BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES, CATEGORY_STYLES, MARKER_STYLES, REVIEW_PHOTO_TONES, REVIEW_TITLE_TONES, REVIEW_FADE_STYLES, REVIEW_EXAMPLE_FADE_STYLES, QUIZ_TITLE_SHADE_INTENTS, NONQUIZ_TITLE_SHADE_INTENTS, EXAMPLE_SHADE_STRENGTHS, valid_panel_opacity, PANEL_STYLES, PANEL_TONES, panel_colours

REPEATED_PALETTE='terracotta-sand'  # Legacy default only; fresh policy checks every palette.


def palette_window(recent):
    """Last nine known rendered palette IDs, oldest first; never copy/model prose."""
    from .core import ROOT, read_json
    catalogue=read_json(ROOT/'data/design-palettes.json');values=[]
    for run in reversed(recent):
        observations=run.get('palette_observations')
        if not isinstance(observations,list):
            observations=[run.get('cards',{}).get(k,{}).get('palette') for k in ('quiz','lesson','word')]
        values.extend(v for v in observations if isinstance(v,str) and v in catalogue)
    return values[-9:]


def palette_policy(window, batch=(), palette=REPEATED_PALETTE):
    # The proposed card is the ninth image, so only eight preceding cards
    # remain in its window. Batch usage also counts when older cards age out.
    prior=window[-8:];recent_uses=prior.count(palette)
    batch_uses=batch.count(palette)
    return {'palette':palette,'window_size':9,'known_images':len(prior),
            'max_uses':2,'recent_uses':recent_uses,'max_per_batch':1,'batch_uses':batch_uses,
            'alternatives_first':recent_uses>=2 or batch_uses>=1}


def palette_policies(window,batch=()):
    from .palettes import active
    return {palette:palette_policy(window,batch,palette) for palette in active()}


def brightness_history(recent):
    """Newest four distinct known batches; quiz colours never affect this tie-break."""
    batches=[];seen=set();counts={'light':0,'dark':0}
    for run in recent:
        batch=run.get('batch_id')
        key=('batch',batch) if isinstance(batch,str) and re.fullmatch(r'b-[a-f0-9]{32}',batch) else None
        if key is not None and key in seen:continue
        if key is not None:seen.add(key)
        observations=run.get('panel_theme_observations')
        if isinstance(observations,list) and len(observations)==3:
            values=observations[1:]
        else:values=[run.get('cards',{}).get(k,{}).get('panel_theme','unknown') for k in ('lesson','word')]
        values=[v if v in ('light','dark','mixed','unknown') else 'unknown' for v in values]
        weight=4-len(batches)
        batches.append({'recency':len(batches)+1,'weight':weight,'lesson':values[0],'word':values[1]})
        for value in values:
            if value in counts:counts[value]+=weight
        if len(batches)==4:break
    return {'max_batches':4,'newest_first':True,'batches':batches,'weighted_counts':counts}


def panel_theme(card):
    """Known current high-opacity panel treatment, independently of palette names."""
    from .core import ROOT,read_json
    from .render import luminance
    palettes=read_json(ROOT/'data/design-palettes.json')
    if not isinstance(card,dict) or not isinstance(card.get('palette'),str):return 'unknown'
    palette=palettes.get(card['palette'])
    composition=card.get('composition',{})
    if not palette or not isinstance(composition,dict):return 'unknown'
    blocks=composition.get('blocks',[])
    if not isinstance(blocks,list):return 'unknown'
    panels=[b for b in blocks if isinstance(b,dict) and isinstance(b.get('style'),str) and b['style'] in PANEL_STYLES]
    if not panels:return 'unknown'
    values=set()
    for block in panels:
        opacity=block.get('panel_opacity')
        if (block.get('panel_tone','auto') not in PANEL_TONES or type(opacity) not in (int,float)
                or not valid_panel_opacity(opacity) or opacity<90):
            return 'unknown'  # Missing or older low-opacity surfaces are not guessed.
        text,surface=panel_colours(palette,block.get('panel_tone','auto'),dark=block['style']=='overlay_dark')
        values.add('dark' if luminance(surface)<luminance(text) else 'light')
    return next(iter(values)) if len(values)==1 else 'mixed'


def accepted_choices(placement):
    from .core import ROOT, read_json
    palettes=read_json(ROOT/'data/design-palettes.json')
    choices={}
    for kind in ('quiz','lesson','word'):
        card=placement.get('cards',{}).get(kind,{})
        # Fallbacks must never teach the model what it previously chose.
        if card.get('status') not in ('accepted','adjusted'):continue
        styles=card.get('block_styles',{})
        if (card.get('palette') not in palettes or card.get('design') not in DESIGNS
                or not isinstance(styles,dict) or not styles
                or any(role not in ('body','example','A','B','C','D') or
                       style not in (EXAMPLE_STYLES if role=='example' else BODY_STYLES if role=='body' else ANSWER_STYLES)
                       for role,style in styles.items())):continue
        safe={field:card[field] for field in ('design','block_styles')}
        safe['panel_theme']=panel_theme(card)
        # A preserved ChatGPT layout may now use a fallback palette. Do not
        # attribute that colour choice to the model in its recent-design context.
        if card.get('palette_outcome',{}).get('source')=='chatgpt':safe['palette']=card['palette']
        for field,allowed in (('category_style',CATEGORY_STYLES),('heading_tone',REVIEW_TITLE_TONES),('example_tone',(*REVIEW_PHOTO_TONES,None))):
            if card.get(field) in allowed:safe[field]=card.get(field)
        badges=card.get('answer_badges',{})
        if isinstance(badges,dict) and all(r in ('A','B','C','D') and s in MARKER_STYLES for r,s in badges.items()):
            safe['answer_badges']=badges
        composition=card.get('composition',{})
        fixed_white=(card.get('render_policy',{}).get('version') in (3,4) and
                     (card.get('heading_backing')=='#ffffff' or card.get('heading_tone') in ('ink_light','ink_paper','ink_accent','accent_light')))
        if isinstance(composition,dict) and composition.get('heading_fade') in REVIEW_FADE_STYLES and not fixed_white:
            safe['heading_fade']=composition['heading_fade']
        if isinstance(composition,dict) and composition.get('heading_shade') in (QUIZ_TITLE_SHADE_INTENTS if kind=='quiz' else NONQUIZ_TITLE_SHADE_INTENTS):
            safe['heading_shade']=composition['heading_shade']
        opacity=composition.get('heading_opacity') if isinstance(composition,dict) else None
        if (kind!='quiz' and type(opacity) is int and 0<=opacity<=126
                and composition.get('heading_shade')=='emphasis'
                and composition.get('heading_tone') in ('paper_dark','paper_ink','accent_dark')):
            safe['heading_opacity']=opacity
        blocks=composition.get('blocks',[]) if isinstance(composition,dict) else []
        if isinstance(blocks,list):
            example=next((b for b in blocks if isinstance(b,dict) and b.get('role')=='example'),{})
            if ((card.get('render_policy',{}).get('version') in (4,5,6,7,8,9)
                     and example.get('style')=='italic_photo_fade'
                     and example.get('fade_style') in REVIEW_EXAMPLE_FADE_STYLES)
                    or (card.get('render_policy',{}).get('version') not in (4,5,6,7,8,9)
                        and example.get('fade_style') in REVIEW_FADE_STYLES
                        and not card.get('render_policy',{}).get('example_fade'))):
                safe['example_fade']=example['fade_style']
            if example.get('style')=='italic_photo_fade' and example.get('shade_strength') in EXAMPLE_SHADE_STRENGTHS:
                safe['example_shade_strength']=example['shade_strength']
            if example.get('style')=='italic_photo_fade' and example.get('backing_colour') is not None:
                from .hybrid import valid_example_backing
                if valid_example_backing(example['backing_colour']):safe['example_backing_colour']=example['backing_colour']
            opacities={b['role']:b['panel_opacity'] for b in blocks if isinstance(b,dict)
                       and isinstance(b.get('role'),str) and styles.get(b['role']) in PANEL_STYLES
                       and type(b.get('panel_opacity')) in (int,float) and valid_panel_opacity(b['panel_opacity']) and b['panel_opacity']>=90}
            if opacities and card.get('render_policy',{}).get('version')==7:safe['panel_opacities']=opacities
        choices[kind]=safe
    return choices


def retained_designs(history,limit):
    """Current published rows only; missing snapshot evidence stays unknown."""
    from .core import PROJECT
    from .batches import identity,creation_order,BATCH_ID
    from .frozen_cards import checked_source
    if history.get('project')!=PROJECT or not isinstance(history.get('days'),list):
        raise ValueError('Visual history belongs to another project')
    retained={}
    for row in sorted(history['days'],key=creation_order,reverse=True)[:limit]:
        batch=identity(row);content=row.get('content',{})
        if not isinstance(batch,str) or not BATCH_ID.fullmatch(batch):
            raise ValueError('Invalid retained visual-history identity')
        metrics={};policies={}
        for card in content.get('cards',[]):
            kind=card.get('kind')
            if kind not in ('quiz','lesson','word'):continue
            source=content.get('rendered_sources',{}).get(kind)
            try:checked=checked_source(source,card)
            except (ValueError,TypeError,KeyError):continue
            metrics[kind]=checked['metrics'];policies[kind]=checked['policy']
        retained[batch]={'date':row['date'],'created_at':row.get('created_at'),
                         'metrics':metrics,'policies':policies}
    return retained


def completed_daily_runs(max_daily=15):
    """Preview/verify/running entries never consume the bounded DAILY lookup."""
    page=1;count=0
    while count<max_daily:
        result=json.loads(gh('api',f'repos/{REPO}/actions/workflows/preparation.yml/runs?per_page=100&page={page}'))
        runs=result['workflow_runs']
        for run in runs:
            if run.get('status')!='completed' or run.get('display_title')!='EasyBosnian (daily)':continue
            rid=run.get('id')
            if type(rid) is not int or rid<=0:continue
            count+=1
            yield rid
            if count==max_daily:return
        if len(runs)<100:return
        page+=1


def design_report_files(store,rid):
    """Read only bounded JSON, never artwork, arbitrary paths or model prose."""
    from .run_reports import get_report
    report=get_report(store,rid)
    pattern=r'(?:b-[a-f0-9]{32}|legacy-\d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})/(?:image-placement|platforms)-result\.json'
    if report is not None:
        if report.get('mode')!='daily':return {}
        return {name:body for name,body in report['files'].items()
                if re.fullmatch(pattern,name) and len(body.encode())<=100_000}
    # Legacy private artifacts may still prove a retained rendering. No ZIP
    # member is extracted, and unneeded images/private notes are never read.
    artifacts=json.loads(gh('api',f'repos/{REPO}/actions/runs/{rid}/artifacts'))['artifacts']
    selected=next((a for a in artifacts if a['name']==f'easybosnian-daily-{rid}' and not a['expired']),None)
    if selected is None or selected['size_in_bytes']>20_000_000 or type(selected['id']) is not int or selected['id']<=0:return {}
    body=gh_binary('api',f'repos/{REPO}/actions/artifacts/{selected["id"]}/zip')
    if len(body)>20_000_000:return {}
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        return {m.filename:archive.read(m).decode('utf-8') for m in archive.infolist()
                if re.fullmatch(pattern,m.filename) and m.file_size<=100_000}


def matching_published_design(files,retained):
    """An old/deleted/unpublished design cannot stand in for the current one."""
    from .batches import BATCH_ID
    names=[name for name in files if name.endswith('/image-placement-result.json')]
    if len(names)!=1:return None
    name=names[0];prefix=name.rsplit('/',1)[0]
    placement=json.loads(files[name]);batch=placement.get('batch_id')
    if isinstance(batch,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',batch):batch='legacy-'+batch
    if not isinstance(batch,str) or not BATCH_ID.fullmatch(batch) or batch not in retained:return None
    current=retained[batch]
    if placement.get('batch')!=current['date'] or set(current['metrics'])!={'quiz','lesson','word'}:return None
    outcome_name=prefix+'/platforms-result.json'
    if outcome_name not in files:return None
    outcome=json.loads(files[outcome_name]);outcome_batch=outcome.get('batch_id')
    if isinstance(outcome_batch,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',outcome_batch):outcome_batch='legacy-'+outcome_batch
    if (outcome_batch!=batch or outcome.get('batch')!=current['date'] or outcome.get('history_saved') is not True
            or not any(outcome.get('platforms',{}).get(platform,{}).get('published') is True
                       for platform in ('instagram','facebook','tiktok'))):return None
    for kind,metrics in current['metrics'].items():
        card=placement.get('cards',{}).get(kind,{})
        if (card.get('palette')!=metrics['palette'] or card.get('composition')!=metrics['composition']
                or card.get('render_policy')!=current['policies'][kind]):return None
    return batch,placement


def recent_choices(limit=5):
    """Retained published batches; reports only enrich verified current choices."""
    recent=[]
    try:
        from .store import Store
        store=Store();retained=retained_designs(store.history(),limit)
        # Current snapshot metadata establishes APPLIED colours, not who chose
        # them. Never invent model provenance from equal IDs or a similar look.
        for batch,row in retained.items():
            metrics=row['metrics']
            recent.append({'run_id':None,'batch_id':batch,'created_at':row['created_at'],'cards':{},
                'palette_observations':[metrics[k]['palette'] for k in ('quiz','lesson','word') if k in metrics],
                'panel_theme_observations':[panel_theme(metrics.get(k,{})) for k in ('quiz','lesson','word')]})
        pending={batch for batch,row in retained.items() if len(row['metrics'])==3}
        if pending:
            for rid in completed_daily_runs():
                match=matching_published_design(design_report_files(store,rid),retained)
                if match is None:continue
                batch,placement=match
                if batch not in pending:continue
                item=next(item for item in recent if item['batch_id']==batch)
                item.update(run_id=rid,cards=accepted_choices(placement));pending.remove(batch)
                if not pending:break
        return recent,'available'
    except Exception:
        # A failed read never triggers another request or admits unverified
        # reports. Already checked retained observations remain usable.
        print('::warning::Recent design context unavailable; current photo review continues')
        return recent,'unavailable'
