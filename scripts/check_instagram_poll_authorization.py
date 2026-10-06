"""Read-only scope/account audit; no token, raw response or social write is logged."""
import json
import os

from easybosnian.cli import load_env
from easybosnian.core import verify_repository
from easybosnian.meta import InstagramDeletion


def audit():
    verify_repository(remote=True)
    client = InstagramDeletion()
    client.verify_account()
    granted = {item.get('permission') for item in client.call('GET', 'me/permissions')['data']
               if item.get('status') == 'granted'}
    required = {'instagram_basic', 'instagram_content_publish', 'pages_read_engagement', 'pages_show_list'}
    return {'account': '@easy_bosnian', 'linked_page_verified': True,
            'granted_poll_scopes': sorted(required & granted),
            'missing_poll_scopes': sorted(required - granted),
            'separate_poll_credential_configured': bool(os.getenv('INSTAGRAM_FACEBOOK_ACCESS_TOKEN')),
            'publication': 'Read-only; no container, post, Story or deletion request'}


if __name__ == '__main__':
    load_env()
    print(json.dumps(audit(), indent=2))
