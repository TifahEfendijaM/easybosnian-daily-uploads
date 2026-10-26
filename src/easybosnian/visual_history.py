"""Read recent accepted choices from protected reports/legacy artifacts; no visual references."""
import io
import json
import os
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
    from .core import ROOT,read_json
    return {palette:palette_policy(window,batch,palette) for palette in read_json(ROOT/'data/design-palettes.json')}


def panel_theme(card):
    """Known opaque panel treatment, independently of a palette's label/name."""
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
        if block.get('panel_tone','auto') not in PANEL_TONES or block.get('panel_opacity')!=100:
            return 'unknown'  # Missing/translucent historical surfaces are not guessed.
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
            if ((card.get('render_policy',{}).get('version') in (4,5,6,7)
                     and example.get('style')=='italic_photo_fade'
                     and example.get('fade_style') in REVIEW_EXAMPLE_FADE_STYLES)
                    or (card.get('render_policy',{}).get('version') not in (4,5,6,7)
                        and example.get('fade_style') in REVIEW_FADE_STYLES
                        and not card.get('render_policy',{}).get('example_fade'))):
                safe['example_fade']=example['fade_style']
            if example.get('style')=='italic_photo_fade' and example.get('shade_strength') in EXAMPLE_SHADE_STRENGTHS:
                safe['example_shade_strength']=example['shade_strength']
            opacities={b['role']:b['panel_opacity'] for b in blocks if isinstance(b,dict)
                       and isinstance(b.get('role'),str) and styles.get(b['role']) in PANEL_STYLES
                       and valid_panel_opacity(b.get('panel_opacity'),legacy=False)}
            if opacities and ('render_policy' not in card or card['render_policy'].get('version')==7):safe['panel_opacities']=opacities
        choices[kind]=safe
    return choices


def recent_choices(limit=5):
    """Bounded read of this workflow only; no pictures, source copy, keys or model prose."""
    recent=[]
    try:
        runs=json.loads(gh('run','list','--repo',REPO,'--workflow','preparation.yml','--limit','15',
                           '--json','databaseId,status,displayTitle,createdAt'))
        for run in runs:
            if run['status']!='completed' or run['displayTitle']!='EasyBosnian (daily)':continue
            rid=run['databaseId']
            if type(rid) is not int or rid<=0:continue
            placement=None
            if os.getenv('EASYBOSNIAN_WORKER_URL') and os.getenv('EASYBOSNIAN_ADMIN_TOKEN'):
                from .run_reports import get_report
                from .store import Store
                report=get_report(Store(),rid)
                if report:
                    members=[body for name,body in report['files'].items()
                             if re.fullmatch(r'(?:b-[a-f0-9]{32}|\d{4}-\d{2}-\d{2})/image-placement-result.json',name)
                             and len(body.encode())<=100_000]
                    if len(members)==1:placement=json.loads(members[0])
            if placement is None:
                # Read legacy artifacts only when this run predates private KV reports.
                artifacts=json.loads(gh('api',f'repos/{REPO}/actions/runs/{rid}/artifacts'))['artifacts']
                selected=next((a for a in artifacts if a['name']==f'easybosnian-daily-{rid}' and not a['expired']),None)
                if selected is None:continue
                if selected['size_in_bytes']>20_000_000 or type(selected['id']) is not int or selected['id']<=0:continue
                body=gh_binary('api',f'repos/{REPO}/actions/artifacts/{selected["id"]}/zip')
                if len(body)>20_000_000:continue
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    members=[m for m in archive.infolist() if re.fullmatch(r'(?:b-[a-f0-9]{32}|\d{4}-\d{2}-\d{2})/image-placement-result.json',m.filename) and m.file_size<=100_000]
                    if len(members)!=1:continue
                    placement=json.loads(archive.read(members[0]))
            choices=accepted_choices(placement)
            from .core import ROOT,read_json
            catalogue=read_json(ROOT/'data/design-palettes.json')
            observations=[placement.get('cards',{}).get(k,{}).get('palette') for k in ('quiz','lesson','word')]
            observations=[v for v in observations if isinstance(v,str) and v in catalogue]
            if choices or observations:
                recent.append({'run_id':rid,'created_at':run['createdAt'],'cards':choices,'palette_observations':observations,
                               'panel_theme_observations':[panel_theme(placement.get('cards',{}).get(k,{})) for k in ('quiz','lesson','word')]})
            if len(recent)==limit:break
        return recent,'available'
    except Exception:
        # Missing history never invalidates a fresh photographic review or triggers a retry.
        print('::warning::Recent design context unavailable; current photo review continues')
        return recent,'unavailable'
