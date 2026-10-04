"""Selection-aware novelty: manual/retained terms may repeat; model choices must be new."""
import copy
from datetime import date as calendar_date
from .validate import instructional, normalise
from .batches import identity, latest_record

CHOICES = ('new', 'same_theme', 'same_words', 'custom')
WORD_ACTIONS = ('keep_today', 'chatgpt', 'entered')
WORD_FALLBACK_CAUSES = ('spelling_correction', 'theme_mismatch', 'invalid_bosnian', 'word_overlap', 'unusable_seed')


def batch_date(history, run_date, target='latest'):
    """Manual replacements keep the latest complete row's date; routine starts use today."""
    if target not in ('latest', 'none', 'today', 'all_today'): raise ValueError('Batch target must be latest, none or all_today')
    if calendar_date.fromisoformat(run_date).isoformat() != run_date:
        raise ValueError('Invalid Sarajevo run date')
    if target in ('none','today','all_today'): return run_date
    record=latest_record(history,run_date)
    return record['date'] if record else run_date


def selection_context(history, date, choice, custom_theme='', custom_words=None, custom_actions=None, source_batch_id=None):
    if choice not in CHOICES: raise ValueError('Unknown content selection')
    previous = next((d['content'] for d in history['days'] if identity(d)==source_batch_id),None) if source_batch_id else next((d['content'] for d in history['days'] if d['date'] == date), None)
    if previous and previous.get('schema_version') != 1: previous = None
    if choice in ('same_theme', 'same_words') and not previous:
        raise ValueError('Reuse requires a complete saved batch; choose new instead')
    result = {'choice': choice, 'previous': previous}
    if source_batch_id:result['source_batch_id']=source_batch_id
    if choice == 'custom':
        theme = custom_theme.strip()
        words = [word.strip() for word in (custom_words or ['', '', ''])]
        if len(words) != 3: raise ValueError('Custom content requires exactly three word fields')
        actions = custom_actions or ['entered' if word else 'keep_today' for word in words]
        if len(actions) != 3 or any(action not in WORD_ACTIONS for action in actions):
            raise ValueError('Choose keep_today, chatgpt or entered for each custom word')
        if not previous and not theme:
            raise ValueError('Without a saved batch, enter a theme')
        for i, action in enumerate(actions):
            if action != 'entered' and words[i]:
                raise ValueError('Clear the word field for keep_today/chatgpt, or select entered to use it')
        theme = theme or previous['theme']['name']
        theme_changed = bool(previous and normalise(theme) != normalise(previous['theme']['name']))
        # Keeping an old-theme word is not a request to force it into a new theme.
        effective_actions = ['chatgpt' if theme_changed and action=='keep_today' else action for action in actions]
        input_fallbacks = []
        seen = set()
        for i, action in enumerate(effective_actions):
            word = previous['words'][i]['lemma'] if action=='keep_today' and previous else words[i]
            cause = None
            if action!='chatgpt':
                if not word or len(word)>180 or not normalise(word): cause='unusable_seed'
                elif normalise(word) in seen: cause='word_overlap'
                else: seen.add(normalise(word))
            if cause:
                effective_actions[i]='chatgpt'
                input_fallbacks.append({'word_index':i,'cause':cause})
        words = [previous['words'][i]['lemma'] if action=='keep_today' else (None if action=='chatgpt' else words[i]) for i, action in enumerate(effective_actions)]
        if len(theme) > 180:
            raise ValueError('Custom theme exceeds the content schema length limit')
        pinned_theme = previous['theme'] if previous and normalise(theme) == normalise(previous['theme']['name']) else None
        old_words = previous['words'] if previous else []
        pinned_words = [next((w for w in old_words if normalise(w['lemma']) == normalise(word)), None) if word is not None else None for word in words]
        result.update(requested_theme=theme, requested_words=words,
                      pinned_theme=pinned_theme, pinned_words=pinned_words, word_actions=effective_actions, theme_changed=theme_changed)
        if input_fallbacks: result['word_input_fallbacks']=input_fallbacks
    return result


def check_selection(package, selection):
    choice = selection['choice']; previous = selection['previous']
    if choice != 'custom' and package.get('private_review',{}).get('word_replacements'):
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
        if previous: check_fresh_copy(package,previous)
        return
    if package['theme'] != previous['theme']:
        raise ValueError('The selected theme and equivalence metadata must remain unchanged')
    if choice == 'same_words':
        if len(package['words']) != len(previous['words']) or any(not retained_metadata(word,pinned,previous) for word,pinned in zip(package['words'],previous['words'])):
            raise ValueError('The selected words, order and equivalence metadata must remain unchanged')
        check_fresh_copy(package,previous)


