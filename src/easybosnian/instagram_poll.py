"""Exact public quiz choices only; never consume or transmit a private answer key."""
import json
import re
import unicodedata

import regex

OPTION_KEYS = ('option_a', 'option_b', 'option_c', 'option_d')
POLL_MESSAGES = {
    'attached': 'Native poll attached and exact ordered choices read back',
    'option_length': 'Poll omitted: an answer is outside Meta’s 1–25 character limit; answers unchanged',
    'option_whitespace': 'Poll omitted: Meta would trim an answer; reviewed answers unchanged',
    'payload_length': 'Poll omitted: serialized poll exceeds Meta’s 200-character limit; answers unchanged',
    'creation_failure': 'Carousel published, but Meta reported POLL_CREATION_FAILURE; no republish',
    'unexpected_status': 'Carousel published, but Meta returned an unexpected add-on status; no republish',
    'read_failed': 'Carousel published, but poll attachment could not be read; no republish',
    'missing': 'Carousel published, but read-back found no poll; no republish',
    'options_mismatch': 'Carousel published, but poll read-back differs from the reviewed choices/order; no republish',
    'status_read_conflict': 'Carousel published, but attachment status and poll read-back disagree; no republish',
}


def characters(text):
    # Extended grapheme clusters: accents and emoji sequences count as one
    # visible character. Never normalize or modify the transmitted source text.
    return len(regex.findall(r'\X', text))


def serialize_poll(options):
    if (not isinstance(options, dict) or list(options) != list(OPTION_KEYS[:len(options)])
            or len(options) not in (2, 3, 4)
            or any(not isinstance(value, str) for value in options.values())):
        raise ValueError('Poll requires exactly two to four consecutive ordered public options')
    for value in options.values():
        if not 1 <= characters(value) <= 25:
            raise PollLimit('option_length')
        if value != value.strip() or any(unicodedata.category(c) == 'Cc' for c in value):
            raise PollLimit('option_whitespace')
    value = json.dumps(options, ensure_ascii=False, separators=(',', ':'))
    # Meta does not specify grapheme counting for serialized JSON. Count Unicode
    # code points conservatively, including keys, escaping and punctuation.
    if len(value) > 200:
        raise PollLimit('payload_length')
    return value


class PollLimit(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(POLL_MESSAGES[reason])


def quiz_poll(package):
    quiz = package['cards'][0]
    options = quiz.get('options', [])
    if (quiz.get('kind') != 'quiz' or len(options) not in (2, 3, 4)
            or [item.get('label') for item in options] != list('ABCD'[:len(options)])):
        raise ValueError('Native poll requires the reviewed Pitanje dana options in original order')
    poll = {key: item['text'] for key, item in zip(OPTION_KEYS, options)}
    try:
        serialize_poll(poll)
    except PollLimit as error:
        # User-approved handling: keep the entire carousel/copy intact, omit
        # only the native poll, and make the omission prominent in reports.
        return None, {'requested': False, 'attached': False, 'failed': False,
                      'reason': error.reason, 'status': POLL_MESSAGES[error.reason]}
    return poll, {'requested': True, 'attached': False, 'failed': False,
                  'status': 'Native poll requested; attachment not yet confirmed'}


def instagram_caption(package):
    question = package['cards'][0]['question']
    caption = package['caption']
    hashtags = ' '.join(package['hashtags'])
    # Preserve every reviewed character of the caption and its difficulty
    # prose. Insert existing hashtags before the final website line.
    body, separator, footer = caption.rpartition('\n')
    if separator and footer == '👉easybosnian.com':
        earlier, paragraph_break, invitation = body.rpartition('\n\n')
        if paragraph_break:
            caption = earlier + '\n\n' + hashtags + '\n\n' + invitation + '\n' + footer
        else:
            caption = hashtags + '\n\n' + caption
    else:  # Legacy content stays readable without inventing a new invitation.
        caption += '\n\n' + hashtags
    if question not in caption:
        caption = 'Pitanje dana: ' + question + '\n\n' + caption
    if len(caption) > 2200 or len(re.findall(r'(?<!\w)#\w+', caption)) > 30 or len(re.findall(r'(?<!\w)@\w+', caption)) > 20:
        raise ValueError('Instagram caption exceeds Meta’s 2200 characters, 30 hashtags or 20 mentions; rewrite reviewed copy, never truncate')
    return caption


def poll_readback(response, expected, attachment_status=None):
    actual = response.get('poll_attachment') if isinstance(response, dict) else None
    matches = (isinstance(actual, dict)
               and {key: actual[key] for key in OPTION_KEYS if key in actual} == expected)
    if attachment_status is not None:
        reason = ('status_read_conflict' if matches else 'creation_failure'
                  if attachment_status == 'POLL_CREATION_FAILURE' else 'unexpected_status')
    elif actual is None:
        reason = 'missing'
    elif not matches:
        reason = 'options_mismatch'
    else:
        reason = 'attached'
    return {'requested': True, 'attached': reason == 'attached', 'failed': reason != 'attached',
            'reason': reason, 'status': POLL_MESSAGES[reason]}
