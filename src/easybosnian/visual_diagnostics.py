"""Whitelisted rendering diagnostics, without source copy or free-form model output."""
import copy
import json
from jsonschema import Draft202012Validator
from .codex_diagnostics import CodexExecutionError, REASONS as CODEX_REASONS

REVIEW_FAILURES = frozenset(('review timed out', 'ChatGPT execution failed; check sign-in and usage',
    'review returned no result', 'invalid review JSON', 'review violated the declarative schema',
    'review unavailable; exact cause not recorded'))
REVIEW_FAILURES = REVIEW_FAILURES | frozenset(CODEX_REASONS.values())

PALETTE_REASONS = {
    'chatgpt': frozenset(('ChatGPT selected this approved palette',)),
    'fallback': frozenset(('ChatGPT palette missing', 'ChatGPT palette not approved',
        'ChatGPT palette fails text contrast', 'ChatGPT palette fails photographic contrast',
        'Repeated palette lacks required suitability exception',
        'Review unavailable; using preparation palette')),
    'reused': frozenset(('Exact saved card palette retained by user request',)),
    'unknown': frozenset(('Palette source not recorded in this older run',)),
}
PALETTE_RENDER_FAILURES = frozenset((
    'Hybrid palette fails text contrast',
    'Actual photographic text contrast fails; never publish unreadable copy',
    'Unshaded photo text fails measured contrast',
))


def select_palette(plan, fallback):
    """Resolve only the palette; never repair any other reviewed field."""
    from .core import ROOT, read_json
    from .render import contrast
    catalogue=read_json(ROOT/'data/design-palettes.json')
    if fallback not in catalogue:raise ValueError('Unknown approved palette')
    from .palettes import active,current
    fallback=current(fallback)
    choices=active()
    requested=plan.get('palette')
    reason=None
    if 'palette' not in plan:reason='ChatGPT palette missing'
    elif not isinstance(requested,str) or requested not in choices:
        reason='ChatGPT palette not approved'
    else:
        colours=catalogue[requested]
        if min(contrast(colours['ink'],colours['panel']),contrast(colours['ink'],colours['accent']))<4.5:
            reason='ChatGPT palette fails text contrast'
    if reason:return fallback,{'source':'fallback','reason':reason}
    return requested,{'source':'chatgpt','reason':'ChatGPT selected this approved palette'}


def safe_palette_outcome(value):
    if not isinstance(value,dict) or set(value)!= {'source','reason'}:
        raise ValueError('Invalid palette provenance metadata')
    if (not isinstance(value['source'],str) or not isinstance(value['reason'],str) or
            value['source'] not in PALETTE_REASONS or value['reason'] not in PALETTE_REASONS[value['source']]):
        raise ValueError('Unapproved palette provenance metadata')
    return copy.deepcopy(value)


def rendering_provenance(card, review_status=None):
    """Old artifacts cannot establish palette source; never guess from equal IDs."""
    palette=card.get('palette_outcome',{'source':'unknown','reason':'Palette source not recorded in this older run'})
    return {'layout':rendering_outcome(card,review_status),'palette':safe_palette_outcome(palette)}


def review_failure(error):
    if isinstance(error,CodexExecutionError):return CODEX_REASONS[error.reason]
    if isinstance(error,json.JSONDecodeError):return 'invalid review JSON'
    return {
        'ChatGPT review exceeded its time allowance; inspect the run and reviewed content; no retry was dispatched':'review timed out',
        'Cloud ChatGPT execution failed: verify the dedicated sign-in and ChatGPT usage limits; no paid fallback':'ChatGPT execution failed; check sign-in and usage',
        'Cloud ChatGPT ended without its required completion result; no batch was approved':'review returned no result',
        'Invalid visual composition':'review violated the declarative schema',
    }.get(str(error),'review unavailable; exact cause not recorded')


def rendering_outcome(card, review_status=None):
    """Only trusted classifications can reach the summary or recent-design context."""
    status=card.get('status')
    if status=='reused':return {'source':'reused','reason':'Exact saved card retained by user request; no new visual decision'}
    if status=='partial':
        from .element_recovery import safe_recovery
        detail=safe_recovery(card.get('element_recovery'))
        return {'source':'mixed','reason':'Pillow preserved valid ChatGPT elements; fallback only for '+', '.join(detail['fallback'])}
    if status=='adjusted':
        from .visual_adjustment import safe_adjustment, EXAMPLE_LINE_REASON
        detail=safe_adjustment(card.get('layout_adjustment'))
        if detail['reason']==EXAMPLE_LINE_REASON:
            return {'source':'chatgpt','reason':'Pillow preserved ChatGPT’s design with a single-line PRIMJER adjustment'}
        return {'source':'chatgpt','reason':'Pillow preserved ChatGPT’s design with measured placement adjustments'}
    if status=='accepted':return {'source':'chatgpt','reason':'Pillow validated and used ChatGPT’s layout choices'}
    if card.get('rejection'):
        return {'source':'fallback','reason':'Pillow rejected the proposal: '+safe_rejection(card['rejection'])['reason']}
    reason=card.get('review_failure')
    if reason in REVIEW_FAILURES:return {'source':'fallback','reason':reason}
    if status=='default' and review_status=='reviewed':return {'source':'fallback','reason':'ChatGPT marked the proposal uncertain'}
    if status=='rejected; safe hybrid fallback':return {'source':'fallback','reason':'Pillow rejected the proposal; exact cause not recorded in this older run'}
    if review_status=='unavailable':return {'source':'fallback','reason':'review unavailable; exact cause not recorded'}
    return {'source':'unknown','reason':'rendering decision not recorded in this older run'}


