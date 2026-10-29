"""Active choices are distinct from archive-readable palette definitions."""
from .core import ROOT,read_json
RETIRED=frozenset(('graphite-chalk',))


def active():return {name:p for name,p in read_json(ROOT/'data/design-palettes.json').items() if name not in RETIRED}


def current(name):return 'mulberry-mint' if name=='graphite-chalk' else name
