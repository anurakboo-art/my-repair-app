"""UI workflow regression tests. Synthetic fixtures only; no production requests."""
import sys
import faulthandler
faulthandler.dump_traceback_later(30,repeat=False)
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
from streamlit.testing.v1 import AppTest
import backend
PLAN={'id':'pm1','asset_id':'asset1','assignee_id':'tech1','task':'Test PM only','due_date':'2026-10-29','completed_at':None,'frequency':'daily','result':''}

ASSET={'id':'asset1','code':'TEST-001','name':'Test machine','location':'Test area'}
MEMBERS=[{'user_id':'admin1','display_name':'Test Admin','role':'admin','active':True},
         {'user_id':'tech1','display_name':'Test Technician','role':'technician','active':True},
         {'user_id':'reporter1','display_name':'Test Reporter','role':'reporter','active':True}]
JOB={'id':'job1','number':1,'asset_id':'asset1','reporter_id':'reporter1','assignee_id':'tech1',
     'symptom':'Test motor stopped','priority':'urgent','impact':'Test impact','status':'assigned',
     'due_date':'2026-10-29','cause':'','repair':'','parts':'','labor_minutes':0,'downtime_minutes':0,
     'version':2,'created_at':'2026-10-29T00:00:00+00:00'}
calls=[]
class Storage:
    def from_(self,bucket): return self
    def list(self,path): return []
API=SimpleNamespace(storage=Storage())
current={'uid':'admin1'}
def restore(*args): return API,SimpleNamespace(id=current['uid']),{'access_token':'fake','refresh_token':'fake'}
def records(api,table,**filters):
    rows={'cmms_assets':[ASSET], 'cmms_jobs':[JOB], 'cmms_members':MEMBERS,
          'cmms_pm':[PLAN], 'cmms_events':[{'created_at':'2026-10-29T00:00:00+00:00','actor_id':'tech1','action':'start','note':'Test note'}]}[table]
    return [r for r in rows if all(r.get(k)==v for k,v in filters.items())]
def command(api,action,data):
    calls.append((action,data))
    return {'id':'job1','number':1}
def element(items,label): return next(x for x in items if x.label==label)
def ok(app): assert not app.exception, app.exception
def create(uid):
    print('Testing UI for',uid,flush=True)
    current['uid']=uid
    app=AppTest.from_file(str(Path(__file__).parent/'app.py'),default_timeout=30)
    app.session_state.tokens={'access_token':'fake','refresh_token':'fake'}
    app.run(); ok(app)
    return app
def page(app,name):
    print('Opening',name,flush=True)
    element(app.radio,'เมนู').set_value(name).run();ok(app)

with patch.object(backend,'restore',restore),patch.object(backend,'records',records),patch.object(backend,'command',command):
    app=create('admin1')
    element(app.button,'เปิดใบงาน').click().run();ok(app)
    assert app.session_state.main_page=='งานซ่อม'
    assert app.session_state.job_pick=='job1'
    element(app.text_input,'ค้นหาใบงาน').set_value('no match').run();ok(app)
    assert not any(x.label=='เลือกใบงาน' for x in app.selectbox)
    page(app,'ภาพรวม')
    element(app.button,'เปิดใบงาน').click().run();ok(app)
    assert app.session_state.job_search==''
    assert element(app.selectbox,'เลือกใบงาน').value=='job1'
    page(app,'แจ้งซ่อม')
    element(app.button,'ส่งใบแจ้งซ่อม').click().run();ok(app)
    assert not calls and app.error
    element(app.text_area,'2. อาการเสีย *').set_value('Test only')
    element(app.button,'ส่งใบแจ้งซ่อม').click().run();ok(app)
    assert calls[-1][0]=='job_create'
    assert app.session_state.main_page=='งานซ่อม' and app.session_state.job_pick=='job1'
    page(app,'ทะเบียนเครื่องจักร')
    element(app.button,'เพิ่มเครื่องจักร').click().run();ok(app)
    assert app.error and calls[-1][0]=='job_create'
    page(app,'จัดการผู้ใช้')
    element(app.selectbox,'เพิ่มหรือแก้ไขผู้ใช้').select('tech1').run();ok(app)
    assert element(app.text_input,'ชื่อแสดงผล').value=='Test Technician'
    assert not any('รหัสผู้ใช้' in x.label for x in app.text_input)
    for name in ('แผน PM','รายงาน'):
        page(app,name)
    app=create('tech1')
    assert app.session_state.main_page=='งานของฉัน'
    element(app.button,'เปิดเพื่อเริ่มซ่อม').click().run();ok(app)
    assert app.session_state.main_page=='งานซ่อม' and app.session_state.job_pick=='job1'
    assert any(b.label=='เริ่ม / กลับมาซ่อม' for b in app.button)
    assert not any(b.label=='มอบหมายช่าง' for b in app.button)
    page(app,'งานของฉัน')
    element(app.button,'PM วันนี้ / ค้าง (1)').click().run();ok(app)
    element(app.button,'เปิดเพื่อบันทึกผล PM').click().run();ok(app)
    assert app.session_state.main_page=='แผน PM' and app.session_state.pm_pick=='pm1'
    assert not calls[-1][0]=='pm_complete'
    app=create('reporter1');page(app,'งานซ่อม')
    assert not any(b.label in ('เริ่ม / กลับมาซ่อม','มอบหมายช่าง') for b in app.button)
    assert 'จัดการผู้ใช้' not in element(app.radio,'เมนู').options
print('PASS: quick navigation, search, open filtered job, form validation, create-to-detail flow, member editing, technician/reporter actions')

