"""Render the selected reviewed history row once, sharing its cards across publishers."""
from .batches import output_key
import io
import os
from PIL import Image
from .core import ROOT, read_json, write_json
from .http import SafeError, request
from .providers import provider
from .hybrid import default_plan, editorial_plan, render_hybrid
from .store import wait_for_image


def render_input(package):
    # Ephemeral artwork-cache provenance, not immutable history or publication state.
    return {'rendering_version':4, **{key:package.get(key) for key in ('batch_id','date','design_palette')},
            'cards':[{key:value for key,value in card.items() if key!='design_template'} for card in package['cards']]}


def artwork(store, package, expose=False, review_images=False, require_prepared=False):
    date=package['date']; output=ROOT/'build'/output_key(package); output.mkdir(parents=True,exist_ok=True)
    assets={}; stage='FLUX generation'
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
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id']} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                baseline=output/f'{kind}-hybrid-reference.jpg'
                metrics=render_hybrid(card,package['design_palette'],background,baseline)
                sheet=output/f'{kind}-placement-sheet.jpg'
                editorial=None
                if kind!='quiz':
                    try:
                        editorial=output/f'{kind}-editorial-reference.jpg'
                        render_hybrid(card,package['design_palette'],background,editorial,editorial_plan(card))
                    except ValueError:editorial=None  # Exact long copy may not fit this optional reference.
                composition_sheet(background,baseline,sheet,editorial)
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
                stage='Pillow rendering'
                try:
                    metrics=render_hybrid(card,palette,background,path,plan)
                    decision_status='accepted' if plan['confidence']=='high' else 'default'
                except ValueError:
                    # Bad cosmetic geometry/contrast cannot trigger a second model
                    # call, generation, or publication. The premeasured reference is safe.
                    metrics=render_hybrid(card,package['design_palette'],background,path,default_plan(card))
                    decision_status='rejected; safe hybrid fallback'
                    print('::warning::Hybrid composition rejected; using measured reference without retry')
                decisions[kind]={'position':metrics['panel_position'],'status':decision_status,
                                 'palette':metrics['palette'],'design':metrics['design'],'block_styles':metrics['block_styles'],'block_typography':metrics['block_typography'],'composition':metrics.get('composition')}
            else:
                stage='FLUX generation'
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id']} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
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
        raise SafeError(str(error),getattr(error,'stage',None) or stage) from None
