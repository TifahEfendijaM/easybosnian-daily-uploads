"""One cached set of FLUX backgrounds shared by all platform renderers."""
import io

from PIL import Image

from .core import ROOT
from .http import SafeError
from .providers import provider
from .render import render


def artwork(store, date, record, vertical=False):
    output = ROOT / "build" / date
    output.mkdir(parents=True, exist_ok=True)
    stage = "storage"
    try:
        for card in record["package"]["cards"]:
            kind = card["kind"]
            item = record["state"].setdefault("cards", {}).setdefault(kind, {})
            background = output / f"{kind}-background.jpg"
            if item.get("background_saved"):
                stage = "storage"
                background.write_bytes(store.get_file(date, background.name))
            else:
                stage = "FLUX generation"
                Image.open(io.BytesIO(provider().generate(card["background_prompt"], date, kind))).convert("RGB").save(background, "JPEG", quality=95)
                stage = "storage"
                store.put_file(date, background.name, background.read_bytes())
                item["background_saved"] = True
                store.save(date, record)
            key = "tiktok_render_saved" if vertical else "render_saved"
            rendered = output / f"{kind}-{'tiktok' if vertical else 'card'}.jpg"
            if item.get(key):
                stage = "storage"
                rendered.write_bytes(store.get_file(date, rendered.name))
            else:
                stage = "Pillow rendering"
                metrics = render(card, record["package"]["design_palette"], background, rendered, tiktok=vertical)
                stage = "storage"
                store.put_file(date, rendered.name, rendered.read_bytes())
                item[key] = True
                item["tiktok_metrics" if vertical else "metrics"] = metrics
                store.save(date, record)
        return output
    except Exception as error:
        raise SafeError(str(error), getattr(error, "stage", None) or stage) from None
