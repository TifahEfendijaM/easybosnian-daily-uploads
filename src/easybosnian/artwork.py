"""Render the selected reviewed history row once, sharing its cards across publishers."""
from .batches import output_key
import io
from PIL import Image
from .core import ROOT
from .http import SafeError, request
from .providers import provider
from .render import render
from .store import wait_for_image


def artwork(store, package, expose=False):
    date=package['date']; output=ROOT/'build'/output_key(package); output.mkdir(parents=True,exist_ok=True)
    assets={}; stage='FLUX generation'
    try:
        for card in package['cards']:
            kind=card['kind']; background=output/f'{kind}-background.jpg'
            stage='FLUX generation'
            Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind,**({'batch_id':package['batch_id']} if package.get('batch_id') else {})))).convert('RGB').save(background,'JPEG',quality=95)
            stage='Pillow rendering'
            path=output/f'{kind}-card.jpg'
            metrics=render(card,package['design_palette'],background,path)
            body=path.read_bytes()
            stage='storage'; store.put_file(output_key(package),path.name,body)
            item={'path':path,'background_path':background,'alt_text':card['alt_text'],'metrics':metrics}
            if expose:
                item['url']=store.expose(output_key(package),path.name,body)
                wait_for_image(item['url'],body,fetch=request)
            assets[kind]=item
        return assets
    except Exception as error:
        raise SafeError(str(error),getattr(error,'stage',None) or stage) from None
