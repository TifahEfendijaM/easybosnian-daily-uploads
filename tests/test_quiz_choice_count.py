"""Uniform answer-count target, checked binary exceptions and legacy reading."""
import copy
import unittest
from easybosnian.validate import validate
from test_project import reviewed_fixture


def candidate(count,target=None,binary=False):
    p=reviewed_fixture()
    options=p['cards'][0]['options']+[{'label':'D','text':'kaput'}]
    p['cards'][0]['options']=options[:count]
    p['private_review']['quiz_choice_review']={'target':target or count,'binary':binary,
        'reason':'Reviewed question classification and plausible distinct alternatives for this quiz.'}
    return p


class QuizChoiceCountTests(unittest.TestCase):
    def test_each_target_accepts_exact_count_and_rejects_different_counts(self):
        for target in (2,3,4):
            validate(candidate(target),quiz_option_target=target)
            for count in (2,3,4):
                if count==target:continue
                with self.subTest(target=target,count=count),self.assertRaisesRegex(ValueError,'option count'):
                    validate(candidate(count,target),quiz_option_target=target)

    def test_binary_review_requires_two_even_when_random_target_is_three_or_four(self):
        for target in (2,3,4):
            p=candidate(2,target,binary=True)
            p['cards'][0]['question']='Da li je predmet koristan za zaštitu od kiše?'
            p['cards'][0]['options']=[{'label':'A','text':'Da'},{'label':'B','text':'Ne'}]
            p['private_review'].update(correct_option='A',correct_text='Da',answer_aliases=['da'],identifying_hints=['tačan odgovor je da'])
            validate(p,quiz_option_target=target)
            p['cards'][0]['options'].append({'label':'C','text':'Možda'})
            with self.assertRaisesRegex(ValueError,'option count'):validate(p,quiz_option_target=target)

    def test_fresh_attempt_requires_matching_review_but_old_saved_content_stays_readable(self):
        p=reviewed_fixture();validate(p)
        with self.assertRaisesRegex(ValueError,'trusted random target'):validate(p,quiz_option_target=3)
        p=candidate(3)
        with self.assertRaisesRegex(ValueError,'trusted random target'):validate(p,quiz_option_target=4)
        for target in (True,1,5,'3'):
            with self.assertRaisesRegex(ValueError,'Invalid trusted quiz option target'):validate(p,quiz_option_target=target)
        for change in ({'binary':'false'},{'reason':''},{'target':5},{'extra':'untrusted'}):
            bad=copy.deepcopy(p);bad['private_review']['quiz_choice_review'].update(change)
            with self.assertRaises(ValueError):validate(bad)


if __name__=='__main__':unittest.main()
