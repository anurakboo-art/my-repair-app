"""CMMS pilot with real authentication and database-enforced access control."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from backend import client, restore, command, records, upload_photo

st.set_page_config(page_title='CMMS • ระบบนำร่อง', page_icon='🔧', layout='wide')
st.title('🔧 ระบบซ่อมบำรุง CMMS')
st.caption('ระบบนำร่อง • บัญชีผู้ใช้จริง • ข้อมูลบันทึกถาวร')

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
        st.rerun()
    except Exception as error:
        safe_error(error)


def view(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
    else:
        st.info('ยังไม่มีรายการที่คุณเข้าถึงได้')


config = json.loads((Path(__file__).parent / 'public_config.json').read_text(encoding='utf-8-sig'))
url, key = config['url'], config['publishable_key']
if not st.session_state.get('tokens'):
    login, signup = st.tabs(['เข้าสู่ระบบ','สมัครบัญชี'])
    with login:
        with st.form('login', clear_on_submit=True):
            email = st.text_input('อีเมล', max_chars=254)
            password = st.text_input('รหัสผ่าน', type='password')
            submit = st.form_submit_button('เข้าสู่ระบบ')
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
            new_password = st.text_input('ตั้งรหัสผ่าน',type='password')
            confirmation = st.text_input('ยืนยันรหัสผ่าน',type='password')
            register = st.form_submit_button('สมัครบัญชี')
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
pages = ['ภาพรวม','แจ้งซ่อม','งานซ่อม','ทะเบียนเครื่องจักร','แผน PM','รายงาน']
if role == 'admin':
    pages.append('จัดการผู้ใช้')
page = st.sidebar.radio('เมนู', pages)
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
asset_label = lambda uid: f"{asset_map[uid]['code']} · {asset_map[uid]['name']}"

def job_rows(items):
    return [{'เลขที่':f"WO-{j['number']:05d}",'เครื่องจักร':asset_label(j['asset_id']), 'อาการ':j['symptom'], 'สถานะ':STATES[j['status']], 'ความเร่งด่วน':PRIORITY[j['priority']], 'กำหนดเสร็จ':j['due_date'], 'เวลาซ่อม (นาที)':j['labor_minutes'], 'เครื่องหยุด (นาที)':j['downtime_minutes']} for j in items]

if page == 'ภาพรวม':
    active = [j for j in jobs if j['status'] not in ('closed','cancelled')]
    cols = st.columns(3)
    cols[0].metric('งานเปิดที่คุณเข้าถึงได้',len(active))
    cols[1].metric('งานเร่งด่วน / วิกฤต',sum(j['priority']!='normal' for j in active))
    cols[2].metric('PM ถึงกำหนด',sum(p['due_date']<=TODAY.isoformat() and not p['completed_at'] for p in plans))
    view(job_rows(active))

elif page == 'แจ้งซ่อม':
    if not assets:
        st.info('ให้หัวหน้าเพิ่มเครื่องจักรในทะเบียนก่อน')
    else:
        with st.form('create_job',clear_on_submit=True):
            asset = st.selectbox('เครื่องจักร',list(asset_map),format_func=asset_label)
            symptom = st.text_area('อาการเสีย *',max_chars=5000)
            priority = st.selectbox('ความเร่งด่วน',list(PRIORITY),format_func=PRIORITY.get)
            impact = st.selectbox('ผลกระทบ',['ยังใช้งานได้','กระทบการผลิต','เครื่องหยุด'])
            if st.form_submit_button('ส่งใบแจ้งซ่อม'):
                if symptom.strip():
                    mutate('job_create',{'asset_id':asset,'symptom':symptom.strip(),'priority':priority,'impact':impact})
                else:
                    st.error('กรุณาระบุอาการเสีย')
        st.caption('เพิ่มรูปประกอบหลังสร้างใบงาน ในเมนูงานซ่อม')

elif page == 'งานซ่อม':
    filter_status = st.selectbox('สถานะ',['all']+list(STATES),format_func=lambda s:'ทั้งหมด' if s=='all' else STATES[s])
    visible = sorted([j for j in jobs if filter_status=='all' or j['status']==filter_status],key=lambda j:j['number'],reverse=True)
    if visible:
        selected = st.selectbox('เลือกใบงาน',visible,format_func=lambda j:f"WO-{j['number']:05d} · {asset_label(j['asset_id'])}")
        j = selected
        data = {'id':j['id'],'version':j['version']}
        st.write(f"**{STATES[j['status']]}** · {j['symptom']}")
        view(job_rows([j]))
        if manager and j['status'] in ('new','assigned'):
            if techs:
                with st.form('assign'):
                    tech = st.selectbox('ช่างผู้รับผิดชอบ',list(techs),format_func=techs.get)
                    due = st.date_input('กำหนดเสร็จ',min_value=TODAY)
                    priority = st.selectbox('ยืนยันความเร่งด่วน',list(PRIORITY),index=list(PRIORITY).index(j['priority']),format_func=PRIORITY.get)
                    if st.form_submit_button('มอบหมายช่าง'):
                        mutate('assign',{**data,'assignee_id':tech,'due_date':due.isoformat(),'priority':priority})
            else:
                st.info('ให้ผู้ดูแลเพิ่มบัญชีช่างก่อนมอบหมาย')
        repairer = role=='technician' and j['assignee_id']==user.id
        if repairer and j['status'] in ('assigned','waiting_parts'):
            if st.button('เริ่ม / กลับมาซ่อม'):
                mutate('start',data)
        if repairer and j['status']=='repairing':
            with st.form('repair'):
                cause = st.text_area('สาเหตุ',value=j['cause'])
                fix = st.text_area('วิธีซ่อม',value=j['repair'])
                parts = st.text_input('อะไหล่ที่ใช้ / รอ',value=j['parts'])
                labor = st.number_input('เวลาซ่อมรวม (นาที)',min_value=0,value=j['labor_minutes'],step=1)
                downtime = st.number_input('เครื่องหยุดรวม (นาที)',min_value=0,value=j['downtime_minutes'],step=1)
                action = st.selectbox('การดำเนินการ',['progress','wait_parts','submit'],format_func={'progress':'บันทึกความคืบหน้า','wait_parts':'รออะไหล่','submit':'ส่งตรวจรับ'}.get)
                if st.form_submit_button('บันทึกงานช่าง'):
                    mutate(action,{**data,'cause':cause,'repair':fix,'parts':parts,'labor_minutes':labor,'downtime_minutes':downtime})
        if j['status']=='acceptance' and (j['reporter_id']==user.id or manager):
            with st.form('accept'):
                result = st.selectbox('ผลตรวจรับ',['accept','reject'],format_func={'accept':'ผ่าน','reject':'ไม่ผ่าน'}.get)
                note = st.text_area('ผลทดสอบ / เหตุผล *')
                if st.form_submit_button('ยืนยันผลตรวจรับ'):
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
            view(records(api,'cmms_events',job_id=j['id']))
        except Exception as error:
            safe_error(error)
    else:
        st.info('ไม่มีใบงานในรายการนี้')

elif page == 'ทะเบียนเครื่องจักร':
    view([{'รหัส':a['code'],'ชื่อ':a['name'],'ตำแหน่ง':a['location']} for a in assets])
    if assets:
        asset = st.selectbox('ประวัติเครื่อง',list(asset_map),format_func=asset_label)
        view(job_rows([j for j in jobs if j['asset_id']==asset]))
    if manager:
        with st.form('asset',clear_on_submit=True):
            code = st.text_input('รหัสเครื่องจักร *',max_chars=60)
            name = st.text_input('ชื่อเครื่องจักร *',max_chars=200)
            location = st.text_input('ตำแหน่ง')
            if st.form_submit_button('เพิ่มเครื่องจักร'):
                mutate('asset_create',{'code':code,'name':name,'location':location})

elif page == 'แผน PM':
    if manager and assets and techs:
        with st.form('pm_create',clear_on_submit=True):
            asset = st.selectbox('เครื่องจักร',list(asset_map),format_func=asset_label)
            task = st.text_input('รายการตรวจ *',max_chars=2000)
            tech = st.selectbox('ช่างผู้รับผิดชอบ',list(techs),format_func=techs.get)
            due = st.date_input('กำหนดตรวจ')
            frequency = st.selectbox('รอบตรวจ',list(FREQUENCY),format_func=FREQUENCY.get)
            if st.form_submit_button('เพิ่มแผน PM'):
                mutate('pm_create',{'asset_id':asset,'task':task,'assignee_id':tech,'due_date':due.isoformat(),'frequency':frequency})
    view([{'รหัส':p['id'],'เครื่องจักร':asset_label(p['asset_id']),'รายการ':p['task'],'กำหนด':p['due_date'],'ผลตรวจ':p['result'],'เสร็จเมื่อ':p['completed_at']} for p in plans])
    pending = [p for p in plans if p['assignee_id']==user.id and not p['completed_at']]
    if role=='technician' and pending:
        p = st.selectbox('บันทึกผล',pending,format_func=lambda p:p['task'])
        with st.form('pm_complete'):
            note = st.text_area('ผลตรวจ *')
            if st.form_submit_button('ยืนยันตรวจเสร็จ'):
                mutate('pm_complete',{'id':p['id'],'note':note})
    st.caption('กำหนดวันตรวจแต่ละรายการเอง ยังไม่สร้างรอบถัดไปอัตโนมัติ')

elif page == 'จัดการผู้ใช้':
    view(members)
    st.caption('ผู้ใช้สมัครและยืนยันอีเมลก่อน แล้วส่งรหัสผู้ใช้ให้ผู้ดูแลเพื่ออนุมัติ')
    with st.form('member'):
        uid = st.text_input('รหัสผู้ใช้ (UUID)')
        display_name = st.text_input('ชื่อแสดงผล')
        new_role = st.selectbox('สิทธิ์',list(ROLES),format_func=ROLES.get)
        enabled = st.checkbox('เปิดใช้งาน',value=True)
        if st.form_submit_button('บันทึกสิทธิ์'):
            mutate('member_save',{'user_id':uid.strip(),'display_name':display_name,'role':new_role,'active':enabled})
else:
    rows = job_rows(jobs)
    view(rows)
    if rows:
        st.download_button('ดาวน์โหลด CSV',pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig'),'cmms-report.csv','text/csv')

