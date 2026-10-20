"""Run-scoped original photographs; no inference, cleanup or history writes."""
import base64
import io
import os
import re
from PIL import Image

from .batches import BATCH_ID
from .core import ROOT, PROJECT, read_json, write_json
from .http import SafeError

KINDS=('quiz','lesson','word')


def valid_source(source):
    return (isinstance(source,dict) and set(source)=={'batch_id','artwork_id'}
            and isinstance(source['batch_id'],str) and BATCH_ID.fullmatch(source['batch_id'])
            and (source['artwork_id'] is None or isinstance(source['artwork_id'],str)
                 and re.fullmatch(r'r-[a-f0-9]{32}',source['artwork_id'])))


def prepare_photos(store,previous,source_batch_id,batch_id,date,kinds=KINDS):
    """Fetch selected originals before research/deletion; never infer replacements."""
    if not previous or not BATCH_ID.fullmatch(source_batch_id or '') or not BATCH_ID.fullmatch(batch_id):
        raise ValueError('Reusing photographs requires a complete selected saved batch')
    if not kinds or len(set(kinds))!=len(kinds) or not set(kinds)<=set(KINDS):
        raise ValueError('Invalid retained photograph roles')
    paths={};originals={};sources={}
    for card in previous['cards']:
        kind=card['kind']
        if kind not in KINDS:raise ValueError('Invalid saved photograph role')
        if kind not in kinds:continue
        try:result=store.call('GET',f'/v1/backgrounds/batches/{source_batch_id}/{kind}')
        except SafeError:
            raise ValueError('Saved original photos are unavailable, expired or ambiguous; choose same_words for new photos. No FLUX request or cleanup was sent.') from None
        candidate=result.get('source')
        expected=previous.get('background_sources',{}).get(kind,previous.get('background_source'))
        if (not valid_source(candidate) or result.get('prompt')!=card['background_prompt']
                or expected is not None and expected!=candidate):
            raise ValueError('Saved photograph does not match its reviewed source')
        sources[kind]=candidate
        raw=base64.b64decode(result['image'],validate=True)
        if len(raw)>10_000_000:raise ValueError('Saved photograph exceeds the safe size')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG') or max(image.size)>4096 or min(image.size)<512:
                raise ValueError('Saved original photograph has an unsupported format or size')
            image.verify()
        path=ROOT/'build/reused-backgrounds'/f'{kind}-photo.jpg'
        path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600);os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as output:output.write(raw)
        paths[kind]=path;originals[kind]=raw
    if set(paths)!=set(kinds):raise ValueError('Selected saved originals are incomplete')
    first=next(iter(sources.values()));source=first if all(v==first for v in sources.values()) else None
    return {'source':source,'sources':sources,'paths':paths,'originals':originals,
            'source_batch_id':source_batch_id,'batch_id':batch_id,'date':date}


def seal_photos(prepared,metadata=False):
    # The research child saw these photos but may not alter them. Compare exact
    # bytes held by the trusted parent, then create its private handoff afterward.
    kinds=tuple(prepared['sources'])
    if any(prepared['paths'][k].read_bytes()!=prepared['originals'][k] for k in kinds):
        raise ValueError('Research changed a saved original photograph; refusing reuse')
    manifest={key:prepared[key] for key in ('source','source_batch_id','batch_id','date')}
    manifest['sources']=prepared['sources']
    manifest.update(project=PROJECT,run_url=os.getenv('GITHUB_RUN_URL'))
    path=ROOT/'build/reused-backgrounds.secret';write_json(path,manifest);path.chmod(0o600)
    uniform=set(kinds)==set(KINDS) and prepared['source'] is not None
    if metadata:
        return ({'background_source':dict(prepared['source'])} if uniform else
                {'background_sources':dict(prepared['sources'])})
    if not uniform:raise ValueError('Per-card photograph reuse requires explicit source metadata')
    return dict(prepared['source'])


def loaded_photos(package):
    manifest=read_json(ROOT/'build/reused-backgrounds.secret')
    if (manifest.get('project')!=PROJECT or manifest.get('run_url')!=os.getenv('GITHUB_RUN_URL')
            or manifest.get('batch_id')!=package.get('batch_id') or manifest.get('date')!=package['date']):
        raise ValueError('Reused photographs belong to a different batch, source or workflow run')
    sources=manifest.get('sources',{k:manifest.get('source') for k in KINDS})
    if (not isinstance(sources,dict) or not sources or not set(sources)<=set(KINDS)
            or any(not valid_source(source) or source!=package.get('background_sources',{}).get(kind,package.get('background_source'))
                   for kind,source in sources.items())):
        raise ValueError('Reused photographs belong to a different batch, source or workflow run')
    paths={kind:ROOT/'build/reused-backgrounds'/f'{kind}-photo.jpg' for kind in sources}
    if not all(path.is_file() for path in paths.values()):raise ValueError('Saved original photos are incomplete; no generation fallback')
    return paths
