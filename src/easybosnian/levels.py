"""One persistent repository configuration for future preparation, no provider state."""
import base64
import json

from .core import ROOT, REPO, gh

LEVELS = ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')
KEEP_CURRENT = 'Keep current'
SETTINGS_PATH = 'data/preparation-settings.json'


def settings_level(value):
    if not isinstance(value, dict) or set(value) != {'bosnian_level'} or value['bosnian_level'] not in LEVELS:
        raise ValueError('Preparation settings must contain one valid A1–C2 bosnian_level')
    return value['bosnian_level']


def load_level():
    return settings_level(json.loads((ROOT / SETTINGS_PATH).read_text()))


def set_level(level):
    """A manually invoked configuration workflow updates only this main-branch file."""
    if level not in (KEEP_CURRENT,*LEVELS): raise ValueError('Choose Keep current or an A1–C2 Bosnian level')
    endpoint = f'repos/{REPO}/contents/{SETTINGS_PATH}'
    current = json.loads(gh('api', endpoint+'?ref=main'))
    old = settings_level(json.loads(base64.b64decode(current['content'])))
    if level == KEEP_CURRENT: return {'bosnian_level': old, 'updated': False}
    if old == level: return {'bosnian_level': level, 'updated': False}
    body = json.dumps({'bosnian_level': level}, indent=2)+'\n'
    payload = {'message': 'Set EasyBosnian preparation level to '+level, 'branch': 'main',
               'sha': current['sha'], 'content': base64.b64encode(body.encode()).decode()}
    gh('api', endpoint, '--method', 'PUT', '--input', '-', input_text=json.dumps(payload))
    actual = json.loads(gh('api', endpoint+'?ref=main'))
    if settings_level(json.loads(base64.b64decode(actual['content']))) != level:
        raise ValueError('The requested global difficulty was not confirmed; no update retry')
    return {'bosnian_level': level, 'updated': True}
