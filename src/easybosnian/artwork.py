"""Render the runner-staged reviewed candidate once, sharing cards across publishers."""
from .batches import output_key
import io
import os
import uuid
import shutil
from PIL import Image
from .core import ROOT, read_json, write_json
from .http import SafeError, request
from .providers import provider
from .hybrid import default_plan, render_hybrid
from .visual_policy import panel_opacities, apply_policy, policy_metadata
from .visual_diagnostics import (rejection_diagnostic, rendering_outcome, rendering_provenance,
    select_palette, safe_palette_outcome, PALETTE_RENDER_FAILURES, REVIEW_FAILURES, choice_record)
from .store import wait_for_image


def render_input(package):
    # Ephemeral artwork-cache provenance, not immutable history or publication state.
    return {'rendering_version':44, **{key:package.get(key) for key in ('batch_id','date','design_palette','background_source','background_sources','rendered_sources')},
            'cards':[{key:value for key,value in card.items() if key!='design_template'} for card in package['cards']]}


def artwork(store, package, expose=False, review_images=False, require_prepared=False, reused_backgrounds=None, frozen_cards=None, design_attempt_limit=3):
    date=package['date']; output=ROOT/'build'/output_key(package); output.mkdir(parents=True,exist_ok=True)
    assets={}; stage='FLUX generation'
    generation_counts={};generation_diagnostics={}
    frozen_cards=frozen_cards or {}
    if frozen_cards and (not review_images or not set(frozen_cards)<=set(('quiz','lesson','word'))):
        raise ValueError('Exact card reuse requires private reviewed artwork preparation')
    if package.get('batch_id'):store.use_content(package)
    artwork_id='r-'+uuid.uuid4().hex
    try:
        if review_images and (expose or require_prepared):
            raise ValueError('Visual artwork preparation must remain private')
        if review_images:
            # Saved preview rows may carry snapshots of the earlier rendering.
            # Only explicitly frozen cards can keep those exact-byte references.
            retained_sources={k:v for k,v in package.get('rendered_sources',{}).items() if k in frozen_cards}
            if retained_sources:package['rendered_sources']=retained_sources
            else:package.pop('rendered_sources',None)
        manifest = output/'prepared-artwork.secret'
        if require_prepared:
            stage='Pillow rendering'
            saved=read_json(manifest)
            if saved['input']!=render_input(package) or saved['run_url']!=os.getenv('GITHUB_RUN_URL'):
                raise ValueError('Prepared artwork belongs to a different input/run; refusing stale cards')
            if set(saved['metrics'])!={'quiz','lesson','word'} or any(
                    not (output/f'{kind}-{suffix}.jpg').is_file()
                    for kind in saved['metrics'] for suffix in ('background','card')):
                raise ValueError('Prepared artwork is incomplete; no generation or publication retry')
            from .frozen_cards import digest
            for kind,source in package.get('rendered_sources',{}).items():
                for suffix in ('card','story'):
                    if digest((output/f'{kind}-{suffix}.jpg').read_bytes())!=source[suffix+'_sha256']:
                        raise ValueError('Prepared finished-card bytes changed before publication')
        candidates={}
        opacity_choices=panel_opacities(package['cards']) if review_images else {}
        if not require_prepared:
            if reused_backgrounds is not None:
                from .photo_reuse import valid_source
                if (not review_images or not reused_backgrounds or not set(reused_backgrounds)<={'quiz','lesson','word'}
                        or any(not valid_source(package.get('background_sources',{}).get(k,package.get('background_source')))
                               for k in reused_backgrounds)):
                    raise ValueError('Photo reuse requires the selected trusted photos and a fresh private review')
            if reused_backgrounds is None or set(reused_backgrounds)!={'quiz','lesson','word'}:
                retained={k:package.get('background_sources',{}).get(k,package.get('background_source'))
                          for k in (reused_backgrounds or {})}
                package['background_source']={'batch_id':package.get('batch_id') or 'legacy-'+date,'artwork_id':artwork_id if package.get('batch_id') else None}
                if retained:package['background_sources']=retained
                else:package.pop('background_sources',None)
        def photo_bytes(card):
            if reused_backgrounds is not None and card['kind'] in reused_backgrounds:return reused_backgrounds[card['kind']].read_bytes()
            if review_images:
                from .photo_generation import generate_photo, rewrite_rejected_scene
                def send():
                    nonlocal stage
                    stage='FLUX generation'
                    current_id=artwork_id if generation_counts[card['kind']]==1 else 'r-'+uuid.uuid4().hex
                    if current_id!=artwork_id:
                        package.setdefault('background_sources',{})[card['kind']]={
                            'batch_id':package.get('batch_id') or 'legacy-'+date,
                            'artwork_id':current_id if package.get('batch_id') else None}
                    return provider().generate(card['background_prompt'],date,card['kind'],**({'batch_id':package['batch_id'],
                        'reviewed_content':package,'artwork_id':current_id} if package.get('batch_id') else {}))
                def rewrite_scene(card):
                    nonlocal stage
                    stage='photo scene revision'
                    return rewrite_rejected_scene(card)
                return generate_photo(card,send,generation_counts,generation_diagnostics,rewrite=rewrite_scene)
            return provider().generate(card['background_prompt'],date,card['kind'],**({'batch_id':package['batch_id'],'reviewed_content':package,'artwork_id':artwork_id} if package.get('batch_id') else {}))
        if review_images:
            from .visual_placement import composition_sheet, review_compositions
            for card in package['cards']:
                kind=card['kind']; background=output/f'{kind}-background.jpg'
                if kind not in frozen_cards:(output/f'{kind}-story.jpg').unlink(missing_ok=True)
                stage='FLUX generation'
                Image.open(io.BytesIO(photo_bytes(card))).convert('RGB').save(background,'JPEG',quality=95)
            # Inspect unstyled actual photographs before any overlay is composed.
            from .photo_quality import quality_gate, inspect_photos
            photo_paths={c['kind']:output/f"{c['kind']}-background.jpg" for c in package['cards'] if c['kind'] not in frozen_cards}
            sources={k:[package.get('background_sources',{}).get(k,package.get('background_source'))] for k in photo_paths}
            def regenerate(card,path):
                nonlocal stage
                from .photo_generation import LIMIT
                if generation_counts.get(card['kind'],0)>=LIMIT:return False
                stage='FLUX generation'
                try:raw=photo_bytes(card)
                except SafeError as error:
                    if (error.stage=='FLUX generation' and error.reason=='ai_content_rejected'
                            and generation_counts.get(card['kind'],0)>=LIMIT):return False
                    raise
                Image.open(io.BytesIO(raw)).convert('RGB').save(path,'JPEG',quality=95)
                source=package.get('background_sources',{}).get(card['kind'],package.get('background_source'))
                sources[card['kind']].append(source)
            stage='photo quality inspection'
            def inspect(package,photos):
                nonlocal stage
                stage='photo quality inspection'
                return inspect_photos(package,photos)
            quality=quality_gate(package,photo_paths,regenerate,pinned=tuple(reused_backgrounds or ()),inspect=inspect) if photo_paths else {}
            for kind,verdict in quality.items():
                if kind in generation_diagnostics:verdict['generation_attempts']=generation_diagnostics[kind]
                source=sources[kind][verdict['selected_attempt']-1]
                if source is not None:
                    if source!=package.get('background_source'):package.setdefault('background_sources',{})[kind]=source
                    elif kind in package.get('background_sources',{}):
                        del package['background_sources'][kind]
                        if not package['background_sources']:package.pop('background_sources')
                if verdict['status']!='accepted':
                    print(f"::warning::{kind} photo retained with a flagged quality defect after {len(verdict['attempts'])} inspection(s): {verdict['reason']}")
            write_json(output/'photo-quality-result.json',{'batch':date,'batch_id':package.get('batch_id'),'cards':quality})
            stage='Pillow rendering'
            for card in package['cards']:
                kind=card['kind'];background=output/f'{kind}-background.jpg'
                if kind in frozen_cards:continue
                baseline=output/f'{kind}-hybrid-reference.jpg'
                metrics=render_hybrid(card,package['design_palette'],background,baseline)
                sheet=output/f'{kind}-placement-sheet.jpg'
                composition_sheet(background,sheet)
                with Image.open(background) as original:photo_size=list(original.size)
                candidates[kind]={'baseline':baseline,'metrics':metrics,'sheet':sheet,'photo_size':photo_size,
                                  'assigned_panel_opacity':opacity_choices[kind]}
            from .visual_history import recent_choices
            recent,recent_status=recent_choices()
            proposal,status=review_compositions(package,candidates,recent)
            decisions={}
        for card in package['cards']:
            kind=card['kind']; background=output/f'{kind}-background.jpg'
            path=output/f'{kind}-card.jpg'
            if require_prepared:
                if not path.is_file() or not background.is_file():
                    raise ValueError('Prepared artwork is incomplete; no generation or publication retry')
                metrics=saved['metrics'][kind]
            elif review_images:
                if kind in frozen_cards:
                    entry=frozen_cards[kind];source=entry['source']
                    shutil.copyfile(entry['card'],path)
                    story_path=output/f'{kind}-story.jpg';shutil.copyfile(entry['story'],story_path)
                    metrics=source['metrics']
                    decisions[kind]=choice_record(metrics,'reused',source['policy'],
                        {'source':'reused','reason':'Exact saved card palette retained by user request'},status)
                    body=path.read_bytes();stage='storage';store.put_file(output_key(package),path.name,body)
                    assets[kind]={'path':path,'story_path':story_path,'background_path':background,
                                  'alt_text':card['alt_text'],'metrics':metrics}
                    continue
                plan=proposal['cards'][kind]
                if status=='reviewed':
                    palette,palette_outcome=select_palette(plan,package['design_palette'])
                    recorded=proposal.get('palette_decisions',{}).get(kind)
                    if recorded is not None and palette_outcome['source']=='chatgpt':
                        palette_outcome=safe_palette_outcome(recorded)
                else:
                    palette=package['design_palette']
                    palette_outcome={'source':'fallback','reason':'Review unavailable; using preparation palette'}
                model_accepted=status=='reviewed' and plan['confidence']=='high'
                plan=dict(plan,palette=palette) if model_accepted else default_plan(card)
                stage='Pillow rendering'
                from .design_repair import render_design
                def draw(candidate):
                    return render_hybrid(card,palette,background,path,apply_policy(candidate,panel_opacity=opacity_choices[kind]))
                def repair(feedback):
                    nonlocal stage
                    stage='visual design repair'
                    result,review_status=review_compositions(package,{kind:candidates[kind]},recent,feedback={kind:feedback})
                    stage='Pillow rendering'
                    return result['cards'][kind],review_status
                palette_rejection=None
                try:
                    metrics,detail=render_design(card,plan,background,draw,model_accepted=model_accepted,
                                                repair=repair,attempt_limit=design_attempt_limit,
                                                invalid_elements=proposal.get('card_invalid_elements',{}).get(kind,()))
                except ValueError as error:
                    if str(error) not in PALETTE_RENDER_FAILURES or palette_outcome['source']!='chatgpt' or palette==package['design_palette']:
                        raise
                    plan=getattr(error,'plan',plan)
                    prior_attempts=getattr(error,'attempts',None)
                    palette_rejection=rejection_diagnostic(error,plan)
                    palette=package['design_palette'];plan=dict(plan,palette=palette)
                    palette_outcome={'source':'fallback','reason':'ChatGPT palette fails photographic contrast'}
                    # Local palette-only validation, never a service or publish retry.
                    try:
                        metrics,detail=render_design(card,plan,background,draw,model_accepted=model_accepted,attempt_limit=1)
                    except ValueError as fallback_error:
                        if str(fallback_error) not in PALETTE_RENDER_FAILURES:raise
                        metrics=draw(default_plan(card))
                        detail={'status':'rejected; safe hybrid fallback','rejection':rejection_diagnostic(fallback_error,plan)}
                    if prior_attempts:detail['design_attempts']=prior_attempts
                if detail.get('rejection'):
                    write_json(output/f'{kind}-rejection-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                               'card':kind,**detail['rejection']})
                if palette_rejection:
                    write_json(output/f'{kind}-palette-rejection-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                               'card':kind,**palette_rejection})
                decisions[kind]=choice_record(metrics,detail.pop('status'),
                    policy_metadata(metrics['composition'],panel_opacity=opacity_choices[kind]),palette_outcome,status,**detail,
                    **({'photo_quality':quality[kind]} if kind in quality else {}),
                    **({'palette_rejection':palette_rejection} if palette_rejection else {}))
                failure=proposal.get('card_failures',{}).get(kind,proposal.get('failure_reason'))
                if failure in REVIEW_FAILURES:decisions[kind]['review_failure']=failure
                decisions[kind]['outcome']=rendering_outcome(decisions[kind],status)
                decisions[kind]['provenance']=rendering_provenance(decisions[kind],status)
            else:
                stage='FLUX generation'
                Image.open(io.BytesIO(photo_bytes(card))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                metrics=render_hybrid(card,package['design_palette'],background,path)
            body=path.read_bytes()
            stage='storage'
            if not require_prepared: store.put_file(output_key(package),path.name,body)
            item={'path':path,'background_path':background,'alt_text':card['alt_text'],'metrics':metrics}
            if expose:
                item['url']=store.expose(output_key(package),path.name,body)
                wait_for_image(item['url'],body,fetch=request)
            assets[kind]=item
            if (output/f'{kind}-story.jpg').is_file():item['story_path']=output/f'{kind}-story.jpg'
            if review_images and package.get('batch_id') and os.getenv('MODE')=='daily':
                from .stories import story_image
                from .frozen_cards import snapshot
                from .core import ROOT as catalogue_root
                story_path=output/f'{kind}-story.jpg'
                story_image(path,story_path,read_json(catalogue_root/'data/design-palettes.json')[metrics['palette']],background,card,
                            category_style=metrics['category_style'])
                item['story_path']=story_path
                package.setdefault('rendered_sources',{})[kind]=snapshot(store,package,card,item,decisions[kind]['render_policy'])
        if review_images:
            write_json(output/'image-placement-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                        'status':status,'recent_design_context':recent_status,'recent_design_runs':len(recent),'cards':decisions})
            write_json(manifest,{'input':render_input(package),'run_url':os.getenv('GITHUB_RUN_URL'),
                               'metrics':{kind:item['metrics'] for kind,item in assets.items()}})
            manifest.chmod(0o600)
        return assets
    except Exception as error:
        raise SafeError(str(error),getattr(error,'stage',None) or stage,
                        getattr(error,'http_status',None),reason=getattr(error,'reason',None),
                        provider_code=getattr(error,'provider_code',None),
                        provider_http_status=getattr(error,'provider_http_status',None)) from None
