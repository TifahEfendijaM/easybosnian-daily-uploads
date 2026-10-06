import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from easybosnian.meta import Facebook
from easybosnian.facebook import publish_facebook
from easybosnian.http import SafeError
from test_project import reviewed_fixture


class FacebookAuthorizationTests(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ,{'META_GRAPH_VERSION':'v26.0'}):return Facebook('protected','1284422991426579')

    def test_exact_page_and_posting_capability_required_before_upload(self):
        facebook=self.client()
        valid={'id':facebook.page_id,'name':'Easy Bosnian','can_post':True}
        for mutation in ('valid','id','name','denied','missing'):
            page=dict(valid)
            if mutation=='id':page['id']='different'
            elif mutation=='name':page['name']='different'
            elif mutation=='denied':page['can_post']=False
            elif mutation=='missing':page.pop('can_post')
            facebook.call=MagicMock(return_value=page)
            if mutation=='valid':self.assertEqual(facebook.verify_page(),valid)
            else:
                with self.assertRaises(ValueError):facebook.verify_page()
            self.assertEqual(facebook.call.call_args.args,('GET','me',{'fields':'id,name,can_post'}))

    def test_photo_permission_failure_survives_platform_summary_without_retry(self):
        package=reviewed_fixture();fb=MagicMock();fb.photo.side_effect=SafeError('HTTP 403; provider code 200; provider subcode unavailable',http_status=403)
        with tempfile.TemporaryDirectory() as tmp,patch('easybosnian.facebook.ROOT',Path(tmp)),patch('easybosnian.facebook.Facebook',return_value=fb),patch('easybosnian.facebook.require_publishing'),patch('easybosnian.facebook.failure',return_value='safe failure'),patch.dict(os.environ,{'FACEBOOK_POSTING_ENABLED':'true'}):
            with self.assertRaisesRegex(SafeError,'HTTP 403; provider code 200'):
                publish_facebook(package,{c['kind']:{'url':'https://images.example/card.jpg'} for c in package['cards']})
            result=json.loads((Path(tmp)/'build'/package['date']/'facebook-result.json').read_text())
        self.assertEqual(result['failed_stage'],'Facebook photo upload')
        self.assertIn('provider code 200',result['error'])
        fb.photo.assert_called_once();fb.publish.assert_not_called()


if __name__=='__main__':unittest.main()
