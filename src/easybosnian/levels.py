"""Active per-run level selection and retained inactive legacy setting utilities."""
import base64
import json
import secrets

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


# Exact halving probabilities through C1; the remaining tail belongs to C2.
RANDOM_LEVEL = 'random'
LEVEL_WEIGHTS = (32,16,8,4,2,2)

def random_level():
    ticket=secrets.randbelow(sum(LEVEL_WEIGHTS))
    for level,weight in zip(LEVELS,LEVEL_WEIGHTS):
        if ticket<weight:return level
        ticket-=weight
    raise AssertionError('Unreachable difficulty ticket')


def select_run_level(selection, requested=RANDOM_LEVEL):
    """One per-run snapshot; the archived persistent setting has no authority."""
    if requested not in (RANDOM_LEVEL,*LEVELS):raise ValueError('Choose random or A1–C2 difficulty')
    if selection['choice'] in ('new','same_theme','custom'):
        return random_level() if requested==RANDOM_LEVEL else requested
    previous=selection.get('previous') or {}
    level=previous.get('bosnian_level')
    return level if level in LEVELS else random_level()
