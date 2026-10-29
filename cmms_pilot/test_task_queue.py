import unittest
from datetime import date
from task_queue import build_queues, attention_count

TODAY=date(2026,10,29)
def job(uid,state,assignee='tech',reporter='reporter',due=None,priority='normal'):
    return {'id':uid,'number':int(uid),'status':state,'assignee_id':assignee,'reporter_id':reporter,'due_date':due,'priority':priority}
def pm(uid,assignee='tech',due='2026-10-29',done=None):
    return {'id':uid,'assignee_id':assignee,'due_date':due,'completed_at':done}
def group(queues,key): return next(q for q in queues if q['key']==key)

class QueueTests(unittest.TestCase):
    def test_technician_only_own_actionable_jobs(self):
        jobs=[job('1','assigned'),job('2','repairing'),job('3','assigned','other'),job('4','closed'),job('5','waiting_parts')]
        queues=build_queues('technician','tech',jobs,[],TODAY)
        self.assertEqual([j['id'] for j in group(queues,'start')['jobs']],['1'])
        self.assertEqual([j['id'] for j in group(queues,'parts')['jobs']],['5'])
        self.assertEqual(attention_count(queues),2)

    def test_pm_due_includes_overdue_but_not_future_other_or_completed(self):
        plans=[pm('old',due='2026-10-28'),pm('today'),pm('future',due='2026-10-30'),pm('other','other'),pm('done',done='2026-10-29')]
        queues=build_queues('technician','tech',[],plans,TODAY)
        self.assertEqual([p['id'] for p in group(queues,'pm')['plans']],['old','today'])
        self.assertEqual(attention_count(queues),2)

    def test_manager_deduplicates_overdue_acceptance_and_excludes_closed(self):
        jobs=[job('1','new'),job('2','acceptance',due='2026-10-28'),job('3','closed',due='2026-10-28')]
        queues=build_queues('manager','boss',jobs,[],TODAY)
        self.assertEqual(attention_count(queues),2)
        self.assertEqual([j['id'] for j in group(queues,'overdue')['jobs']],['2'])

    def test_reporter_own_acceptance_only_and_tracking_not_action_count(self):
        jobs=[job('1','acceptance'),job('2','acceptance',reporter='other'),job('3','new')]
        queues=build_queues('reporter','reporter',jobs,[],TODAY)
        self.assertEqual(attention_count(queues),1)
        self.assertEqual([j['id'] for j in group(queues,'tracking')['jobs']],['3'])

    def test_urgency_then_due_date_and_no_input_mutation(self):
        jobs=[job('1','assigned',priority='normal'),job('2','assigned',priority='critical',due='2026-10-30'),job('3','assigned',priority='critical',due='2026-10-28')]
        queues=build_queues('technician','tech',jobs,[],TODAY)
        self.assertEqual([j['id'] for j in group(queues,'start')['jobs']],['3','2','1'])
        self.assertEqual([j['id'] for j in jobs],['1','2','3'])

    def test_technician_can_also_be_reporter_awaiting_acceptance(self):
        queues=build_queues('technician','tech',[job('1','acceptance',reporter='tech')],[],TODAY)
        self.assertEqual(attention_count(queues),1)

    def test_empty_state(self):
        for role in ('admin','manager','technician','reporter'):
            self.assertEqual(attention_count(build_queues(role,'user',[],[],TODAY)),0)

if __name__=='__main__': unittest.main()

