"""Explicit reuse choices, with narrowly scoped same-date novelty exceptions."""
from .validate import instructional

CHOICES = ('new', 'same_theme', 'same_words')


def selection_context(history, date, choice):
    if choice not in CHOICES: raise ValueError('Unknown content selection')
    previous = next((d['content'] for d in history['days'] if d['date'] == date), None)
    if choice != 'new' and (not previous or previous.get('schema_version') != 1):
        raise ValueError('Reuse requires today\'s complete content row; choose new instead')
    return {'choice': choice, 'previous': previous}


def check_selection(package, selection):
    choice = selection['choice']; previous = selection['previous']
    if choice == 'new': return
    if package['theme'] != previous['theme']:
        raise ValueError('The selected theme and equivalence metadata must remain unchanged')
    if choice == 'same_words' and package['words'] != previous['words']:
        raise ValueError('The selected words, order and equivalence metadata must remain unchanged')
    if choice == 'same_words':
        for old, new in zip(previous['cards'], package['cards']):
            if instructional(old) == instructional(new) or old['background_prompt'] == new['background_prompt']:
                raise ValueError('Reusing words still requires fresh text and a fresh background prompt per card')


def novelty_history(history, date, selection):
    # Keep every older row authoritative. Exempt only explicitly reused metadata
    # from today's row; do not ignore today's old words for same_theme.
    import copy
    result = copy.deepcopy(history)
    if selection['choice'] == 'new': return result
    for day in result['days']:
        if day['date'] != date: continue
        day['content']['theme'] = {'name':'', 'equivalence_keys':[]}
        if selection['choice'] == 'same_words': day['content']['words'] = []
    return result
