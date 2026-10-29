"""Public, session-only CMMS prototype. Never connect production data here."""
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CMMS • ระบบซ่อมบำรุง", page_icon="🔧", layout="wide")


def now():
    return datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")


def initialize():
    if st.session_state.get("cmms_version") != 2:
        st.session_state.cmms_version = 2
        st.session_state.assets = [
            {"รหัส": "AC-001", "ชื่อ": "เครื่องปรับอากาศ", "ตำแหน่ง": "อาคารผลิต A"},
            {"รหัส": "CV-001", "ชื่อ": "สายพานลำเลียง", "ตำแหน่ง": "ไลน์ผลิต 2"},
            {"รหัส": "AD-001", "ชื่อ": "เครื่องทำลมแห้ง", "ตำแหน่ง": "ห้องระบบลม"},
            {"รหัส": "SB-001", "ชื่อ": "เครื่องพ่นทราย", "ตำแหน่ง": "พื้นที่เตรียมผิว"},
        ]
        st.session_state.jobs = []
        st.session_state.plans = []


def event(job, action, actor, note=""):
    job["ประวัติ"].append({"เวลา": now(), "ผู้ดำเนินการ": actor, "เหตุการณ์": action, "หมายเหตุ": note})


def table(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีรายการ")


def summary(job):
    return {k: v for k, v in job.items() if k not in ("ประวัติ", "รูปภาพ")}


initialize()
st.title("🔧 ระบบซ่อมบำรุง CMMS")
st.caption("รุ่นทดลอง 2 • ข้อมูลสมมติ • เก็บเฉพาะ session • เวลาไทย")
st.warning("ใช้ข้อมูลทดลองเท่านั้น ข้อมูลอาจหายเมื่อ session สิ้นสุด บทบาทด้านล่างเป็นการจำลอง ไม่ใช่ระบบเข้าสู่ระบบหรือการควบคุมสิทธิ์จริง")
role = st.sidebar.selectbox("จำลองบทบาท", ["ผู้แจ้ง", "ช่าง", "หัวหน้าซ่อมบำรุง", "ผู้ดูแลระบบ"])
actor = st.sidebar.selectbox("ผู้ใช้งานตัวอย่าง", ["ผู้แจ้งตัวอย่าง A", "ช่างตัวอย่าง A", "ช่างตัวอย่าง B", "หัวหน้าตัวอย่าง"])
menu = st.sidebar.radio("เมนู", ["ภาพรวม", "แจ้งซ่อม", "งานซ่อม", "ทะเบียนเครื่องจักร", "แผน PM", "รายงาน"])
st.sidebar.caption("เปลี่ยนบทบาทเพื่อทดลองแต่ละขั้นตอน ข้อมูลอยู่ใน session เดียวกัน")
assets = {a["รหัส"]: a for a in st.session_state.assets}
techs = ["ช่างตัวอย่าง A", "ช่างตัวอย่าง B"]
manager = role in ("หัวหน้าซ่อมบำรุง", "ผู้ดูแลระบบ")
jobs = st.session_state.jobs
plans = st.session_state.plans
asset_label = lambda code: f'{code} · {assets[code]["ชื่อ"]}'

if menu == "ภาพรวม":
    active = [j for j in jobs if j["สถานะ"] not in ("ปิดงาน", "ยกเลิก")]
    cols = st.columns(3)
    cols[0].metric("งานเปิด", len(active))
    cols[1].metric("งานเร่งด่วน / วิกฤต", sum(j["ความเร่งด่วน"] != "ปกติ" for j in active))
    cols[2].metric("PM ถึงกำหนด", sum(p["กำหนด"] <= datetime.now(ZoneInfo("Asia/Bangkok")).date().isoformat() and p["สถานะ"] != "เสร็จแล้ว" for p in plans))
    st.subheader("คิวงานซ่อม")
    table([summary(j) for j in active])
    st.caption("แจ้งใหม่ → มอบหมายแล้ว → กำลังซ่อม → รอตรวจรับ → ปิดงาน")

elif menu == "แจ้งซ่อม":
    st.subheader("แจ้งซ่อมเครื่องจักร")
    with st.form("new_job", clear_on_submit=True):
        machine = st.selectbox("เครื่องจักร", list(assets), format_func=asset_label)
        symptom = st.text_area("อาการเสีย *")
        impact = st.selectbox("ผลกระทบ", ["ยังใช้งานได้", "กระทบการผลิต", "เครื่องหยุด"])
        priority = st.selectbox("ความเร่งด่วน", ["ปกติ", "เร่งด่วน", "วิกฤต"])
        photos = st.file_uploader("รูปประกอบทดลอง (ไม่เกิน 5 รูป รูปละ 5 MB)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
        send = st.form_submit_button("ส่งใบแจ้งซ่อม")
    if send:
        if not symptom.strip():
            st.error("กรุณาระบุอาการเสีย")
        elif len(photos) > 5 or any(p.size > 5 * 1024 * 1024 for p in photos):
            st.error("แนบได้ไม่เกิน 5 รูป และรูปละไม่เกิน 5 MB")
        else:
            job = {"เลขที่": f"DEMO-{len(jobs)+1:04d}", "เครื่องจักร": machine,
                   "ผู้แจ้ง": actor, "แจ้งเมื่อ": now(), "อาการ": symptom.strip(),
                   "ผลกระทบ": impact, "ความเร่งด่วน": priority, "สถานะ": "แจ้งใหม่",
                   "ช่าง": "", "กำหนดเสร็จ": "", "สาเหตุ": "", "วิธีซ่อม": "",
                   "เวลาซ่อม (นาที)": 0, "เครื่องหยุด (นาที)": 0, "อะไหล่": "",
                   "รูปภาพ": [{"ชื่อ": p.name, "ข้อมูล": p.getvalue()} for p in photos], "ประวัติ": []}
            event(job, "แจ้งใหม่", actor)
            jobs.append(job)
            st.success(f'สร้าง {job["เลขที่"]} แล้ว เปิดเมนูงานซ่อมเพื่อติดตาม')

elif menu == "งานซ่อม":
    st.subheader("ติดตามและดำเนินงานซ่อม")
    scope = st.selectbox("รายการที่ต้องการดู", ["ทุกงานทดลอง", "งานที่ฉันแจ้ง", "งานที่มอบหมายให้ฉัน"])
    visible = [j for j in jobs if scope == "ทุกงานทดลอง" or (scope == "งานที่ฉันแจ้ง" and j["ผู้แจ้ง"] == actor) or (scope == "งานที่มอบหมายให้ฉัน" and j["ช่าง"] == actor)]
    state_filter = st.selectbox("สถานะ", ["ทั้งหมด", "แจ้งใหม่", "มอบหมายแล้ว", "กำลังซ่อม", "รออะไหล่", "รอตรวจรับ", "ปิดงาน", "ยกเลิก"])
    visible = [j for j in visible if state_filter == "ทั้งหมด" or j["สถานะ"] == state_filter]
    if not visible:
        st.info("ไม่มีงานในรายการนี้ เริ่มจากเมนูแจ้งซ่อม")
    else:
        selected = st.selectbox("เลือกใบงาน", [j["เลขที่"] for j in visible])
        job = next(j for j in visible if j["เลขที่"] == selected)
        st.write(f'**{asset_label(job["เครื่องจักร"])} · {job["สถานะ"]}**')
        st.write(job["อาการ"])
        table([summary(job)])
        for photo in job["รูปภาพ"]:
            st.image(photo["ข้อมูล"], caption=photo["ชื่อ"], width=280)
        state = job["สถานะ"]
        if manager and state in ("แจ้งใหม่", "มอบหมายแล้ว"):
            with st.form(f'assign_{selected}'):
                tech = st.selectbox("มอบหมายช่าง", techs)
                due = st.date_input("กำหนดเสร็จ", min_value=datetime.now(ZoneInfo("Asia/Bangkok")).date())
                confirmed_priority = st.selectbox("ยืนยันความเร่งด่วน", ["ปกติ", "เร่งด่วน", "วิกฤต"], index=["ปกติ", "เร่งด่วน", "วิกฤต"].index(job["ความเร่งด่วน"]))
                if st.form_submit_button("บันทึกการมอบหมาย"):
                    job.update({"ช่าง": tech, "กำหนดเสร็จ": due.isoformat(), "ความเร่งด่วน": confirmed_priority, "สถานะ": "มอบหมายแล้ว"})
                    event(job, "มอบหมายแล้ว", actor, tech)
                    st.rerun()
        can_repair = role == "ช่าง" and actor == job["ช่าง"]
        if can_repair and state in ("มอบหมายแล้ว", "รออะไหล่"):
            if st.button("เริ่ม / กลับมาซ่อม"):
                job["สถานะ"] = "กำลังซ่อม"
                event(job, "กำลังซ่อม", actor)
                st.rerun()
        if can_repair and state == "กำลังซ่อม":
            with st.form(f'repair_{selected}'):
                cause = st.text_area("สาเหตุ", value=job["สาเหตุ"])
                fix = st.text_area("วิธีซ่อม", value=job["วิธีซ่อม"])
                parts = st.text_input("อะไหล่ที่ใช้ / อะไหล่ที่รอ", value=job["อะไหล่"])
                labor = st.number_input("เวลาซ่อมรวม (นาที)", min_value=0, value=job["เวลาซ่อม (นาที)"], step=1)
                downtime = st.number_input("เครื่องหยุดรวม (นาที)", min_value=0, value=job["เครื่องหยุด (นาที)"], step=1)
                action = st.selectbox("การดำเนินการ", ["บันทึกความคืบหน้า", "รออะไหล่", "ส่งตรวจรับ"])
                if st.form_submit_button("บันทึกงานช่าง"):
                    if action == "ส่งตรวจรับ" and (not cause.strip() or not fix.strip()):
                        st.error("กรอกสาเหตุและวิธีซ่อมก่อนส่งตรวจรับ")
                    elif action == "รออะไหล่" and not parts.strip():
                        st.error("ระบุอะไหล่ที่รอ")
                    else:
                        job.update({"สาเหตุ": cause.strip(), "วิธีซ่อม": fix.strip(), "อะไหล่": parts.strip(), "เวลาซ่อม (นาที)": labor, "เครื่องหยุด (นาที)": downtime})
                        job["สถานะ"] = {"ส่งตรวจรับ": "รอตรวจรับ", "รออะไหล่": "รออะไหล่"}.get(action, "กำลังซ่อม")
                        event(job, action, actor, fix)
                        st.rerun()
        if state == "รอตรวจรับ" and ((role == "ผู้แจ้ง" and actor == job["ผู้แจ้ง"]) or manager):
            with st.form(f'accept_{selected}'):
                result = st.selectbox("ผลตรวจรับ", ["ผ่าน", "ไม่ผ่าน"])
                note = st.text_area("ผลทดสอบ / เหตุผล *")
                if st.form_submit_button("ยืนยันผลตรวจรับ"):
                    if not note.strip():
                        st.error("กรุณาบันทึกผลทดสอบหรือเหตุผล")
                    else:
                        job["สถานะ"] = "ปิดงาน" if result == "ผ่าน" else "กำลังซ่อม"
                        event(job, job["สถานะ"], actor, note.strip())
                        st.rerun()
        if manager and state not in ("ปิดงาน", "ยกเลิก"):
            with st.expander("ยกเลิกใบงาน"):
                with st.form(f'cancel_{selected}'):
                    reason = st.text_input("เหตุผลยกเลิก")
                    if st.form_submit_button("ยืนยันยกเลิกใบงาน"):
                        if not reason.strip():
                            st.error("ต้องระบุเหตุผล")
                        else:
                            job["สถานะ"] = "ยกเลิก"
                            event(job, "ยกเลิก", actor, reason.strip())
                            st.rerun()
        st.subheader("ประวัติการดำเนินการ")
        table(job["ประวัติ"])

elif menu == "ทะเบียนเครื่องจักร":
    st.subheader("ทะเบียนเครื่องจักร")
    table(st.session_state.assets)
    machine = st.selectbox("ดูประวัติเครื่อง", list(assets), format_func=asset_label)
    table([summary(j) for j in jobs if j["เครื่องจักร"] == machine])
    if manager:
        with st.expander("เพิ่มเครื่องจักรทดลอง"):
            with st.form("asset"):
                code = st.text_input("รหัสเครื่องจักร")
                name = st.text_input("ชื่อเครื่องจักร")
                location = st.text_input("ตำแหน่ง")
                if st.form_submit_button("เพิ่มเครื่องจักร"):
                    if not all(v.strip() for v in (code, name, location)):
                        st.error("กรอกข้อมูลให้ครบ")
                    elif code.strip().upper() in assets:
                        st.error("รหัสเครื่องจักรซ้ำ")
                    else:
                        st.session_state.assets.append({"รหัส": code.strip().upper(), "ชื่อ": name.strip(), "ตำแหน่ง": location.strip()})
                        st.rerun()

elif menu == "แผน PM":
    st.subheader("แผนบำรุงรักษา PM")
    if manager:
        with st.form("new_pm", clear_on_submit=True):
            machine = st.selectbox("เครื่องจักร", list(assets), format_func=asset_label)
            task = st.text_input("รายการตรวจ *")
            frequency = st.selectbox("รอบตรวจ", ["รายวัน", "รายสัปดาห์", "รายเดือน", "รายปี"])
            due = st.date_input("กำหนดตรวจ")
            owner = st.selectbox("ผู้รับผิดชอบ", techs)
            if st.form_submit_button("เพิ่มแผน PM"):
                if not task.strip():
                    st.error("ระบุรายการตรวจ")
                else:
                    plans.append({"เลขที่": f"PM-{len(plans)+1:04d}", "เครื่องจักร": machine, "รายการ": task.strip(), "รอบตรวจ": frequency, "กำหนด": due.isoformat(), "ช่าง": owner, "สถานะ": "รอดำเนินการ", "ผลตรวจ": "", "บันทึกเมื่อ": ""})
                    st.rerun()
    table(plans)
    pending = [p for p in plans if p["สถานะ"] != "เสร็จแล้ว" and role == "ช่าง" and p["ช่าง"] == actor]
    if pending:
        selected = st.selectbox("บันทึกผล PM", [p["เลขที่"] for p in pending])
        with st.form("pm_result"):
            note = st.text_area("ผลการตรวจ *")
            if st.form_submit_button("ยืนยันตรวจเสร็จ"):
                if not note.strip():
                    st.error("กรอกผลการตรวจ")
                else:
                    plan = next(p for p in pending if p["เลขที่"] == selected)
                    plan.update({"สถานะ": "เสร็จแล้ว", "ผลตรวจ": note.strip(), "บันทึกเมื่อ": now()})
                    st.rerun()
    st.caption("รุ่นนี้กำหนดวันตรวจแต่ละรายการเอง ยังไม่สร้างงานรอบถัดไปอัตโนมัติ")

else:
    st.subheader("รายงานงานซ่อมทดลอง")
    rows = [summary(j) for j in jobs]
    table(rows)
    if rows:
        st.download_button("ดาวน์โหลด CSV", pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"), "cmms-demo.csv", "text/csv")
        st.bar_chart(pd.DataFrame(rows)["เครื่องจักร"].value_counts())


