import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from PIL import Image
from easybosnian.design_repair import render_design
from easybosnian.hybrid import default_plan,render_hybrid
from test_project import reviewed_fixture


class DesignRepairTests(unittest.TestCase):
    def test_model_repairs_only_failed_block_and_successful_elements_stay_exact(self):
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high',palette='burgundy-oat')
        plan['blocks'][0].update(style='outlined',max_lines=1)
        revised=copy.deepcopy(plan);revised['blocks'][0]['max_lines']=None
        repair=Mock(return_value=(revised,'reviewed'))
        with tempfile.TemporaryDirectory() as tmp:
            photo=Path(tmp)/'photo.jpg';Image.new('RGB',(1024,1024),'#728192').save(photo,'JPEG')
            path=Path(tmp)/'out.jpg'
            draw=lambda candidate:render_hybrid(card,plan['palette'],photo,path,candidate)
            metrics,detail=render_design(card,plan,photo,draw,model_accepted=True,repair=repair)
        repair.assert_called_once();self.assertEqual(detail['status'],'accepted')
        self.assertEqual(metrics['composition'],revised)
        self.assertEqual(repair.call_args.args[0]['failed_elements'],['body'])
        self.assertEqual(metrics['composition']['blocks'][1],plan['blocks'][1])

    def test_three_failed_attempts_keep_safe_sibling_elements_and_use_nearby_recovery(self):
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high',palette='burgundy-oat')
        plan['blocks'][0].update(style='outlined',max_lines=1)
        repair=Mock(return_value=(plan,'reviewed'))
        with tempfile.TemporaryDirectory() as tmp:
            photo=Path(tmp)/'photo.jpg';Image.new('RGB',(1024,1024),'#728192').save(photo,'JPEG')
            path=Path(tmp)/'out.jpg';draw=lambda candidate:render_hybrid(card,plan['palette'],photo,path,candidate)
            metrics,detail=render_design(card,plan,photo,draw,model_accepted=True,repair=repair)
        self.assertEqual(repair.call_count,2);self.assertEqual(detail['status'],'partial')
        self.assertEqual(detail['element_recovery']['fallback'],['body'])
        self.assertEqual(metrics['composition']['blocks'][1],plan['blocks'][1])
        self.assertEqual(metrics['composition']['category_style'],plan['category_style'])
        self.assertEqual(metrics['composition']['blocks'][0]['style'],'outlined')
        self.assertEqual(metrics['composition']['blocks'][0]['y'],plan['blocks'][0]['y'])

    def test_service_failure_does_not_retry_and_protected_elements_cannot_be_changed(self):
        card=reviewed_fixture()['cards'][2];plan=dict(default_plan(card),confidence='high',palette='burgundy-oat')
        plan['blocks'][0]['max_lines']=1
        for available in (False,True):
            revised=copy.deepcopy(plan);revised['blocks'][0]['max_lines']=None;revised['blocks'][1]['y']-=100
            repair=Mock(return_value=(revised,'reviewed' if available else 'unavailable'))
            with tempfile.TemporaryDirectory() as tmp:
                photo=Path(tmp)/'photo.jpg';Image.new('RGB',(1024,1024),'#728192').save(photo,'JPEG')
                path=Path(tmp)/'out.jpg';draw=lambda candidate:render_hybrid(card,plan['palette'],photo,path,candidate)
                metrics,detail=render_design(card,plan,photo,draw,model_accepted=True,repair=repair)
            self.assertEqual(repair.call_count,2 if available else 1);self.assertEqual(detail['status'],'partial')
            self.assertEqual(metrics['composition']['blocks'][1],plan['blocks'][1])

if __name__=='__main__':unittest.main()
