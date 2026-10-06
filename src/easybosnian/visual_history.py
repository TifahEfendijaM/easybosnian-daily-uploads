"""Read recent accepted choices from private run artifacts, without visual references."""
import io
import json
import re
import zipfile

from .core import REPO, gh, gh_binary
from .designs import DESIGNS, BODY_STYLES, ANSWER_STYLES, EXAMPLE_STYLES, CATEGORY_STYLES, MARKER_STYLES, PHOTO_TONES


def accepted_choices(placement):
    from .core import ROOT, read_json
    palettes=read_json(ROOT/'data/design-palettes.json')
    choices={}
    for kind in ('quiz','lesson','word'):
        card=placement.get('cards',{}).get(kind,{})
        # Fallbacks must never teach the model what it previously chose.
        if card.get('status')!='accepted':continue
        styles=card.get('block_styles',{})
        if (card.get('palette') not in palettes or card.get('design') not in DESIGNS
                or not isinstance(styles,dict) or not styles
                or any(role not in ('body','example','A','B','C','D') or
                       style not in (EXAMPLE_STYLES if role=='example' else BODY_STYLES if role=='body' else ANSWER_STYLES)
                       for role,style in styles.items())):continue
        safe={field:card[field] for field in ('design','block_styles')}
        # A preserved ChatGPT layout may now use a fallback palette. Do not
        # attribute that colour choice to the model in its recent-design context.
        if card.get('palette_outcome',{}).get('source')!='fallback':safe['palette']=card['palette']
        for field,allowed in (('category_style',CATEGORY_STYLES),('heading_tone',PHOTO_TONES),('example_tone',(*PHOTO_TONES,None))):
            if card.get(field) in allowed:safe[field]=card.get(field)
        badges=card.get('answer_badges',{})
        if isinstance(badges,dict) and all(r in ('A','B','C','D') and s in MARKER_STYLES for r,s in badges.items()):
            safe['answer_badges']=badges
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
            artifacts=json.loads(gh('api',f'repos/{REPO}/actions/runs/{rid}/artifacts'))['artifacts']
            selected=next((a for a in artifacts if a['name']==f'easybosnian-daily-{rid}' and not a['expired']),None)
            if selected is None:continue
            # Bound both archive size and the one metadata member; never extract files.
            if selected['size_in_bytes']>20_000_000 or type(selected['id']) is not int or selected['id']<=0:continue
            body=gh_binary('api',f'repos/{REPO}/actions/artifacts/{selected["id"]}/zip')
            if len(body)>20_000_000:continue
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                members=[m for m in archive.infolist() if re.fullmatch(r'(?:b-[a-f0-9]{32}|\d{4}-\d{2}-\d{2})/image-placement-result.json',m.filename) and m.file_size<=100_000]
                if len(members)!=1:continue
                choices=accepted_choices(json.loads(archive.read(members[0])))
            if choices:recent.append({'run_id':rid,'created_at':run['createdAt'],'cards':choices})
            if len(recent)==limit:break
        return recent,'available'
    except Exception:
        # Missing history never invalidates a fresh photographic review or triggers a retry.
        print('::warning::Recent design context unavailable; current photo review continues')
        return recent,'unavailable'
