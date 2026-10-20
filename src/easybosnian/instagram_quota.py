"""Read the authorized account's live publishing allowance; never reserve or retry."""
from .http import SafeError


def publishing_quota(ig, required=3):
    """A missing/unsupported read is unknown, never an invented zero or limit."""
    try:
        response=ig.publishing_limit()
    except Exception:
        return {'status':'unavailable','reason':'quota_read_failed'}
    rows=response.get('data') if isinstance(response,dict) else None
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):
        return {'status':'unavailable','reason':'quota_response_invalid'}
    row=rows[0];config=row.get('config')
    if not isinstance(config,dict):return {'status':'unavailable','reason':'quota_response_invalid'}
    used,total,duration=row.get('quota_usage'),config.get('quota_total'),config.get('quota_duration')
    if (type(used) is not int or used<0 or type(total) is not int or total<=0
            or type(duration) is not int or duration<=0):
        return {'status':'unavailable','reason':'quota_response_invalid'}
    return {'status':'available','quota_usage':used,'quota_total':total,
            'quota_duration':duration,'remaining':max(0,total-used),'required':required}


def require_story_capacity(quota):
    if quota['status']=='available' and quota['remaining']<quota['required']:
        raise SafeError(f"Instagram publishing quota has only {quota['remaining']} slots available "
                        f"for {quota['required']} Stories; wait for the rolling allowance to recover; no automatic retry",
                        reason='instagram_publishing_limit')