def check_fresh_copy(package, previous):
    if package['caption'] == previous['caption']:
        raise ValueError('Reusing words requires a fresh caption')
    for new in package['cards']:
        old = next((c for c in previous['cards'] if normalise(c['word']) == normalise(new['word'])), None)
        if old and (instructional(old) == instructional(new) or old['background_prompt'] == new['background_prompt']):
            raise ValueError('Reusing words requires fresh text and background prompts')


def retained_metadata(word, pinned, previous):
    expected=copy.deepcopy(pinned)
    if 'bosnian_level' not in expected and 'bosnian_level' in word:
        expected['bosnian_level']=previous.get('bosnian_level')
    return word==expected


def replacement_review(package, selection):
    """Review permits fallback for one invalid entered/kept seed, never a batch-check waiver."""
    changes=package['private_review'].get('word_replacements',[]);result={}
    if not isinstance(changes,list):
        raise ValueError('Custom replacement reviews must be a list')
    for change in changes:
        if not isinstance(change,dict) or any(not isinstance(change.get(key),str) for key in ('requested_word','chosen_word','reason')):
            raise ValueError('Custom compatibility replacement review is incomplete')
        index=change.get('word_index');cause=change.get('cause','theme_mismatch')
        if (type(index) is not int or index not in (0,1,2) or index in result
                or selection['word_actions'][index] not in ('entered','keep_today')
                or cause not in WORD_FALLBACK_CAUSES
                or (selection['word_actions'][index]=='keep_today' and 'cause' not in change)
                or selection['requested_words'][index] is None
                or not isinstance(change.get('reason'),str) or len(change['reason'])<20
                or normalise(change.get('requested_word',''))!=normalise(selection['requested_words'][index])
                or normalise(change.get('chosen_word',''))!=normalise(package['words'][index]['lemma'])
                or normalise(change['chosen_word'])==normalise(change['requested_word'])):
            raise ValueError('Custom word fallback review does not match an entered or kept word')
        result[index]=change
    return result


def retained_level(word, pinned, previous):
    target=pinned['bosnian_level'] if 'bosnian_level' in pinned else previous.get('bosnian_level')
    if target is None and ('bosnian_level' not in word or word['bosnian_level'] is not None):
        raise ValueError('An unrated retained word must explicitly preserve its unknown level')
    return target


def word_levels(package, selection, global_level):
    if selection['choice']=='same_words':
        return [retained_level(word,pinned,selection['previous']) for word,pinned in zip(package['words'],selection['previous']['words'])]
    if selection['choice']!='custom': return [global_level]*3
    changes=replacement_review(package,selection);targets=[]
    for index,(requested,pinned) in enumerate(zip(selection['requested_words'],selection['pinned_words'])):
        if index in changes and changes[index].get('cause')=='spelling_correction':
            level=package['words'][index].get('bosnian_level')
            if level not in ('A1','A2','B1','B2','C1','C2'):
                raise ValueError('A corrected custom word needs its own reviewed difficulty')
            targets.append(level)
        elif requested is None or index in changes:targets.append(global_level)
        elif pinned:targets.append(retained_level(package['words'][index],pinned,selection['previous']))
        else:
            level=package['words'][index].get('bosnian_level')
            if level not in ('A1','A2','B1','B2','C1','C2'):
                raise ValueError('A compatible new entered word needs its own reviewed difficulty')
            targets.append(level)
    return targets


def novelty_history(history, date, selection, package=None):
    """Keep every history row, exempting only the user's actual selected concepts.

    A spelling correction still represents a manual choice. A different fallback
    represents a model choice and must compare against all history. Final aliases
    come from the checked draft, not a blanket exemption for custom mode.
    """
    result = copy.deepcopy(history)
    result.pop('reused_theme_keys', None)
    result.pop('reused_word_keys', None)
    if selection['choice'] == 'new': return result
    if package: check_selection(package, selection)
    if selection['choice'] == 'custom':
        theme = package['theme'] if package else (selection['pinned_theme'] or
                    {'name': selection['requested_theme'], 'equivalence_keys': []})
        changes = replacement_review(package, selection) if package else {}
        words = []
        for index, requested in enumerate(selection['requested_words']):
            if requested is None: continue  # Explicit/structural delegation to ChatGPT.
            if index in changes and changes[index].get('cause') != 'spelling_correction':
                continue  # An invalid/incompatible seed became a different model choice.
            words.append(package['words'][index] if package else (selection['pinned_words'][index] or
                         {'lemma': requested, 'equivalence_keys': []}))
    else:
        theme = selection['previous']['theme']
        words = selection['previous']['words'] if selection['choice'] == 'same_words' else []
    result['reused_theme_keys'] = [normalise(k) for k in [theme['name'], *theme['equivalence_keys']]]
    result['reused_word_keys'] = [normalise(k) for word in words for k in [word['lemma'], *word['equivalence_keys']]]
    return result
