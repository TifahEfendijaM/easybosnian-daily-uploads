"""Render the selected reviewed history row once, sharing its cards across publishers."""
import io
from PIL import Image
from .core import ROOT
from .http import SafeError, request
from .providers import provider
from .render import render


def artwork(store, package, expose=False):
    date=package['date']; output=ROOT/'build'/date; output.mkdir(parents=True,exist_ok=True)
    assets={}; stage='FLUX generation'
    try:
        for card in package['cards']:
            kind=card['kind']; background=output/f'{kind}-background.jpg'
            stage='FLUX generation'
            Image.open(io.BytesIO(provider().generate(card['background_prompt'],date,kind))).convert('RGB').save(background,'JPEG',quality=95)
            stage='Pillow rendering'
            path=output/f'{kind}-card.jpg'
            metrics=render(card,package['design_palette'],background,path)
            stage='storage'; store.put_file(date,path.name,path.read_bytes())
            item={'path':path,'background_path':background,'alt_text':card['alt_text'],'metrics':metrics}
            if expose:
                item['url']=store.expose(date,path.name)
                if request('GET',item['url'],raw=True)!=path.read_bytes():
                    raise ValueError('Public image bytes differ from the reviewed renderer output')
            assets[kind]=item
        return assets
    except Exception as error:
        raise SafeError(str(error),getattr(error,'stage',None) or stage) from None
