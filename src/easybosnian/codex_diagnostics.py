"""Fixed classifications of CLI failures; never export messages or model/tool output."""
import json
import re


REASONS = {
    'usage_limit': 'ChatGPT reported an exhausted usage allowance',
    'rate_limit': 'ChatGPT refused the request because of a rate limit',
    'authentication': 'The dedicated cloud ChatGPT sign-in was rejected',
    'refresh_token_reused': 'The dedicated cloud ChatGPT refresh token was already used',
    'connection': 'The ChatGPT connection or response stream failed',
    'service': 'The ChatGPT service returned a server error',
    'configuration': 'The Codex invocation or model configuration was rejected',
    'timeout': 'ChatGPT exceeded the existing execution time allowance',
    'unknown': 'Codex exited unsuccessfully without a recognized failure reason',
}


class CodexExecutionError(ValueError):
    def __init__(self, diagnostic):
        self.reason = diagnostic['reason']
        self.http_status = diagnostic['http_status']
        detail = REASONS[self.reason]
        if diagnostic['exit_code'] is not None:
            detail += f"; CLI exit {diagnostic['exit_code']}"
        if self.http_status is not None:
            detail += f'; HTTP {self.http_status}'
        super().__init__(f'Cloud ChatGPT execution failed: {detail}. No retry or paid fallback was dispatched.')


def _classify(message):
    """Inspect trusted CLI error messages locally; return only bounded identifiers."""
    message = message.lower()
    status = re.search(r'(?:unexpected status|http(?: status)?)[ :]+([45][0-9]{2})\b', message)
    status = int(status[1]) if status else None
    if 'refresh_token_reused' in message or 'refresh token has already been used' in message:
        reason = 'refresh_token_reused'
    elif any(s in message for s in ('usage_limit_reached', "hit your usage limit", 'usage limit exceeded', 'usage allowance exhausted')):
        reason = 'usage_limit'
    elif status == 401 or any(s in message for s in ('invalid_grant', 'token_expired', 'authentication_error', 'unauthorized', 'please sign in again')):
        reason = 'authentication'
    elif status == 429 or 'rate_limit_exceeded' in message:
        reason = 'rate_limit'
    elif status is not None and status >= 500:
        reason = 'service'
    elif any(s in message for s in ('stream disconnected', 'connection reset', 'connection refused', 'error sending request', 'network error', 'error decoding response body')):
        reason = 'connection'
    elif any(s in message for s in ('unexpected argument', 'unrecognized option', 'model_not_found', 'unsupported_model', 'invalid_json_schema')):
        reason = 'configuration'
    else:
        reason = 'unknown'
    return reason, status


def execution_diagnostic(path, exit_code, *, timed_out=False):
    # JSONL item events can contain arbitrary model prose and shell output. NEVER
    # search those for failure keywords. Only CLI error/turn.failed envelopes count.
    started = completed = False
    terminal = None
    errors = []
    startup_errors = []
    with path.open(encoding='utf-8', errors='replace') as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except ValueError:
                if not started and line.startswith(('error:', 'Error:')):
                    startup_errors.append(line[:16384])
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get('type')
            if kind == 'turn.started':
                started = True
            elif kind == 'turn.completed':
                completed = True
            elif kind == 'error' and isinstance(event.get('message'), str):
                errors.append(event['message'][:16384])
            elif kind == 'turn.failed':
                error = event.get('error')
                if isinstance(error, dict) and isinstance(error.get('message'), str):
                    terminal = error['message'][:16384]
    reason, status = _classify(terminal or (errors[-1] if errors else '') or '\n'.join(startup_errors))
    if timed_out:
        reason = 'timeout'
    elif exit_code == 0:
        reason, status = 'success', None
    return {'version': 1, 'reason': reason, 'exit_code': exit_code,
            'http_status': status, 'turn_started': started, 'turn_completed': completed}
