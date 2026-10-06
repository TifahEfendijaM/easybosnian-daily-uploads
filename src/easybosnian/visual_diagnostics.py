"""Whitelisted rendering diagnostics, without source copy or free-form model output."""
import copy
import json
from jsonschema import Draft202012Validator

TRUSTED_REJECTION_MESSAGES = frozenset((
    'Actual glyphs exceed block width',
    'Actual photographic text contrast fails; never publish unreadable copy',
    'An unbreakable word exceeds the available width',
    'Bottom sheet requires a wide lower placement',
    'Cannot measure empty copy',
    'Caption treatment is limited to three measured lines',
    'Composition intersects the fixed heading, margin or logo strip',
    'Composition must preserve every reviewed block and quiz label order',
    'Composition palette differs from rendering palette',
    'Composition text blocks overlap or have no breathing room',
    'Editorial explanation must precede the photograph',
    'Editorial italic footer must follow the photograph',
    'Editorial reference cannot fit exact copy',
    'Editorial requires a wide cover-fit photograph',
    'Editorial requires plain explanation and italic footer',
    'Exact text exceeds maximum lines; never truncate',
    'Font size outside the approved role range',
    'Hybrid copy covers too much of the photograph; never shrink/truncate',
    'Hybrid heading exceeds measured lines; never truncate',
    'Hybrid palette fails text contrast',
    'Hybrid separate photograph must remain complete',
    'Invalid hybrid composition contract',
    'Invalid maximum line count',
    'Italic example must fit directly inside the complete photograph',
    'Leading/trailing whitespace cannot be removed without truncation',
    'Line spacing outside the approved multiplier range',
    'Manual line breaks/control whitespace are unsupported',
    'No approved fallback leading fits measured glyphs',
    'Only visual quizzes support smaller complete photo windows',
    'Original logo must retain alpha transparency',
    'Paper examples require automatic palette ink',
    'Paper headings require automatic palette ink',
    'Paper styles require the editorial design',
    'Photo window intersects heading or logo strip',
    'Photographic caption requires a full-background hybrid card',
    'Pill answers are limited to two measured lines',
    'Quiz choices must retain their visual reading order',
    'Quiz photo treatment is fixed by its reviewed task type',
    'Quiz retains its clear photographic design',
    'Requested leading collides with measured glyphs',
    'Separate photograph must remain free of explanation panels',
    'Unknown approved palette',
    'Unshaded photo text fails measured contrast',
    'Unsupported answer badge',
    'Unsupported category treatment',
    'Unsupported example style',
    'Unsupported explanation/answer style',
    'Unsupported photographic colour treatment',
    'Unsupported trusted panel renderer',
    'Unsupported wrapping input',
    'Unsupported wrapping preference',
    'Visual quiz answers must follow the complete photograph',
    'Visual quiz cannot preserve complete photo and exact copy',
    'Visual quiz requires a complete protected photograph',
    'Wrapping would alter exact reviewed text',
))


def approved_proposal(plan):
    from .visual_placement import CARD_SCHEMA
    if list(Draft202012Validator(CARD_SCHEMA).iter_errors(plan)):
        return None
    try:json.dumps(plan,allow_nan=False)
    except (TypeError,ValueError):return None
    return copy.deepcopy(plan)


def rejection_diagnostic(error, plan):
    message=str(error)
    return {'reason':message if message in TRUSTED_REJECTION_MESSAGES else 'Unclassified rendering validation failure',
            'proposal':approved_proposal(plan)}


def safe_rejection(value):
    if not isinstance(value,dict) or set(value)!= {'reason','proposal'}:
        raise ValueError('Invalid safe rendering rejection metadata')
    if not isinstance(value['reason'],str) or (value['reason'] not in TRUSTED_REJECTION_MESSAGES and value['reason']!='Unclassified rendering validation failure'):
        raise ValueError('Unapproved rendering rejection reason')
    proposal=value['proposal']
    if proposal is not None and approved_proposal(proposal) is None:
        raise ValueError('Unapproved rejected rendering parameters')
    return copy.deepcopy(value)
