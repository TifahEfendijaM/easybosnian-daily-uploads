"""In-run design repair; successful elements remain exact, never a publish retry."""
import copy
from .hybrid import default_plan, roles, validate_current_design
from .element_recovery import GLOBAL_GROUPS, recover_elements, recoverable_proposal
from .visual_adjustment import nearest_valid_plan, applied_adjustment, single_line_example_plan
from .visual_diagnostics import rejection_diagnostic, PALETTE_RENDER_FAILURES

ATTEMPT_LIMIT=3


class PaletteValidationError(ValueError):
    def __init__(self,reason,plan,attempts):
        super().__init__(reason)
        self.plan=copy.deepcopy(plan);self.attempts=copy.deepcopy(attempts)


def unchanged(requested,revised,preserved):
    old={b['role']:b for b in requested['blocks']};new={b['role']:b for b in revised.get('blocks',[])}
    return (requested.get('palette')==revised.get('palette')
            and all((all(requested.get(k)==revised.get(k) for k in GLOBAL_GROUPS[n]) if n in GLOBAL_GROUPS
                     else old.get(n)==new.get(n)) for n in preserved))


def render_design(card,plan,background,draw,*,model_accepted,repair=None,attempt_limit=ATTEMPT_LIMIT,invalid_elements=()):
    """Return the rendered plan plus safe metadata. Only Pillow rejections retry.

    A service/authorization/timeout failure never triggers another request.
    A known partial candidate is a proof of which elements can remain exact;
    repairs are forbidden from changing those elements or the approved palette.
    """
    if type(attempt_limit) is not int or not 1<=attempt_limit<=ATTEMPT_LIMIT:raise ValueError('Invalid design attempt limit')
    legacy_draw=draw
    def draw(candidate):
        validate_current_design(card,candidate)
        return legacy_draw(candidate)
    current=copy.deepcopy(plan);rejection=None;attempts=[];recovery=None;protected=set();repair_violation=None
    def render(candidate):
        wide=single_line_example_plan(card,candidate,background) if model_accepted and 'example' not in protected else None
        if wide is not None:
            try:return draw(wide)
            except ValueError:pass
        return draw(candidate)
    for attempt in range(1,attempt_limit+1):
        try:
            if repair_violation:raise ValueError(repair_violation)
            if invalid_elements:raise ValueError('Invalid hybrid composition contract')
            metrics=render(current)
            adjustment=applied_adjustment(current,metrics['composition']) if model_accepted else None
            return metrics,{'status':('adjusted' if adjustment else 'accepted') if model_accepted else 'default',
                **({'layout_adjustment':adjustment} if adjustment else {}),
                **({'rejection':rejection} if rejection else {}),
                **({'design_attempts':attempts+[{'attempt':attempt,'result':'accepted'}]} if attempts else {})}
        except ValueError as error:
            if not model_accepted:raise
            rejection=rejection_diagnostic(error,current)
            attempts.append({'attempt':attempt,'result':'rejected','reason':rejection['reason']})
        repair_violation=None
        recovered=recover_elements(card,current,background,draw,required=invalid_elements,reason=rejection['reason'])
        if recovered:recovery=recovered
        if recovery:
            _,detail=recovery
            protected.update(detail['preserved'])
            locked=tuple(r for r in roles(card) if r in detail['preserved'])
            adjusted=nearest_valid_plan(card,current,background,locked_roles=locked,
                lock_window='photo_window' in detail['preserved'],reason=rejection['reason'])
            if adjusted and not invalid_elements:
                try:
                    metrics=draw(adjusted[0])
                    return metrics,{'status':'adjusted','layout_adjustment':applied_adjustment(current,metrics['composition']),
                        'rejection':rejection,'design_attempts':attempts+[{'attempt':attempt,'result':'adjusted'}]}
                except ValueError:pass
        if attempt==attempt_limit or repair is None:break
        # Only schema-approved values from the proven safe candidate are exposed;
        # no invalid/free-form input or fallback treatment becomes a recommendation.
        detail=recovery[1] if recovery else None
        preserved=detail['preserved'] if detail else []
        valid=recovery[0]['composition'] if recovery else None
        feedback={'reason':rejection['reason'],'previous':rejection['proposal'],
                  'failed_elements':detail['fallback'] if detail else roles(card)+list(GLOBAL_GROUPS),
                  'preserved_elements':preserved,
                  'preserved_values':({**{k:valid.get(k) for n,keys in GLOBAL_GROUPS.items() if n in preserved for k in keys},
                    'blocks':[b for b in valid['blocks'] if b['role'] in preserved]} if valid else {})}
        revised,status=repair(feedback)
        if status!='reviewed':
            attempts.append({'attempt':attempt+1,'result':'unavailable'})
            break  # No service-error retry; retain the local safe result.
        if not isinstance(revised,dict) or revised.get('confidence')!='high':break
        if not recoverable_proposal(card,revised):
            repair_violation='Invalid hybrid composition contract'
            continue
        if not unchanged(current,revised,preserved):
            repair_violation='Repair changed a protected approved element'
            continue
        current=copy.deepcopy(revised)
        invalid_elements=()
    if recovery:
        metrics,detail=recovery
        # Candidate searches render multiple files. Redraw the selected candidate.
        metrics=draw(metrics['composition'])
        return metrics,{'status':'partial','element_recovery':detail,'rejection':rejection,'design_attempts':attempts}
    if recoverable_proposal(card,current) and rejection['reason'] in PALETTE_RENDER_FAILURES:
        raise PaletteValidationError(rejection['reason'],current,attempts)
    # Unavailable/uncertain/untrusted structures cannot establish valid elements.
    return draw(default_plan(card)),{'status':'rejected; safe hybrid fallback','rejection':rejection,'design_attempts':attempts}
