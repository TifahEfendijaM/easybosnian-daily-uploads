"""Explicit reuse choices, with narrowly scoped same-date novelty exceptions."""
import copy
from .validate import instructional, normalise

CHOICES = ('new', 'same_theme', 'same_words', 'custom')
WORD_ACTIONS = ('keep_today', 'chatgpt', 'entered')


def selection_context(history, date, choice, custom_theme='', custom_words=None, custom_actions=None):
    if choice not in CHOICES: raise ValueError('Unknown content selection')
    previous = next((d['content'] for d in history['days'] if d['date'] == date), None)
    if previous and previous.get('schema_version') != 1: previous = None
    if choice in ('same_theme', 'same_words') and not previous:
        raise ValueError('Reuse requires today\'s complete content row; choose new instead')
    result = {'choice': choice, 'previous': previous}
    if choice == 'custom':
        theme = custom_theme.strip()
        words = [word.strip() for word in (custom_words or ['', '', ''])]
        if len(words) != 3: raise ValueError('Custom content requires exactly three word fields')
        actions = custom_actions or ['entered' if word else 'keep_today' for word in words]
        if len(actions) != 3 or any(action not in WORD_ACTIONS for action in actions):
            raise ValueError('Choose keep_today, chatgpt or entered for each custom word')
        if not previous and (not theme or 'keep_today' in actions):
            raise ValueError('Without today\'s saved content, enter a theme and enter or delegate every word')
        for i, action in enumerate(actions):
            if action == 'entered' and not words[i]:
                raise ValueError('The entered word action requires a word in its matching field')
            if action != 'entered' and words[i]:
                raise ValueError('Clear the word field for keep_today/chatgpt, or select entered to use it')
        theme = theme or previous['theme']['name']
        words = [previous['words'][i]['lemma'] if action=='keep_today' else (None if action=='chatgpt' else words[i]) for i, action in enumerate(actions)]
        fixed = [word for word in words if word is not None]
        if len(set(normalise(w) for w in fixed)) != len(fixed):
            raise ValueError('Custom content requires three distinct words')
        if len(theme) > 180 or any(len(word) > 180 for word in fixed):
            raise ValueError('Custom theme or word exceeds the content schema length limit')
        pinned_theme = previous['theme'] if previous and normalise(theme) == normalise(previous['theme']['name']) else None
        old_words = previous['words'] if previous else []
        pinned_words = [next((w for w in old_words if normalise(w['lemma']) == normalise(word)), None) if word is not None else None for word in words]
        result.update(requested_theme=theme, requested_words=words,
                      pinned_theme=pinned_theme, pinned_words=pinned_words, word_actions=actions)
    return result


def check_selection(package, selection):
    choice = selection['choice']; previous = selection['previous']
    if choice == 'new': return
    if choice == 'custom':
        if normalise(package['theme']['name']) != normalise(selection['requested_theme']):
            raise ValueError('Custom theme differs from the requested theme')
        if selection['pinned_theme'] and package['theme'] != selection['pinned_theme']:
            raise ValueError('Reused custom theme metadata must stay unchanged')
        for word, requested, pinned in zip(package['words'], selection['requested_words'], selection['pinned_words']):
            if (requested is not None and normalise(word['lemma']) != normalise(requested)) or (pinned and word != pinned):
                raise ValueError('Custom word or reused equivalence metadata differs from the requested selection')
        if previous:
            if package['caption'] == previous['caption']:
                raise ValueError('Custom content requires a fresh caption')
            for new in package['cards']:
                old = next((c for c in previous['cards'] if normalise(c['word']) == normalise(new['word'])), None)
                if old and (instructional(old) == instructional(new) or old['background_prompt'] == new['background_prompt']):
                    raise ValueError('Custom reuse requires fresh text and background prompts')
        return
    if package['theme'] != previous['theme']:
        raise ValueError('The selected theme and equivalence metadata must remain unchanged')
    if choice == 'same_words' and package['words'] != previous['words']:
        raise ValueError('The selected words, order and equivalence metadata must remain unchanged')
    if choice == 'same_words':
        expected = copy.deepcopy(previous)
        for old, new in zip(previous['cards'], package['cards']):
            if old['background_prompt'] == new['background_prompt']:
                raise ValueError('Image-only reruns require a fresh background prompt per card')
        for old, new in zip(expected['cards'], package['cards']): old['background_prompt'] = new['background_prompt']
        if package != expected:
            raise ValueError('Image-only reruns must preserve all existing content, palette and layouts')


def novelty_history(history, date, selection):
    # Keep every older row authoritative. Exempt only explicitly reused metadata
    # from today's row; do not ignore today's old words for same_theme.
    result = copy.deepcopy(history)
    if selection['choice'] == 'new': return result
    for day in result['days']:
        if day['date'] != date: continue
        if selection['choice'] != 'custom' or selection['pinned_theme']:
            day['content']['theme'] = {'name':'', 'equivalence_keys':[]}
        if selection['choice'] == 'same_words': day['content']['words'] = []
        if selection['choice'] == 'custom':
            reused = [word for word in selection['pinned_words'] if word]
            day['content']['words'] = [w for w in day['content']['words'] if w not in reused]
    return result
