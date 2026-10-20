"""Render the runner-staged reviewed candidate once, sharing cards across publishers."""
from .batches import output_key
import io
import os
import uuid
from PIL import Image
from .core import ROOT, read_json, write_json
from .http import SafeError, request
from .providers import provider
from .hybrid import default_plan, render_hybrid
from .visual_diagnostics import (rejection_diagnostic, rendering_outcome, rendering_provenance,
    select_palette, safe_palette_outcome, PALETTE_RENDER_FAILURES, REVIEW_FAILURES)
from .store import wait_for_image


def render_input(package):
    # Ephemeral artwork-cache provenance, not immutable history or publication state.
    return {'rendering_version':26, **{key:package.get(key) for key in ('batch_id','date','design_palette','background_source','background_sources')},
            'cards':[{key:value for key,value in card.items() if key!='design_template'} for card in package['cards']]}


def artwork(store, package, expose=False, review_images=False, require_prepared=False, reused_backgrounds=None):
    date=package['date']; output=ROOT/'build'/output_key(package); output.mkdir(parents=True,exist_ok=True)
    assets={}; stage='FLUX generation'
    if package.get('batch_id'):store.use_content(package)
    artwork_id='r-'+uuid.uuid4().hex
    try:
        if review_images and (expose or require_prepared):
            raise ValueError('Visual artwork preparation must remain private')
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
        candidates={}
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
            return provider().generate(card['background_prompt'],date,card['kind'],**({'batch_id':package['batch_id'],'reviewed_content':package,'artwork_id':artwork_id} if package.get('batch_id') else {}))
        if review_images:
            from .visual_placement import composition_sheet, review_compositions
            for card in package['cards']:
                kind=card['kind']; background=output/f'{kind}-background.jpg'
                stage='FLUX generation'
                Image.open(io.BytesIO(photo_bytes(card))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                baseline=output/f'{kind}-hybrid-reference.jpg'
                metrics=render_hybrid(card,package['design_palette'],background,baseline)
                sheet=output/f'{kind}-placement-sheet.jpg'
                # The model sees only real photos/crops; baseline remains a private measured fallback.
                composition_sheet(background,sheet)
                with Image.open(background) as original:photo_size=list(original.size)
                candidates[kind]={'baseline':baseline,'metrics':metrics,'sheet':sheet,'photo_size':photo_size}
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
                rejection=None;palette_rejection=None;layout_adjustment=None
                stage='Pillow rendering'
                def draw_plan(selected_plan):
                    from .visual_adjustment import single_line_example_plan
                    wider=single_line_example_plan(card,selected_plan,background) if model_accepted else None
                    if wider is not None:
                        try:return render_hybrid(card,palette,background,path,wider)
                        except ValueError:pass  # Keep valid wrapping if the wider line is unreadable.
                    return render_hybrid(card,palette,background,path,selected_plan)
                def render_selected(selected_plan):
                    nonlocal palette,palette_outcome,palette_rejection
                    try:
                        return draw_plan(selected_plan)
                    except ValueError as error:
                        if (str(error) not in PALETTE_RENDER_FAILURES or
                                palette_outcome['source']!='chatgpt'):
                            raise
                        # A bounded local colour fallback, never another model,
                        # generation, storage or publication request. Preserve
                        # every layout field and revalidate against real pixels.
                        palette_rejection=rejection_diagnostic(error,selected_plan)
                        write_json(output/f'{kind}-palette-rejection-result.json',
                                   {'batch':date,'batch_id':package.get('batch_id'),'card':kind,**palette_rejection})
                        print(f"::warning::{kind} palette rejected: {palette_rejection['reason']}; validating unchanged layout with preparation palette")
                        palette_outcome={'source':'fallback','reason':'ChatGPT palette fails photographic contrast'}
                        if palette==package['design_palette']:raise
                        palette=package['design_palette']
                        selected_plan['palette']=palette
                        return draw_plan(selected_plan)
                try:
                    metrics=render_selected(plan)
                    decision_status='accepted' if model_accepted else 'default'
                except ValueError as error:
                    # Bad cosmetic geometry/contrast cannot trigger a second model
                    # call, generation, or publication. The premeasured reference is safe.
                    rejection=rejection_diagnostic(error,plan)
                    write_json(output/f'{kind}-rejection-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                               'card':kind,**rejection})
                    from .visual_adjustment import nearest_valid_plan
                    adjusted=nearest_valid_plan(card,plan,background) if model_accepted else None
                    if adjusted is not None:
                        try:
                            metrics=render_selected(adjusted[0])
                            layout_adjustment=adjusted[1];decision_status='adjusted'
                            print(f'::notice::{kind} approved design retained with measured placement adjustments')
                        except ValueError as adjusted_error:
                            rejection=rejection_diagnostic(adjusted_error,adjusted[0])
                            metrics=render_selected(default_plan(card))
                            decision_status='rejected; safe hybrid fallback'
                    else:
                        # Unsupported/unreadable/impossible proposals still need
                        # a safe exact-copy fallback, preserving the resolved palette.
                        metrics=render_selected(default_plan(card))
                        decision_status='rejected; safe hybrid fallback'
                    if layout_adjustment is None:
                        print(f"::warning::{kind} composition rejected: {rejection['reason']}; using measured fallback without retry")
                if model_accepted and decision_status in ('accepted','adjusted'):
                    from .visual_adjustment import applied_adjustment
                    layout_adjustment=applied_adjustment(plan,metrics['composition'])
                    if layout_adjustment is not None:decision_status='adjusted'
                decisions[kind]={'position':metrics['panel_position'],'status':decision_status,
                                 'palette':metrics['palette'],'design':metrics['design'],'category_style':metrics['category_style'],
                                 'heading_tone':metrics['heading_tone'],'example_tone':metrics['example_tone'],
                                 'block_styles':metrics['block_styles'],'answer_badges':metrics['answer_badges'],
                                 'block_typography':metrics['block_typography'],'composition':metrics.get('composition'),
                                 'palette_outcome':palette_outcome,
                                 **({'layout_adjustment':layout_adjustment} if layout_adjustment is not None else {}),
                                 **({'rejection':rejection} if rejection is not None else {}),
                                 **({'palette_rejection':palette_rejection} if palette_rejection is not None else {})}
                if proposal.get('failure_reason') in REVIEW_FAILURES:
                    decisions[kind]['review_failure']=proposal['failure_reason']
                card_failure=proposal.get('card_failures',{}).get(kind)
                if card_failure in REVIEW_FAILURES:
                    decisions[kind]['review_failure']=card_failure
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
