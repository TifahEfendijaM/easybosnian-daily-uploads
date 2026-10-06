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
from .visual_diagnostics import approved_proposal, rejection_diagnostic
from .store import wait_for_image


def render_input(package):
    # Ephemeral artwork-cache provenance, not immutable history or publication state.
    return {'rendering_version':12, **{key:package.get(key) for key in ('batch_id','date','design_palette')},
            'cards':[{key:value for key,value in card.items() if key!='design_template'} for card in package['cards']]}


def artwork(store, package, expose=False, review_images=False, require_prepared=False):
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
        if review_images:
            from .visual_placement import composition_sheet, review_compositions
            for card in package['cards']:
                kind=card['kind']; background=output/f'{kind}-background.jpg'
                stage='FLUX generation'
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id'],'reviewed_content':package,'artwork_id':artwork_id} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                baseline=output/f'{kind}-hybrid-reference.jpg'
                metrics=render_hybrid(card,package['design_palette'],background,baseline)
                sheet=output/f'{kind}-placement-sheet.jpg'
                # The model sees only real photos/crops; baseline remains a private measured fallback.
                composition_sheet(background,sheet)
                with Image.open(background) as original:photo_size=list(original.size)
                candidates[kind]={'baseline':baseline,'metrics':metrics,'sheet':sheet,'photo_size':photo_size}
            proposal,status=review_compositions(package,candidates)
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
                palette=plan.get('palette',package['design_palette'])
                if plan['confidence']!='high':plan=default_plan(card)
                rejection=None
                stage='Pillow rendering'
                try:
                    metrics=render_hybrid(card,palette,background,path,plan)
                    decision_status='accepted' if plan['confidence']=='high' else 'default'
                except ValueError as error:
                    # Bad cosmetic geometry/contrast cannot trigger a second model
                    # call, generation, or publication. The premeasured reference is safe.
                    rejection=rejection_diagnostic(error,plan)
                    write_json(output/f'{kind}-rejection-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                               'card':kind,**rejection})
                    print(f"::warning::{kind} composition rejected: {rejection['reason']}; using measured fallback without retry")
                    # A geometry rejection should not undo a valid photo-reviewed palette.
                    # Invalid colour contracts/contrast retain the preparation-palette fallback.
                    from .render import contrast
                    from .hybrid import ROOT as renderer_root
                    catalogue=read_json(renderer_root/'data/design-palettes.json')
                    selected=catalogue.get(palette)
                    keep_palette=(approved_proposal(plan) is not None and selected is not None
                                  and min(contrast(selected['ink'],selected['panel']),contrast(selected['ink'],selected['accent']))>=4.5)
                    metrics=render_hybrid(card,palette if keep_palette else package['design_palette'],background,path,default_plan(card))
                    decision_status='rejected; safe hybrid fallback'
                decisions[kind]={'position':metrics['panel_position'],'status':decision_status,
                                 'palette':metrics['palette'],'design':metrics['design'],'category_style':metrics['category_style'],
                                 'heading_tone':metrics['heading_tone'],'example_tone':metrics['example_tone'],
                                 'block_styles':metrics['block_styles'],'answer_badges':metrics['answer_badges'],
                                 'block_typography':metrics['block_typography'],'composition':metrics.get('composition'),
                                 **({'rejection':rejection} if rejection is not None else {})}
            else:
                stage='FLUX generation'
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id'],'reviewed_content':package,'artwork_id':artwork_id} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
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
                        'status':status,'cards':decisions})
            write_json(manifest,{'input':render_input(package),'run_url':os.getenv('GITHUB_RUN_URL'),
                               'metrics':{kind:item['metrics'] for kind,item in assets.items()}})
            manifest.chmod(0o600)
        return assets
    except Exception as error:
        raise SafeError(str(error),getattr(error,'stage',None) or stage,
                        getattr(error,'http_status',None),reason=getattr(error,'reason',None),
                        provider_code=getattr(error,'provider_code',None),
                        provider_http_status=getattr(error,'provider_http_status',None)) from None
