"""Render the selected reviewed history row once, sharing its cards across publishers."""
from .batches import output_key
import io
import os
import shutil
from PIL import Image
from .core import ROOT, read_json, write_json
from .http import SafeError, request
from .providers import provider
from .render import render
from .store import wait_for_image


def render_input(package):
    # Ephemeral artwork-cache provenance, not immutable history or publication state.
    return {key: package.get(key) for key in ('batch_id', 'date', 'design_palette', 'cards')}


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
            from .visual_placement import contact_sheet, review_positions
            for card in package['cards']:
                kind=card['kind']; background=output/f'{kind}-background.jpg'
                stage='FLUX generation'
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id']} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                paths={position:output/f'{kind}-{position}-candidate.jpg' for position in ('normal','bottom')}
                metrics={position:render(card,package['design_palette'],background,path,panel_position=position) for position,path in paths.items()}
                sheet=output/f'{kind}-placement-sheet.jpg'
                contact_sheet(background,paths['normal'],paths['bottom'],sheet)
                candidates[kind]={'paths':paths,'metrics':metrics,'sheet':sheet,
                    'movable':not (kind=='quiz' and card.get('quiz_format')=='visual_identification')}
            decisions,status=review_positions(package,candidates)
            write_json(output/'image-placement-result.json',{'batch':date,'batch_id':package.get('batch_id'),
                        'status':status,'cards':decisions})
        for card in package['cards']:
            kind=card['kind']; background=output/f'{kind}-background.jpg'
            path=output/f'{kind}-card.jpg'
            if require_prepared:
                if not path.is_file() or not background.is_file():
                    raise ValueError('Prepared artwork is incomplete; no generation or publication retry')
                metrics=saved['metrics'][kind]
            elif review_images:
                position=decisions[kind]['position']
                shutil.copyfile(candidates[kind]['paths'][position],path)
                metrics=candidates[kind]['metrics'][position]
            else:
                stage='FLUX generation'
                Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id']} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
                stage='Pillow rendering'
                metrics=render(card,package['design_palette'],background,path)
            body=path.read_bytes()
            stage='storage'
            if not require_prepared: store.put_file(output_key(package),path.name,body)
            item={'path':path,'background_path':background,'alt_text':card['alt_text'],'metrics':metrics}
            if expose:
                item['url']=store.expose(output_key(package),path.name,body)
                wait_for_image(item['url'],body,fetch=request)
            assets[kind]=item
        if review_images:
            write_json(manifest,{'input':render_input(package),'run_url':os.getenv('GITHUB_RUN_URL'),
                               'metrics':{kind:item['metrics'] for kind,item in assets.items()}})
            manifest.chmod(0o600)
        return assets
    except Exception as error:
        raise SafeError(str(error),getattr(error,'stage',None) or stage) from None
