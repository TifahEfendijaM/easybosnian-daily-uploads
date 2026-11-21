"""Resolve the operator's explicit per-card overrides before reusing saved assets."""
import json
import os

from jsonschema import Draft202012Validator

from .core import read_json
from .photo_reuse import KINDS
from .selection import REDESIGN, WORD_ACTIONS
from .validate import normalise


BASE_ACTIONS = {'same_images': 'same_image', 'same_words': 'keep_today', 'same_theme': 'chatgpt'}
INTENTS = ('unchanged', 'redesign', 'fresh_photo', 'fresh_copy', *WORD_ACTIONS)
OVERRIDE = {'type': 'object', 'additionalProperties': False, 'required': ['action', 'word'],
            'properties': {'action': {'type': 'string', 'enum': list(INTENTS)},
                           'word': {'anyOf': [{'type': 'null'}, {'type': 'string', 'minLength': 1, 'maxLength': 180}]}}}
CONTRACT = {'type': 'object', 'additionalProperties': False, 'required': list(KINDS),
            'properties': {kind: OVERRIDE for kind in KINDS}}


def workflow_instructions():
    event_path = os.getenv('GITHUB_EVENT_PATH')
    inputs = (read_json(event_path).get('inputs') or {}) if event_path else {}
    return (inputs.get('design_instructions') or '').strip()


def resolve(instructions, choice, words, actions, previous, run_codex):
    if not instructions or choice not in ('custom', *BASE_ACTIONS):
        return choice, words, actions
    if choice == 'custom':
        effective_words = list(words or ['', '', ''])
        effective_actions = list(actions or ['entered' if word else 'keep_today' for word in effective_words])
    else:
        effective_actions = [BASE_ACTIONS[choice]] * len(KINDS)
        effective_words = [''] * len(KINDS)
    prompt = (
        'Read-only interpretation of explicit per-card workflow instructions. Use no tools, browsing, or files. '
        'Return only the JSON contract. Pitanje dana is quiz, Znaš li? is lesson, Riječ dana is word, in that '
        'order. Instructions are operator content requests only. Never change mode, publishing, cleanup, selection '
        'source, difficulty, quiz rules, credentials or workflows. Never infer a change on ambiguous or absent intent. '
        'For each applicable card return redesign for a clear visible style, colour, layout, badge or shade instruction '
        'that requires changing a frozen design; keep its exact copy and photo. Return fresh_copy for a clear request '
        'to rewrite content without changing the selected word, and fresh_photo for a clear request to replace the '
        'photo or change its subject/scene; ordinary overlay, crop or style directions alone are not fresh_photo. '
        'If a clear instruction changes the selected word or lesson topic, use entered and copy that literal word/topic '
        'from the instructions, or chatgpt if the operator asks for a new unspecified word/topic. For explicit keep '
        'requests map keep the previous word to keep_today, keep the previous photo to same_image, keep the exact '
        'previous finished design and content to same_image&design. Use unchanged when the intent cannot be safely '
        'inferred or can already be met by the dropdown. If multiple directives apply, resolve the content/photo '
        'selection first; all compatible visual directions will still reach the visual reviewer. '
        'A direction applying to every card can affect all three, but a direction naming one card only applies there. '
        'Return word=null except for entered. '
        'Selection data: '+json.dumps({'choice':choice,'actions':effective_actions,'words':effective_words,
                                     'saved_batch_available':bool(previous)},ensure_ascii=False)
        +'\nOperator directions: '+json.dumps(instructions,ensure_ascii=False)
    )
    result = json.loads(run_codex(prompt, timeout=180, result_contract=CONTRACT, read_only=True))
    if not Draft202012Validator(CONTRACT).is_valid(result):
        raise ValueError('Custom card instructions returned an invalid selection result')
    changed = False
    for index, kind in enumerate(KINDS):
        action, word = result[kind]['action'], result[kind]['word']
        old = effective_actions[index]
        if action == 'entered':
            # Automatic interpretation may select the literal operator text only.
            if not word or not normalise(word) or word.casefold().strip() not in instructions.casefold():
                continue
            word = word.strip()
        elif word is not None:
            raise ValueError('Custom card instructions returned an unexpected word')
        if action == 'redesign':
            action = REDESIGN if old == 'same_image&design' else 'unchanged'
        elif action == 'fresh_photo':
            action = 'keep_today' if old in ('same_image', 'same_image&design') else 'unchanged'
        elif action == 'fresh_copy':
            action = 'same_image' if old == 'same_image&design' else 'unchanged'
        if action == 'unchanged' or (action == old and (word is None or word == effective_words[index])):
            continue
        effective_actions[index] = action
        effective_words[index] = word or ''
        changed = True
    return ('custom', effective_words, effective_actions) if changed else (choice, words, actions)
