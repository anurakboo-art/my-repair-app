"""CMMS pilot with real authentication and database-enforced access control."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from backend import client, restore, command, records, upload_photo
from task_queue import build_queues, queue_size, attention_count

st.set_page_config(page_title='CMMS • ระบบนำร่อง', page_icon='🔧', layout='wide')
st.markdown('''<style>
.block-container {max-width:1160px;padding-top:2rem;padding-bottom:3rem}
[data-testid="stForm"] {border-radius:14px}
[data-testid="stMetric"] {border:1px solid var(--secondary-background-color);border-radius:12px;padding:12px}
button[kind="primary"] {min-height:44px}
@media(max-width:640px){.block-container{padding:1.2rem 1rem 3rem} [data-testid="stHorizontalBlock"]{flex-wrap:wrap} [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{min-width:min(100%,220px)} [role="radiogroup"]{gap:6px!important}}
</style>''',unsafe_allow_html=True)
st.title('🔧 ศูนย์งานซ่อมบำรุง')

ROLES = {'reporter':'ผู้แจ้ง','technician':'ช่าง','manager':'หัวหน้าซ่อมบำรุง','admin':'ผู้ดูแลระบบ'}
STATES = {'new':'แจ้งใหม่','assigned':'มอบหมายแล้ว','repairing':'กำลังซ่อม','waiting_parts':'รออะไหล่','acceptance':'รอตรวจรับ','closed':'ปิดงาน','cancelled':'ยกเลิก'}
PRIORITY = {'normal':'ปกติ','urgent':'เร่งด่วน','critical':'วิกฤต'}
FREQUENCY = {'daily':'รายวัน','weekly':'รายสัปดาห์','monthly':'รายเดือน','yearly':'รายปี'}
TODAY = datetime.now(ZoneInfo('Asia/Bangkok')).date()


def safe_error(error):
    text = str(error)
    messages = {'CMMS_STALE_VERSION':'ข้อมูลถูกแก้ไขโดยผู้ใช้อื่นแล้ว กรุณากดโหลดข้อมูลใหม่',
                'CMMS_NOTE_REQUIRED':'กรุณาระบุผลทดสอบหรือเหตุผล',
                'CMMS_REPAIR_REQUIRED':'ระบุสาเหตุและวิธีซ่อมก่อนส่งตรวจรับ',
                'CMMS_PARTS_REQUIRED':'กรุณาระบุอะไหล่ที่รอ',
                'CMMS_KEEP_OWN_ADMIN':'ไม่สามารถลดสิทธิ์หรือระงับบัญชีผู้ดูแลที่กำลังใช้งานได้',
                'CMMS_INVALID_TECHNICIAN':'ต้องเลือกบัญชีช่างที่ยังเปิดใช้งาน',
                'CMMS_ACCESS_DENIED':'ไม่มีสิทธิ์ดำเนินการ หรือสถานะงานเปลี่ยนแล้ว',
                '23505':'มีรหัสซ้ำ กรุณาตรวจสอบ', '23503':'ไม่พบข้อมูลอ้างอิง กรุณาตรวจสอบรหัสผู้ใช้หรือเครื่องจักร'}
    st.error(next((msg for code,msg in messages.items() if code in text), 'ดำเนินการไม่สำเร็จ กรุณาตรวจข้อมูลหรือการเชื่อมต่อแล้วลองใหม่'))


def mutate(action, data):
    try:
        result = command(api, action, data)
        st.session_state.notice = 'บันทึกสำเร็จ'
        if action == 'job_create':
            st.session_state.notice = f"สร้างใบงาน WO-{result['number']:05d} สำเร็จ เพิ่มรูปและติดตามงานได้ด้านล่าง"
            go('งานซ่อม',result['id'])
        st.rerun()
    except Exception as error:
        safe_error(error)


def view(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    else:
        st.info('ยังไม่มีรายการที่คุณเข้าถึงได้')


def go(page, job_id=None):
    st.session_state.pending_page = page
    if job_id:
        st.session_state.pending_job = job_id


def go_queue(key):
    go('งานของฉัน')
    st.session_state.work_queue = key


def go_pm(plan_id):
    go('แผน PM')
    st.session_state.pending_pm = plan_id


def thai_date(value):
    if not value:
        return 'ยังไม่กำหนด'
    return datetime.fromisoformat(value.replace('Z','+00:00')).strftime('%d/%m/%Y')


config = json.loads((Path(__file__).parent / 'public_config.json').read_text(encoding='utf-8-sig'))
url, key = config['url'], config['publishable_key']
if not st.session_state.get('tokens'):
    st.caption('แจ้งซ่อม ติดตามงาน และวางแผนดูแลเครื่องจักรในที่เดียว')
    login, signup = st.tabs(['เข้าสู่ระบบ','สมัครบัญชี'])
    with login:
        with st.form('login', clear_on_submit=True):
            email = st.text_input('อีเมล', max_chars=254)
            password = st.text_input('รหัสผ่าน', type='password')
            submit = st.form_submit_button('เข้าสู่ระบบ',type='primary',width='stretch')
        if submit:
            try:
                response = client(url,key).auth.sign_in_with_password({'email':email.strip(),'password':password})
                st.session_state.tokens = {'access_token':response.session.access_token,'refresh_token':response.session.refresh_token}
                st.rerun()
            except Exception:
                st.error('เข้าสู่ระบบไม่สำเร็จ ตรวจอีเมล รหัสผ่าน และการยืนยันอีเมล')
    with signup:
        st.caption('สมัครและยืนยันอีเมลก่อน จากนั้นรอผู้ดูแลอนุมัติสิทธิ์ ไม่มีการเลือกบทบาทด้วยตนเอง')
        with st.form('signup',clear_on_submit=True):
            new_email = st.text_input('อีเมลสำหรับสมัคร', max_chars=254)
            new_password = st.text_input('ตั้งรหัสผ่าน',type='password',help='อย่างน้อย 12 ตัวอักษร')
            confirmation = st.text_input('ยืนยันรหัสผ่าน',type='password')
            register = st.form_submit_button('สมัครบัญชี',type='primary',width='stretch')
        if register:
            if len(new_password)<12 or new_password != confirmation:
                st.error('ใช้รหัสผ่านอย่างน้อย 12 ตัว และยืนยันให้ตรงกัน')
            else:
                try:
                    client(url,key).auth.sign_up({'email':new_email.strip(),'password':new_password})
                    st.success('หากอีเมลนี้สมัครได้ ระบบจะส่งขั้นตอนยืนยันไปยังอีเมล กรุณาตรวจกล่องข้อความ')
                except Exception:
                    st.error('สมัครไม่สำเร็จ กรุณาลองอีกครั้งภายหลัง')
    st.stop()

try:
    api, user, tokens = restore(url,key,st.session_state.tokens)
    st.session_state.tokens = tokens
except Exception:
    st.session_state.clear()
    st.warning('เซสชันหมดอายุ กรุณาเข้าสู่ระบบอีกครั้ง')
    st.stop()

if st.sidebar.button('ออกจากระบบ'):
    try:
        api.auth.sign_out({'scope':'local'})
    finally:
        st.session_state.clear()
    st.rerun()
try:
    own = records(api,'cmms_members',user_id=user.id)
except Exception as error:
    safe_error(error)
    st.stop()
if not own or not own[0]['active']:
    st.info('บัญชีนี้ยังไม่ได้รับอนุมัติ กรุณาแจ้งรหัสผู้ใช้ด้านล่างให้ผู้ดูแล')
    st.code(user.id)
    st.stop()
member = own[0]
role = member['role']
manager = role in ('manager','admin')
st.sidebar.write(f"**{member['display_name']}** · {ROLES[role]}")
st.caption(f"{member['display_name']} · {ROLES[role]}  |  {TODAY.strftime('%d/%m/%Y')}")
pages = ['งานของฉัน','ภาพรวม','แจ้งซ่อม','งานซ่อม','ทะเบียนเครื่องจักร','แผน PM','รายงาน']
if role == 'admin':
    pages.append('จัดการผู้ใช้')
if 'pending_page' in st.session_state:
    st.session_state.main_page = st.session_state.pop('pending_page')
if 'main_page' not in st.session_state:
    st.session_state.main_page = 'งานของฉัน' if role == 'technician' else 'ภาพรวม'
page = st.radio('เมนู',pages,horizontal=True,key='main_page',label_visibility='collapsed')
st.divider()
if st.sidebar.button('โหลดข้อมูลใหม่'):
    st.rerun()
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))

try:
    assets = records(api,'cmms_assets')
    jobs = records(api,'cmms_jobs')
    members = records(api,'cmms_members')
    plans = records(api,'cmms_pm')
except Exception as error:
    safe_error(error)
    st.stop()
asset_map = {a['id']:a for a in assets}
techs = {m['user_id']:m['display_name'] for m in members if m['active'] and m['role']=='technician'}
people = {m['user_id']:m['display_name'] for m in members}
asset_label = lambda uid: f"{asset_map[uid]['code']} · {asset_map[uid]['name']}"
queues = build_queues(role,user.id,jobs,plans,TODAY)

def job_rows(items):
    return [{'เลขที่':f"WO-{j['number']:05d}",'เครื่องจักร':asset_label(j['asset_id']), 'อาการ':j['symptom'], 'สถานะ':STATES[j['status']], 'ความเร่งด่วน':PRIORITY[j['priority']], 'กำหนดเสร็จ':j['due_date'], 'เวลาซ่อม (นาที)':j['labor_minutes'], 'เครื่องหยุด (นาที)':j['downtime_minutes']} for j in items]

def queue_buttons(prefix):
    columns = st.columns(min(3,len(queues)))
    for index,queue in enumerate(queues):
        columns[index % len(columns)].button(
            f"{queue['title']} ({queue_size(queue)})",key=f"{prefix}_{queue['key']}",
            type='primary' if page == 'งานของฉัน' and st.session_state.get('work_queue') == queue['key'] else 'secondary',
            width='stretch',on_click=go_queue,args=(queue['key'],))


if page == 'งานของฉัน':
    st.subheader('งานของฉัน')
    st.caption('เลือกกลุ่มงาน แล้วเปิดรายการเพื่อดำเนินการต่อ จำนวนคำนวณจากงานที่คุณมีสิทธิ์ดู')
    st.metric('รอฉันทำ',attention_count(queues))
    if st.session_state.get('work_queue') not in {q['key'] for q in queues}:
        st.session_state.work_queue = next((q['key'] for q in queues if queue_size(q)),queues[0]['key'])
    queue_buttons('mine')
    selected_queue = next(q for q in queues if q['key']==st.session_state.work_queue)
    st.markdown(f"### {selected_queue['title']}")
    if not queue_size(selected_queue):
        st.success('ไม่มีรายการในกลุ่มนี้')
    for job in selected_queue['jobs']:
        with st.container(border=True):
            st.markdown(f"**WO-{job['number']:05d} · {asset_label(job['asset_id'])}**")
            st.write(job['symptom'])
            overdue = bool(job['due_date'] and job['due_date'] < TODAY.isoformat())
            st.caption(f"{PRIORITY[job['priority']]} · {STATES[job['status']]} · กำหนด {thai_date(job['due_date'])}" + (' · เกินกำหนด' if overdue else ''))
            action_labels = {'new':'เปิดเพื่อมอบหมาย','assigned':'เปิดเพื่อเริ่มซ่อม','repairing':'เปิดเพื่อบันทึกผลซ่อม','waiting_parts':'เปิดเพื่อติดตามอะไหล่','acceptance':'เปิดเพื่อตรวจรับ'}
            if job['status']=='acceptance' and (manager or job['reporter_id']==user.id):
                label = 'เปิดเพื่อตรวจรับ'
            elif manager and job['status'] in ('new','assigned'):
                label = 'เปิดเพื่อมอบหมาย'
            elif role=='technician' and job['assignee_id']==user.id:
                label = action_labels.get(job['status'],'ติดตามใบงาน')
            else:
                label = 'ติดตามใบงาน'
            st.button(label,key=f"task_{job['id']}",width='stretch',on_click=go,args=('งานซ่อม',job['id']))
    for plan in selected_queue['plans']:
        with st.container(border=True):
            st.markdown(f"**PM · {asset_label(plan['asset_id'])}**")
            st.write(plan['task'])
            st.caption(f"กำหนด {thai_date(plan['due_date'])} · {people.get(plan['assignee_id'],'ช่างผู้รับผิดชอบ')}" + (' · เกินกำหนด' if plan['due_date'] < TODAY.isoformat() else ' · วันนี้'))
            st.button('เปิดเพื่อบันทึกผล PM' if role=='technician' and plan['assignee_id']==user.id else 'ติดตามแผน PM',key=f"task_pm_{plan['id']}",width='stretch',on_click=go_pm,args=(plan['id'],))
    st.divider()
    st.button('＋ แจ้งซ่อมใหม่',on_click=go,args=('แจ้งซ่อม',))

elif page == 'ภาพรวม':
    st.subheader('วันนี้ต้องดูแลอะไรบ้าง')
    st.markdown(f"**รอฉันทำ {attention_count(queues)} รายการ**")
    queue_buttons('overview')
    active = [j for j in jobs if j['status'] not in ('closed','cancelled')]
    cols = st.columns(3)
    cols[0].metric('งานเปิดที่คุณเข้าถึงได้',len(active))
    cols[1].metric('งานเร่งด่วน / วิกฤต',sum(j['priority']!='normal' for j in active))
    cols[2].metric('PM ถึงกำหนด',sum(p['due_date']<=TODAY.isoformat() and not p['completed_at'] for p in plans))
    quick = st.columns(3)
    quick[0].button('＋ แจ้งซ่อม',type='primary',width='stretch',on_click=go,args=('แจ้งซ่อม',))
    quick[1].button('ดูงานซ่อม',width='stretch',on_click=go,args=('งานซ่อม',))
    quick[2].button('ดูแผน PM',width='stretch',on_click=go,args=('แผน PM',))
    if not assets:
        with st.container(border=True):
            st.markdown('### เริ่มต้นใช้งาน')
            st.write('1. เพิ่มเครื่องจักร → 2. เพิ่มบัญชีช่าง → 3. ทดลองแจ้งซ่อม')
            if manager:
                st.button('เพิ่มเครื่องจักรเครื่องแรก',on_click=go,args=('ทะเบียนเครื่องจักร',))
    elif active:
        st.markdown('### งานที่ต้องติดตาม')
        for job in sorted(active,key=lambda j:(j['priority']=='normal',j['due_date'] or '9999',-j['number']))[:6]:
            with st.container(border=True):
                st.markdown(f"**WO-{job['number']:05d} · {asset_label(job['asset_id'])}**")
                st.write(job['symptom'])
                st.caption(f"{STATES[job['status']]} · {PRIORITY[job['priority']]} · กำหนด {thai_date(job['due_date'])}")
                st.button('เปิดใบงาน',key=f"open_{job['id']}",on_click=go,args=('งานซ่อม',job['id']))
    else:
        st.success('ไม่มีงานซ่อมค้างในรายการที่คุณดูแล')

elif page == 'แจ้งซ่อม':
    st.subheader('แจ้งซ่อมใหม่')
    st.caption('เลือกเครื่องจักรและบอกอาการเสีย จากนั้นติดตามงานได้ทันที')
    if not assets:
        st.info('ให้หัวหน้าเพิ่มเครื่องจักรในทะเบียนก่อน')
    else:
        with st.form('create_job',clear_on_submit=True):
            asset = st.selectbox('1. เครื่องจักรที่ต้องการแจ้งซ่อม',list(asset_map),format_func=asset_label)
            symptom = st.text_area('2. อาการเสีย *',max_chars=5000,placeholder='เช่น เปิดเครื่องแล้วมอเตอร์ไม่หมุน หรือมีเสียงผิดปกติ')
            cols = st.columns(2)
            priority = cols[0].selectbox('3. ความเร่งด่วน',list(PRIORITY),format_func=PRIORITY.get)
            impact = cols[1].selectbox('ผลกระทบต่อการทำงาน',['ยังใช้งานได้','กระทบการผลิต','เครื่องหยุด'])
            if st.form_submit_button('ส่งใบแจ้งซ่อม',type='primary',width='stretch'):
                if symptom.strip():
                    mutate('job_create',{'asset_id':asset,'symptom':symptom.strip(),'priority':priority,'impact':impact})
                else:
                    st.error('กรุณาระบุอาการเสีย')
        st.caption('เพิ่มรูปประกอบหลังสร้างใบงาน ในเมนูงานซ่อม')

elif page == 'งานซ่อม':
    st.subheader('ติดตามงานซ่อม')
    if 'pending_job' in st.session_state:
        st.session_state.job_pick = st.session_state.pop('pending_job')
        st.session_state.job_search = ''
        st.session_state.job_filter = 'all'
    cols = st.columns([2,1])
    search = cols[0].text_input('ค้นหาใบงาน',key='job_search',placeholder='เลขใบงาน รหัสเครื่อง หรืออาการเสีย')
    filter_status = cols[1].selectbox('สถานะ',['all']+list(STATES),key='job_filter',format_func=lambda s:'ทั้งหมด' if s=='all' else STATES[s])
    visible = sorted([j for j in jobs if (filter_status=='all' or j['status']==filter_status) and (not search.strip() or search.strip().casefold() in f"WO-{j['number']:05d} {asset_label(j['asset_id'])} {j['symptom']}".casefold())],key=lambda j:j['number'],reverse=True)
    st.caption(f'พบ {len(visible)} ใบงาน')
    if visible:
        options = {j['id']:j for j in visible}
        if st.session_state.get('job_pick') not in options:
            st.session_state.job_pick = next(iter(options))
        selected = st.selectbox('เลือกใบงาน',list(options),key='job_pick',format_func=lambda uid:f"WO-{options[uid]['number']:05d} · {asset_label(options[uid]['asset_id'])}")
        j = options[selected]
        data = {'id':j['id'],'version':j['version']}
        with st.container(border=True):
            st.markdown(f"### WO-{j['number']:05d} · {STATES[j['status']]}")
            st.write(f"**{asset_label(j['asset_id'])}**")
            st.write(j['symptom'])
            st.caption(f"{PRIORITY[j['priority']]} · {j['impact']} · กำหนด {thai_date(j['due_date'])}")
            st.write(f"ผู้รับผิดชอบ: {people.get(j['assignee_id'],'ยังไม่มอบหมาย' if not j['assignee_id'] else 'ช่างผู้รับผิดชอบ')}")
        guidance = {'new':'ขั้นต่อไป: หัวหน้ามอบหมายช่าง','assigned':'ขั้นต่อไป: ช่างผู้รับผิดชอบกดเริ่มซ่อม','repairing':'ขั้นต่อไป: บันทึกผลซ่อม แล้วส่งตรวจรับ','waiting_parts':'รออะไหล่พร้อม แล้วช่างกดกลับมาซ่อม','acceptance':'ขั้นต่อไป: ผู้แจ้งหรือหัวหน้าตรวจรับผลซ่อม','closed':'งานนี้ตรวจรับและปิดเรียบร้อยแล้ว','cancelled':'ใบงานนี้ยกเลิกแล้ว ดูเหตุผลในประวัติ'}
        st.info(guidance[j['status']])
        if j['cause'] or j['repair']:
            with st.expander('สรุปผลการซ่อม',expanded=j['status'] in ('acceptance','closed')):
                st.write('**สาเหตุ:**',j['cause'] or 'ยังไม่ได้บันทึก')
                st.write('**วิธีซ่อม:**',j['repair'] or 'ยังไม่ได้บันทึก')
                st.write('**อะไหล่:**',j['parts'] or 'ไม่มีรายการ')
                st.caption(f"เวลาซ่อม {j['labor_minutes']} นาที · เครื่องหยุด {j['downtime_minutes']} นาที")
        if manager and j['status'] in ('new','assigned'):
            if techs:
                st.markdown('### มอบหมายงานให้ช่าง')
                with st.form('assign'):
                    tech = st.selectbox('ช่างผู้รับผิดชอบ',list(techs),format_func=techs.get)
                    due = st.date_input('กำหนดเสร็จ',min_value=TODAY)
                    priority = st.selectbox('ยืนยันความเร่งด่วน',list(PRIORITY),index=list(PRIORITY).index(j['priority']),format_func=PRIORITY.get)
                    if st.form_submit_button('มอบหมายช่าง',type='primary',width='stretch'):
                        mutate('assign',{**data,'assignee_id':tech,'due_date':due.isoformat(),'priority':priority})
            else:
                st.info('ให้ผู้ดูแลเพิ่มบัญชีช่างก่อนมอบหมาย')
        repairer = role=='technician' and j['assignee_id']==user.id
        if repairer and j['status'] in ('assigned','waiting_parts'):
            if st.button('เริ่ม / กลับมาซ่อม',type='primary',width='stretch'):
                mutate('start',data)
        if repairer and j['status']=='repairing':
            st.markdown('### บันทึกผลซ่อม')
            with st.form('repair'):
                cause = st.text_area('สาเหตุ',value=j['cause'])
                fix = st.text_area('วิธีซ่อม',value=j['repair'])
                parts = st.text_input('อะไหล่ที่ใช้ / รอ',value=j['parts'])
                labor = st.number_input('เวลาซ่อมรวม (นาที)',min_value=0,value=j['labor_minutes'],step=1)
                downtime = st.number_input('เครื่องหยุดรวม (นาที)',min_value=0,value=j['downtime_minutes'],step=1)
                action = st.selectbox('การดำเนินการ',['progress','wait_parts','submit'],format_func={'progress':'บันทึกความคืบหน้า','wait_parts':'รออะไหล่','submit':'ส่งตรวจรับ'}.get)
                if st.form_submit_button('บันทึกงานช่าง',type='primary',width='stretch'):
                    mutate(action,{**data,'cause':cause,'repair':fix,'parts':parts,'labor_minutes':labor,'downtime_minutes':downtime})
        if j['status']=='acceptance' and (j['reporter_id']==user.id or manager):
            st.markdown('### ตรวจรับงานซ่อม')
            with st.form('accept'):
                result = st.selectbox('ผลตรวจรับ',['accept','reject'],format_func={'accept':'ผ่าน','reject':'ไม่ผ่าน'}.get)
                note = st.text_area('ผลทดสอบ / เหตุผล *')
                if st.form_submit_button('ยืนยันผลตรวจรับ',type='primary',width='stretch'):
                    mutate(result,{**data,'note':note})
        if manager and j['status'] not in ('closed','cancelled'):
            with st.expander('ยกเลิกใบงาน'):
                with st.form('cancel'):
                    reason = st.text_input('เหตุผลยกเลิก')
                    if st.form_submit_button('ยืนยันยกเลิก'):
                        mutate('cancel',{**data,'note':reason})
        with st.expander('รูปประกอบ'):
            try:
                photos = api.storage.from_('cmms-photos').list(j['id'])
                for photo in photos:
                    if photo.get('id'):
                        st.image(api.storage.from_('cmms-photos').download(f"{j['id']}/{photo['name']}"),width=360)
                if user.id in (j['reporter_id'],j['assignee_id']) and j['status'] not in ('closed','cancelled'):
                    with st.form('photo',clear_on_submit=True):
                        photo = st.file_uploader('รูป JPEG / PNG ไม่เกิน 5 MB',type=['jpg','jpeg','png'])
                        if st.form_submit_button('บันทึกรูป') and photo:
                            try:
                                upload_photo(api,j['id'],photo)
                                st.session_state.notice='บันทึกรูปสำเร็จ'
                                st.rerun()
                            except Exception as error:
                                safe_error(error)
            except Exception as error:
                safe_error(error)
        st.subheader('ประวัติการดำเนินการ')
        try:
            actions = {**STATES,'assign':'มอบหมายช่าง','start':'เริ่มซ่อม','progress':'บันทึกความคืบหน้า','wait_parts':'รออะไหล่','submit':'ส่งตรวจรับ','accept':'ตรวจรับผ่าน','reject':'ส่งกลับแก้ไข','cancel':'ยกเลิก'}
            events = records(api,'cmms_events',job_id=j['id'])
            view([{'วันเวลา':datetime.fromisoformat(e['created_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Bangkok')).strftime('%d/%m/%Y %H:%M'),'ผู้ดำเนินการ':people.get(e['actor_id'],'ผู้ใช้งาน'),'การดำเนินการ':actions.get(e['action'],e['action']),'หมายเหตุ':e['note']} for e in events])
        except Exception as error:
            safe_error(error)
    else:
        st.info('ไม่มีใบงานในรายการนี้')

elif page == 'ทะเบียนเครื่องจักร':
    st.subheader('ทะเบียนเครื่องจักร')
    st.caption('ค้นหาเครื่องจักร ดูประวัติ และเพิ่มเครื่องจักรใหม่')
    find_asset = st.text_input('ค้นหาเครื่องจักร',placeholder='รหัส ชื่อ หรือตำแหน่ง')
    view([{'รหัส':a['code'],'ชื่อ':a['name'],'ตำแหน่ง':a['location']} for a in assets if find_asset.casefold() in f"{a['code']} {a['name']} {a['location']}".casefold()])
    if assets:
        asset = st.selectbox('ประวัติเครื่อง',list(asset_map),format_func=asset_label)
        view(job_rows([j for j in jobs if j['asset_id']==asset]))
    if manager:
        st.markdown('### เพิ่มเครื่องจักรใหม่')
        with st.form('asset',clear_on_submit=True):
            code = st.text_input('รหัสเครื่องจักร *',max_chars=60)
            name = st.text_input('ชื่อเครื่องจักร *',max_chars=200)
            location = st.text_input('ตำแหน่ง')
            if st.form_submit_button('เพิ่มเครื่องจักร',type='primary',width='stretch'):
                if code.strip() and name.strip():
                    mutate('asset_create',{'code':code,'name':name,'location':location})
                else:
                    st.error('กรุณากรอกรหัสและชื่อเครื่องจักร')

elif page == 'แผน PM':
    st.subheader('แผนตรวจบำรุง PM')
    if plans:
        st.markdown('### รายการตรวจที่วางแผนไว้')
    view([{'เครื่องจักร':asset_label(p['asset_id']),'รายการตรวจ':p['task'],'ผู้รับผิดชอบ':people.get(p['assignee_id'],'ช่างผู้รับผิดชอบ'),'กำหนด':thai_date(p['due_date']),'รอบ':FREQUENCY[p['frequency']],'สถานะ':'เสร็จแล้ว' if p['completed_at'] else ('ถึงกำหนด' if p['due_date']<=TODAY.isoformat() else 'รอดำเนินการ'),'ผลตรวจ':p['result']} for p in plans])
    if manager and assets and techs:
        st.markdown('### เพิ่มรายการตรวจใหม่')
        with st.form('pm_create',clear_on_submit=True):
            asset = st.selectbox('เครื่องจักร',list(asset_map),format_func=asset_label)
            task = st.text_input('รายการตรวจ *',max_chars=2000)
            tech = st.selectbox('ช่างผู้รับผิดชอบ',list(techs),format_func=techs.get)
            due = st.date_input('กำหนดตรวจ')
            frequency = st.selectbox('รอบตรวจ',list(FREQUENCY),format_func=FREQUENCY.get)
            if st.form_submit_button('เพิ่มแผน PM',type='primary',width='stretch'):
                if task.strip():
                    mutate('pm_create',{'asset_id':asset,'task':task,'assignee_id':tech,'due_date':due.isoformat(),'frequency':frequency})
                else:
                    st.error('กรุณาระบุรายการตรวจ')
    elif manager:
        st.info('เพิ่มเครื่องจักรและบัญชีช่างก่อนสร้างแผน PM')
    pending = [p for p in plans if p['assignee_id']==user.id and not p['completed_at']]
    if role=='technician' and pending:
        pm_options = {p['id']:p for p in pending}
        if 'pending_pm' in st.session_state:
            st.session_state.pm_pick = st.session_state.pop('pending_pm')
        if st.session_state.get('pm_pick') not in pm_options:
            st.session_state.pm_pick = next(iter(pm_options))
        pm_id = st.selectbox('บันทึกผล',list(pm_options),key='pm_pick',format_func=lambda uid:f"{asset_label(pm_options[uid]['asset_id'])} · {pm_options[uid]['task']}")
        p = pm_options[pm_id]
        with st.form('pm_complete'):
            note = st.text_area('ผลตรวจ *')
            if st.form_submit_button('ยืนยันตรวจเสร็จ',type='primary',width='stretch'):
                mutate('pm_complete',{'id':p['id'],'note':note})
    st.caption('กำหนดวันตรวจแต่ละรายการเอง ยังไม่สร้างรอบถัดไปอัตโนมัติ')

elif page == 'จัดการผู้ใช้':
    st.subheader('ผู้ใช้และสิทธิ์การทำงาน')
    view([{'ชื่อ':m['display_name'],'สิทธิ์':ROLES[m['role']],'สถานะ':'เปิดใช้งาน' if m['active'] else 'ระงับใช้งาน'} for m in members])
    choices = ['new']+list(people)
    selected_member = st.selectbox('เพิ่มหรือแก้ไขผู้ใช้',choices,format_func=lambda uid:'＋ อนุมัติผู้ใช้ใหม่' if uid=='new' else people[uid])
    existing = next((m for m in members if m['user_id']==selected_member),None)
    st.caption('ผู้ใช้ใหม่: สมัครและยืนยันอีเมล แล้วส่งรหัสที่หน้ารออนุมัติให้ผู้ดูแล')
    with st.form(f'member_{selected_member}'):
        uid = existing['user_id'] if existing else st.text_input('รหัสผู้ใช้จากหน้ารออนุมัติ')
        display_name = st.text_input('ชื่อแสดงผล',value=existing['display_name'] if existing else '')
        new_role = st.selectbox('สิทธิ์',list(ROLES),index=list(ROLES).index(existing['role']) if existing else 0,format_func=ROLES.get)
        enabled = st.checkbox('เปิดใช้งาน',value=existing['active'] if existing else True)
        if st.form_submit_button('บันทึกสิทธิ์',type='primary',width='stretch'):
            mutate('member_save',{'user_id':uid.strip(),'display_name':display_name,'role':new_role,'active':enabled})
else:
    st.subheader('รายงานงานซ่อม')
    rows = job_rows(jobs)
    view(rows)
    if rows:
        st.download_button('ดาวน์โหลด CSV',pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'),'cmms-report.csv','text/csv')

