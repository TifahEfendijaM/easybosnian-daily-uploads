import unittest
from unittest.mock import patch
from easybosnian.selection import quiz_format_target,check_selection
from test_project import reviewed_fixture

class QuizFormatProbabilityTests(unittest.TestCase):
 def test_exact_one_of_four_outcomes_is_picture_identification(self):
  values=[]
  for ticket in range(4):
   with patch('easybosnian.selection.randbelow',return_value=ticket) as random:
    values.append(quiz_format_target({'choice':'new'}));random.assert_called_once_with(4)
  self.assertEqual(values,['visual_identification','other','other','other'])
 def test_frozen_quiz_never_draws_and_keeps_existing_format(self):
  for fmt in ('visual_identification','other'):
   p=reviewed_fixture();p['cards'][0]['quiz_format']=fmt
   choice={'choice':'custom','word_actions':['same_image&design','chatgpt','chatgpt'],'previous':p}
   with patch('easybosnian.selection.randbelow') as random:self.assertEqual(quiz_format_target(choice),fmt)
   random.assert_not_called()
 def test_selection_checks_target_before_new_mode_shortcut(self):
  for fmt in ('visual_identification','other'):
   p=reviewed_fixture();p['cards'][0]['quiz_format']=fmt
   check_selection(p,{'choice':'new','previous':None,'quiz_format_target':fmt})
   with self.assertRaisesRegex(ValueError,'trusted random target'):
    check_selection(p,{'choice':'new','previous':None,'quiz_format_target':'other' if fmt=='visual_identification' else 'visual_identification'})
  with self.assertRaisesRegex(ValueError,'Invalid trusted quiz format'):
   check_selection(p,{'choice':'new','previous':None,'quiz_format_target':'choose_any'})