def choice_record(metrics,status,policy,palette_outcome,review_status=None,**extra):
    result={'position':metrics['panel_position'],'status':status,
            **{key:metrics.get(key) for key in ('palette','design','category_style','heading_tone','example_tone',
               'heading_backing','block_styles','answer_badges','block_typography','composition')},
            **({'dark_panel_surface':metrics['dark_panel_surface']} if 'dark_panel_surface' in metrics else {}),
            **({'example_shading':metrics['example_shading']} if 'example_shading' in metrics else {}),
            **({'heading_shading':metrics['heading_shading']} if 'heading_shading' in metrics else {}),
            'render_policy':policy,'palette_outcome':palette_outcome,**extra}
    result['outcome']=rendering_outcome(result,review_status)
    result['provenance']=rendering_provenance(result,review_status)
    return result

TRUSTED_REJECTION_MESSAGES = frozenset((
    'Only light explanation panels can reduce surface richness',
    'Light surface richness outside the approved range',
    'Custom example backing requires a full-photo fade and explicit lettering tone',
    'Custom example backing must be a dark six-digit hex colour',
    'Secondary example backing requires a photographic fade',
    'Unsupported secondary example palette',
    'Repair changed a protected approved element',
    'Actual panel text contrast fails; never publish unreadable copy',
    'Unboxed editorial body cannot set panel opacity',
    'Unboxed editorial body requires automatic palette ink',
    'Unsupported panel colour treatment',
    'Unsupported fade treatment',
    'Panel opacity outside the approved range',
    'Category text fails measured contrast',
    'Folded answers are limited to two measured lines',
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
    'Paper headings cannot select a photographic shade',
    'Stronger title shading requires a photographic quiz',
    'Decorative non-quiz title shading requires distant PRIMJER on a full photograph',
    'Increased decorative title strength requires an explicit black backing',
    'Selected title opacity requires black emphasis with distant PRIMJER',
    'All panels in an image must share one opacity',
    'Assigned panel opacity outside the approved range',
    'Only photographic faded examples can select a shade preset',
    'Only photographic faded examples can select shade strength',
    'Paper styles require the editorial design',
    'Photo window intersects heading or logo strip',
    'Photographic caption requires a full-background hybrid card',
    'Pill answers are limited to two measured lines',
    'Quiz choices must retain their visual reading order',
    'Quiz photo treatment is fixed by its reviewed task type',
    'Quiz retains its clear photographic design',
    'Requested leading collides with measured glyphs',
    'Separate photograph must remain free of explanation panels',
    'Separate photo layouts are reserved for picture-identification quizzes',
    'Fresh title shades require smooth edges',
    'Fresh underline panels use minimal_rule; overlay_light is archive-only',
    'Crisp-top PRIMJER shade requires an above-body example near the title',
    'Separate-photo quiz answers require non-dark panel surfaces',
    'Answer badge text fails measured contrast',
    'Non-quiz title cannot remain readable within its shade limit',
    'Visual quiz answers require consistent widths and typography',
    'Visual quiz answers require aligned groups and consistent spacing',
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


def safe_design_attempts(value):
    if not isinstance(value,list) or not 1<=len(value)<=4:raise ValueError('Invalid design attempt diagnostics')
    for item in value:
        if (not isinstance(item,dict) or set(item) not in ({'attempt','result'},{'attempt','result','reason'})
                or type(item['attempt']) is not int or not 1<=item['attempt']<=3
                or item['result'] not in ('accepted','adjusted','rejected','unavailable')):raise ValueError('Invalid design attempt diagnostics')
        if 'reason' in item and item['reason'] not in (*TRUSTED_REJECTION_MESSAGES,'Unclassified rendering validation failure',
                                                      'Repair changed a protected approved element'):
            raise ValueError('Unapproved design attempt reason')
    return copy.deepcopy(value)
