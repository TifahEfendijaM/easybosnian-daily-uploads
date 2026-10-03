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
        theme_changed = bool(previous and normalise(theme) != normalise(previous['theme']['name']))
        # Keeping an old-theme word is not a request to force it into a new theme.
        effective_actions = ['chatgpt' if theme_changed and action=='keep_today' else action for action in actions]
        words = [previous['words'][i]['lemma'] if action=='keep_today' else (None if action=='chatgpt' else words[i]) for i, action in enumerate(effective_actions)]
        fixed = [word for word in words if word is not None]
        if len(set(normalise(w) for w in fixed)) != len(fixed):
            raise ValueError('Custom content requires three distinct words')
        if len(theme) > 180 or any(len(word) > 180 for word in fixed):
            raise ValueError('Custom theme or word exceeds the content schema length limit')
        pinned_theme = previous['theme'] if previous and normalise(theme) == normalise(previous['theme']['name']) else None
        old_words = previous['words'] if previous else []
        pinned_words = [next((w for w in old_words if normalise(w['lemma']) == normalise(word)), None) if word is not None else None for word in words]
        result.update(requested_theme=theme, requested_words=words,
                      pinned_theme=pinned_theme, pinned_words=pinned_words, word_actions=effective_actions, theme_changed=theme_changed)
    return result


def check_selection(package, selection):
    choice = selection['choice']; previous = selection['previous']
    if choice not in ('custom','same_words') and package.get('private_review',{}).get('word_replacements'):
        raise ValueError('Word replacement reviews apply only to custom selections')
    if choice == 'new': return
    if choice == 'custom':
        replacements = replacement_review(package, selection)
        if normalise(package['theme']['name']) != normalise(selection['requested_theme']):
            raise ValueError('Custom theme differs from the requested theme')
        if selection['pinned_theme'] and package['theme'] != selection['pinned_theme']:
            raise ValueError('Reused custom theme metadata must stay unchanged')
        for index, (word, requested, pinned) in enumerate(zip(package['words'], selection['requested_words'], selection['pinned_words'])):
            if index in replacements: continue
            if (requested is not None and normalise(word['lemma']) != normalise(requested)) or (pinned and not retained_metadata(word,pinned,previous)):
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


def retained_metadata(word, pinned, previous):
    expected=copy.deepcopy(pinned)
    if 'bosnian_level' not in expected and 'bosnian_level' in word:
        expected['bosnian_level']=previous.get('bosnian_level')
    return word==expected


def replacement_review(package, selection):
    """A reviewed incompatibility permits replacing an entered word, never a level mismatch."""
    changes=package['private_review'].get('word_replacements',[]);result={}
    if not isinstance(changes,list):
        raise ValueError('Custom replacement reviews must be a list')
    for change in changes:
        if not isinstance(change,dict) or any(not isinstance(change.get(key),str) for key in ('requested_word','chosen_word','reason')):
            raise ValueError('Custom compatibility replacement review is incomplete')
        index=change.get('word_index')
        if (type(index) is not int or index not in (0,1,2) or index in result or selection['word_actions'][index]!='entered'
                or not isinstance(change.get('reason'),str) or len(change['reason'])<20
                or normalise(change.get('requested_word',''))!=normalise(selection['requested_words'][index])
                or normalise(change.get('chosen_word',''))!=normalise(package['words'][index]['lemma'])
                or normalise(change['chosen_word'])==normalise(change['requested_word'])):
            raise ValueError('Custom compatibility replacement review does not match an entered word')
        result[index]=change
    return result


def word_levels(package, selection, global_level):
    if selection['choice']=='same_words': return None
    if selection['choice']!='custom': return [global_level]*3
    changes=replacement_review(package,selection);targets=[]
    for index,(requested,pinned) in enumerate(zip(selection['requested_words'],selection['pinned_words'])):
        if requested is None or index in changes:targets.append(global_level)
        elif pinned:
            target=pinned['bosnian_level'] if 'bosnian_level' in pinned else selection['previous'].get('bosnian_level')
            if target is None and ('bosnian_level' not in package['words'][index] or package['words'][index]['bosnian_level'] is not None):
                raise ValueError('An unrated retained word must explicitly preserve its unknown level')
            targets.append(target)
        else:
            level=package['words'][index].get('bosnian_level')
            if level not in ('A1','A2','B1','B2','C1','C2'):
                raise ValueError('A compatible new entered word needs its own reviewed difficulty')
            targets.append(level)
    return targets


def novelty_history(history, date, selection, package=None):
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
            changes=replacement_review(package,selection) if package else {}
            reused = [word for index,word in enumerate(selection['pinned_words']) if word and index not in changes]
            day['content']['words'] = [w for w in day['content']['words'] if w not in reused]
    return result
