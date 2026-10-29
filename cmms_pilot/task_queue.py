"""Role-aware presentation of records already authorized by database RLS."""
def build_queues(role, user_id, jobs, plans, today):
    today = today.isoformat() if hasattr(today, 'isoformat') else today
    active = [j for j in jobs if j['status'] not in ('closed', 'cancelled')]
    own = [j for j in active if j.get('assignee_id') == user_id]
    reported = [j for j in active if j['reporter_id'] == user_id]
    due = [p for p in plans if not p.get('completed_at') and p['due_date'] <= today]
    queues = []

    def add(key, title, job_items=(), pm_items=(), attention=True):
        queues.append({'key':key, 'title':title, 'jobs':sorted(job_items,key=lambda j:(
            {'critical':0,'urgent':1,'normal':2}.get(j['priority'],3), j.get('due_date') or '9999-12-31',j['number'])),
            'plans':sorted(pm_items,key=lambda p:(p['due_date'],p['id'])), 'attention':attention})

    if role in ('manager', 'admin'):
        add('assign', 'รอมอบหมาย', [j for j in active if j['status'] == 'new'])
        add('accept', 'รอตรวจรับ', [j for j in active if j['status'] == 'acceptance'])
        add('overdue', 'งานเกินกำหนด', [j for j in active if j.get('due_date') and j['due_date'] < today])
        add('pm', 'PM ถึงกำหนด', pm_items=due)
    elif role == 'technician':
        add('start', 'รอเริ่มซ่อม', [j for j in own if j['status'] == 'assigned'])
        add('repair', 'กำลังซ่อม', [j for j in own if j['status'] == 'repairing'])
        add('pm', 'PM วันนี้ / ค้าง', pm_items=[p for p in due if p['assignee_id'] == user_id])
        add('parts', 'รออะไหล่', [j for j in own if j['status'] == 'waiting_parts'], attention=False)
        add('accept', 'รอฉันตรวจรับ', [j for j in reported if j['status'] == 'acceptance'])
    else:
        add('accept', 'รอฉันตรวจรับ', [j for j in reported if j['status'] == 'acceptance'])
        add('tracking', 'ติดตามงานที่แจ้ง', [j for j in reported if j['status'] != 'acceptance'], attention=False)
    return queues


def queue_size(queue):
    return len(queue['jobs']) + len(queue['plans'])


def attention_count(queues):
    # An overdue job awaiting acceptance appears in both lists, but is counted once.
    identities = set()
    for queue in queues:
        if queue['attention']:
            identities.update(('job',j['id']) for j in queue['jobs'])
            identities.update(('pm',p['id']) for p in queue['plans'])
    return len(identities)

