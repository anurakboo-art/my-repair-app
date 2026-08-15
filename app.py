import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from PIL import Image
import io
import base64
import json
import plotly.express as px
from supabase import create_client

# -------------------------------------------------------------
# Config & Setup
# -------------------------------------------------------------
st.set_page_config(page_title="ระบบแจ้งซ่อมบำรุง / PM", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase_client()

# กำหนดโซนเวลาประเทศไทย (UTC+7)
THAILAND_TZ = timezone(timedelta(hours=7))

def get_thailand_now_dt():
    return datetime.now(THAILAND_TZ)

def parse_date(val, default_date):
    if not val or pd.isna(val):
        return default_date
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return default_date

def parse_time(val, default_time):
    if not val or pd.isna(val):
        return default_time
    try:
        val_str = str(val).strip()
        if "T" in val_str:
            val_str = val_str.split("T")[1]
        val_str = val_str.split("+")[0].split(".")[0] # ตัด timezone / microseconds ออก
        if len(val_str) >= 8:
            return datetime.strptime(val_str[:8], "%H:%M:%S").time()
        elif len(val_str) >= 5:
            return datetime.strptime(val_str[:5], "%H:%M").time()
        return default_time
    except Exception:
        return default_time

def format_timedelta(td):
    if pd.isna(td) or td is None:
        return "-"
    total_seconds = int(td.total_seconds())
    if total_seconds <= 0:
        return "0 นาที"
    
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days} วัน")
    if hours > 0:
        parts.append(f"{hours} ชม.")
    if minutes > 0 or (days == 0 and hours == 0):
        parts.append(f"{minutes} นาที")
    
    return " ".join(parts)

# -------------------------------------------------------------
# Helper Functions สำหรับจัดการรูปภาพหลายรูป & การแต่งสีตาราง
# -------------------------------------------------------------
def compress_and_to_base64(image_bytes, max_size=(600, 600), quality=60):
    if not image_bytes:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail(max_size)
        out_buf = io.BytesIO()
        img.save(out_buf, format='JPEG', quality=quality)
        return base64.b64encode(out_buf.getvalue()).decode('utf-8')
    except Exception:
        return ""

def compress_multiple_to_json(file_list, max_size=(600, 600), quality=60):
    if not file_list:
        return ""
    b64_list = []
    for file in file_list:
        if hasattr(file, 'getvalue'):
            img_bytes = file.getvalue()
        elif isinstance(file, bytes):
            img_bytes = file
        else:
            continue
        b64_str = compress_and_to_base64(img_bytes, max_size=max_size, quality=quality)
        if b64_str:
            b64_list.append(b64_str)
    return json.dumps(b64_list) if b64_list else ""

def base64_to_image(b64_str):
    if not b64_str or pd.isna(b64_str) or str(b64_str).strip() == "":
        return None
    try:
        img_bytes = base64.b64decode(str(b64_str))
        return Image.open(io.BytesIO(img_bytes))
    except Exception:
        return None

def get_image_list_from_b64(b64_val):
    if not b64_val or pd.isna(b64_val) or str(b64_val).strip() == "":
        return []
    s = str(b64_val).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            res = json.loads(s)
            if isinstance(res, list):
                return [x for x in res if x]
        except Exception:
            pass
    return [s]

def display_image_gallery(b64_val, title="🖼️ รูปถ่าย"):
    b64_list = get_image_list_from_b64(b64_val)
    images = [base64_to_image(x) for x in b64_list]
    images = [img for img in images if img is not None]
    
    if images:
        st.markdown(f"**{title} ({len(images)} รูป):**")
        cols = st.columns(min(len(images), 4))
        for idx, img in enumerate(images):
            with cols[idx % 4]:
                st.image(img, use_container_width=True)

def style_status(val):
    if val == "เสร็จสิ้น":
        return "background-color: #d4edda; color: #155724; font-weight: bold;"
    elif val == "รอดำเนินการ":
        return "background-color: #fff3cd; color: #856404; font-weight: bold;"
    elif val == "ยกเลิก":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
    elif val == "กำลังดำเนินการ":
        return "background-color: #cce5ff; color: #004085; font-weight: bold;"
    return ""

def apply_status_style(df_input):
    styler = df_input.style
    if hasattr(styler, "map"):
        return styler.map(style_status, subset=["สถานะ"])
    return styler.applymap(style_status, subset=["สถานะ"])

# กำหนดแผนก / โซน เริ่มต้น
DEFAULT_DEPTS = ["สีฝุ่น", "สีน้ำมัน", "โซน 2"]

COLUMN_NAMES = [
    "id", "ticket_no", "reporter", "job_type", "department", "equipment", 
    "description", "priority", "status", "report_date", "report_time", 
    "created_at", "image_before", "received_no", "received_date", "received_time", 
    "technician", "cause", "solution", "parts_used", "parts_qty", 
    "completed_date", "completed_time", "completed_at", "image_after"
]

def load_data():
    if not supabase:
        st.warning("⚠️ กรุณาตั้งค่า SUPABASE_URL และ SUPABASE_KEY ใน Secrets (.streamlit/secrets.toml)")
        return pd.DataFrame(columns=COLUMN_NAMES)
    try:
        res = supabase.table("tickets").select("*").execute()
        df = pd.DataFrame(res.data)
        if df.empty:
            return pd.DataFrame(columns=COLUMN_NAMES)
        for c in COLUMN_NAMES:
            if c not in df.columns:
                df[c] = ""
        
        # จัดเรียงลำดับใบแจ้งซ่อมตามวันที่แจ้ง (เก่าไปใหม่)
        df["sort_dt"] = pd.to_datetime(df["report_date"].astype(str) + " " + df["report_time"].astype(str).fillna("00:00:00"), errors='coerce')
        df = df.sort_values(by=["sort_dt", "created_at"], ascending=[True, True]).drop(columns=["sort_dt"])
        
        return df
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
        return pd.DataFrame(columns=COLUMN_NAMES)

def generate_default_ticket_no(df):
    now = get_thailand_now_dt()
    prefix = f"REP-{now.strftime('%Y%m%d')}-"
    if df.empty or "ticket_no" not in df.columns:
        return f"{prefix}001"
    
    today_tickets = df[df["ticket_no"].astype(str).str.startswith(prefix)]
    if today_tickets.empty:
        return f"{prefix}001"
    
    max_num = 0
    for t in today_tickets["ticket_no"].astype(str):
        try:
            num = int(t.split("-")[-1])
            if num > max_num:
                max_num = num
        except Exception:
            pass
    return f"{prefix}{max_num + 1:03d}"

def generate_default_received_no(df):
    now = get_thailand_now_dt()
    prefix = f"RCV-{now.strftime('%Y%m%d')}-"
    if df.empty or "received_no" not in df.columns:
        return f"{prefix}001"
    
    today_rcv = df[df["received_no"].astype(str).str.startswith(prefix)]
    if today_rcv.empty:
        return f"{prefix}001"
    
    max_num = 0
    for r in today_rcv["received_no"].astype(str):
        try:
            num = int(r.split("-")[-1])
            if num > max_num:
                max_num = num
        except Exception:
            pass
    return f"{prefix}{max_num + 1:03d}"

# -------------------------------------------------------------
# Main App Layout
# -------------------------------------------------------------
df = load_data()

st.title("🛠️ ระบบบันทึกงานแจ้งซ่อมบำรุง และ PM (เรียงจากวันเก่าไปใหม่)")

tab1, tab2, tab3 = st.tabs([
    "📝 บันทึกงานแจ้งซ่อม / PM",
    "⚙️ จัดการสถานะ / อัปเดตงานซ่อม",
    "📊 รายงาน & สถิติ"
])

# =============================================================
# TAB 1: บันทึกงานแจ้งซ่อม / PM
# =============================================================
with tab1:
    st.subheader("📋 ฟอร์มแจ้งซ่อม / แจ้งทำ PM")
    
    default_ticket_no = generate_default_ticket_no(df)
    
    existing_depts = df["department"].dropna().unique().tolist() if not df.empty and "department" in df.columns else []
    all_depts = list(dict.fromkeys(DEFAULT_DEPTS + [d for d in existing_depts if d]))
    dept_options = all_depts + ["➕ พิมพ์ระบุแผนกใหม่..."]
    
    with st.form("repair_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            ticket_no = st.text_input("เลขที่ใบแจ้งซ่อม *", value=default_ticket_no, placeholder="เช่น REP-20260815-001")
        with col2:
            reporter = st.text_input("ชื่อผู้แจ้ง *")
        with col3:
            job_type = st.selectbox("ประเภทงาน *", ["แจ้งซ่อม", "PM"])
            
        col4, col5 = st.columns(2)
        with col4:
            dept_choice = st.selectbox("แผนก / โซน *", dept_options)
            if dept_choice == "➕ พิมพ์ระบุแผนกใหม่...":
                department = st.text_input("พิมพ์ชื่อแผนก / โซน ใหม่ *")
            else:
                department = dept_choice
        with col5:
            equipment = st.text_input("อุปกรณ์ / เครื่องจักร / สถานที่ *")
        
        description = st.text_area("อาการเสีย / รายละเอียดงาน *", height=100)
        
        st.markdown("🕒 **วันและเวลาที่แจ้ง**")
        now_dt = get_thailand_now_dt()
        col_d1, col_t1 = st.columns(2)
        with col_d1:
            report_date = st.date_input("📅 วันที่แจ้ง", value=now_dt.date())
        with col_t1:
            report_time = st.time_input("⏰ เวลาที่แจ้ง", value=now_dt.time().replace(microsecond=0))
            
        priority = st.select_slider("ระดับความเร่งด่วน", options=["ปกติ", "ด่วน", "ด่วนที่สุด"], value="ปกติ")
        
        uploaded_images_b = st.file_uploader(
            "📸 อัปโหลดรูปถ่ายก่อนซ่อม / อาการเสีย (เลือกได้หลายรูป)", 
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True
        )
        
        submitted = st.form_submit_button("💾 บันทึกใบแจ้งซ่อม", use_container_width=True)
        
        if submitted:
            if not ticket_no.strip() or not reporter.strip() or not department.strip() or not equipment.strip() or not description.strip():
                st.error("❌ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")
            elif not supabase:
                st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
            else:
                check_dup = supabase.table("tickets").select("ticket_no").eq("ticket_no", ticket_no.strip()).execute()
                if check_dup.data:
                    st.error(f"❌ เลขที่ใบแจ้งซ่อม '{ticket_no.strip()}' มีในระบบแล้ว กรุณาใช้เลขอื่น")
                else:
                    image_b64 = compress_multiple_to_json(uploaded_images_b) if uploaded_images_b else ""
                    created_at_str = datetime.combine(report_date, report_time).replace(tzinfo=THAILAND_TZ).isoformat()
                    
                    new_data = {
                        "ticket_no": ticket_no.strip(),
                        "reporter": reporter,
                        "job_type": job_type,
                        "department": department.strip(),
                        "equipment": equipment,
                        "description": description,
                        "priority": priority,
                        "status": "รอดำเนินการ",
                        "report_date": str(report_date),
                        "report_time": report_time.strftime("%H:%M:%S"),
                        "created_at": created_at_str,
                        "image_before": image_b64,
                        "received_no": "",
                        "received_date": "",
                        "received_time": "",
                        "technician": "",
                        "cause": "",
                        "solution": "",
                        "parts_used": "",
                        "parts_qty": "",
                        "image_after": ""
                    }
                    
                    try:
                        supabase.table("tickets").insert(new_data).execute()
                        st.success(f"✅ บันทึกใบแจ้งซ่อมเลขที่ **{ticket_no}** เรียบร้อยแล้ว!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}")

# =============================================================
# TAB 2: จัดการสถานะ / อัปเดตงานซ่อม
# =============================================================
with tab2:
    st.subheader("⚙️ อัปเดตสถานะและบันทึกการซ่อม")
    
    if df.empty:
        st.info("ยังไม่มีข้อมูลใบแจ้งซ่อมในระบบ")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.multiselect("กรองตามสถานะ", options=["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"], default=["รอดำเนินการ", "กำลังดำเนินการ", "ยกเลิก"])
        with col_f2:
            search_kw = st.text_input("🔍 ค้นหา (เลขใบแจ้งซ่อม / เลขที่รับ / ชื่อผู้แจ้ง / อุปกรณ์)", "")
            
        df_filtered = df.copy()
        if status_filter:
            df_filtered = df_filtered[df_filtered["status"].isin(status_filter)]
        if search_kw:
            kw = search_kw.lower()
            df_filtered = df_filtered[
                df_filtered["ticket_no"].astype(str).str.lower().str.contains(kw) |
                df_filtered["received_no"].astype(str).str.lower().str.contains(kw) |
                df_filtered["reporter"].astype(str).str.lower().str.contains(kw) |
                df_filtered["equipment"].astype(str).str.lower().str.contains(kw) |
                df_filtered["description"].astype(str).str.lower().str.contains(kw)
            ]
            
        st.markdown(f"**รายการใบแจ้งซ่อม ({len(df_filtered)} รายการ) - เรียงตามวันที่ (เก่า ➔ ใหม่):**")
        
        display_cols = [
            "ticket_no", "received_no", "reporter", "job_type", "department", "equipment", 
            "description", "priority", "status", "report_date", "report_time", 
            "received_date", "received_time", "technician", "cause", "solution", 
            "completed_date", "completed_time"
        ]
        
        df_show = df_filtered[display_cols].copy()
        df_show.columns = [
            "เลขที่ใบแจ้งซ่อม", "เลขที่รับ", "ผู้แจ้ง", "ประเภทงาน", "แผนก", "อุปกรณ์", 
            "อาการเสีย/รายละเอียด", "ความเร่งด่วน", "สถานะ", "วันที่แจ้ง", "เวลาแจ้ง", 
            "วันที่รับ", "เวลาที่รับ", "ผู้ซ่อม", "สาเหตุ", "วิธีแก้ไข", "วันที่เสร็จ", "เวลาเสร็จ"
        ]
        
        st.dataframe(apply_status_style(df_show), use_container_width=True)
        
        st.markdown("---")
        st.markdown("### ✏️ แก้ไขข้อมูล / อัปเดตงานซ่อม")
        
        ticket_list = df_filtered["ticket_no"].tolist()
        if not ticket_list:
            st.warning("ไม่มีรายการตรงตามเงื่อนไขที่เลือก")
        else:
            selected_ticket_no = st.selectbox("เลือกเลขที่ใบแจ้งซ่อมเพื่อจัดการ:", ticket_list)
            ticket = df[df["ticket_no"] == selected_ticket_no].iloc[0]
            
            with st.form("update_form"):
                st.markdown("#### 1️⃣ ข้อมูลการแจ้งซ่อม (ฝั่งผู้แจ้ง)")
                col_e0, col_e1, col_e2, col_e3, col_e4 = st.columns(5)
                with col_e0:
                    ticket_no_edit = st.text_input("เลขที่ใบแจ้งซ่อม", value=str(ticket["ticket_no"] or ""))
                with col_e1:
                    reporter_edit = st.text_input("ผู้แจ้งซ่อม", value=str(ticket["reporter"] or ""))
                
                curr_job_type = str(ticket["job_type"] or "แจ้งซ่อม")
                job_type_list = ["แจ้งซ่อม", "PM"]
                if curr_job_type not in job_type_list:
                    job_type_list.append(curr_job_type)
                    
                with col_e2:
                    job_type_edit = st.selectbox("ประเภทงาน", job_type_list, index=job_type_list.index(curr_job_type))
                
                curr_ticket_dept = str(ticket["department"] or "")
                edit_dept_options = all_depts + ["➕ พิมพ์ระบุแผนกใหม่..."]
                curr_dept_idx = edit_dept_options.index(curr_ticket_dept) if curr_ticket_dept in edit_dept_options else len(edit_dept_options) - 1
                
                with col_e3:
                    dept_choice_edit = st.selectbox("แผนก / โซน", edit_dept_options, index=curr_dept_idx)
                    if dept_choice_edit == "➕ พิมพ์ระบุแผนกใหม่...":
                        department_edit = st.text_input("พิมพ์ชื่อแผนก / โซน ใหม่", value=curr_ticket_dept)
                    else:
                        department_edit = dept_choice_edit
                
                prio_options = ["ปกติ", "ด่วน", "ด่วนที่สุด"]
                curr_prio = str(ticket["priority"] or "ปกติ")
                if curr_prio not in prio_options:
                    curr_prio = "ปกติ"
                    
                with col_e4:
                    priority_edit = st.selectbox("ระดับความเร่งด่วน", prio_options, index=prio_options.index(curr_prio))
                    
                col_e5, col_e6 = st.columns(2)
                with col_e5:
                    equipment_edit = st.text_input("อุปกรณ์ / เครื่องจักร", value=str(ticket["equipment"] or ""))
                with col_e6:
                    description_edit = st.text_area("อาการเสีย / รายละเอียด", value=str(ticket["description"] or ""), height=70)
                
                st.markdown("🕒 **วันและเวลาที่แจ้ง (แก้ไขได้)**")
                col_rd, col_rt = st.columns(2)
                
                init_rep_date = parse_date(ticket["report_date"], now_dt.date())
                init_rep_time = parse_time(ticket["report_time"], now_dt.time().replace(microsecond=0))
                
                with col_rd:
                    report_date_edit = st.date_input("📅 วันที่แจ้ง", value=init_rep_date)
                with col_rt:
                    report_time_edit = st.time_input("⏰ เวลาที่แจ้ง", value=init_rep_time)
                
                display_image_gallery(ticket.get("image_before", ""), title="🖼️ รูปถ่ายก่อนซ่อมปัจจุบัน")
                
                uploaded_images_b_new = st.file_uploader(
                    "📸 เปลี่ยน/อัปโหลดเพิ่ม รูปถ่ายก่อนซ่อม (เลือกได้หลายรูป)",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key="edit_img_b"
                )
                
                st.markdown("---")
                st.markdown("#### 2️⃣ การดำเนินงานของช่าง (ฝั่งผู้ซ่อม)")
                
                curr_rcv_no = str(ticket.get("received_no", "") or "").strip()
                if not curr_rcv_no:
                    curr_rcv_no = generate_default_received_no(df)
                    
                col_rcv1, col_rcv2, col_rcv3 = st.columns(3)
                with col_rcv1:
                    received_no_input = st.text_input("เลขที่รับงาน / ใบรับ", value=curr_rcv_no)
                
                init_rcv_date = parse_date(ticket.get("received_date"), now_dt.date())
                init_rcv_time = parse_time(ticket.get("received_time"), now_dt.time().replace(microsecond=0))
                
                with col_rcv2:
                    received_date_input = st.date_input("📅 วันที่รับงาน", value=init_rcv_date)
                with col_rcv3:
                    received_time_input = st.time_input("⏰ เวลาที่รับงาน", value=init_rcv_time)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                status_options = ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"]
                curr_status = str(ticket["status"] or "รอดำเนินการ")
                status_idx = status_options.index(curr_status) if curr_status in status_options else 0
                
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    new_status = st.selectbox("สถานะงาน (เลือก 'ยกเลิก' เพื่อยกเลิกงาน) *", status_options, index=status_idx)
                with col_u2:
                    technician_name = st.text_input("ชื่อผู้ซ่อม / ช่างผู้รับผิดชอบ", value=str(ticket.get("technician", "") or ""))
                
                cause_input = st.text_area("สาเหตุของปัญหา / เหตุผลที่ยกเลิก", value=str(ticket.get("cause", "") or ""), height=70)
                solution_input = st.text_area("วิธีแก้ไข / การดำเนินการ", value=str(ticket.get("solution", "") or ""), height=70)
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    parts_used = st.text_input("อะไหล่ที่ใช้", value=str(ticket.get("parts_used", "") or ""))
                with col_p2:
                    parts_qty = st.text_input("จำนวนอะไหล่", value=str(ticket.get("parts_qty", "") or ""))
                    
                st.markdown("🕒 **วันและเวลาซ่อมเสร็จ**")
                col_cd, col_ct = st.columns(2)
                
                init_comp_date = parse_date(ticket.get("completed_date"), now_dt.date())
                init_comp_time = parse_time(ticket.get("completed_time"), now_dt.time().replace(microsecond=0))
                
                with col_cd:
                    completed_date = st.date_input("📅 วันที่ซ่อมเสร็จ", value=init_comp_date)
                with col_ct:
                    completed_time = st.time_input("⏰ เวลาที่ซ่อมเสร็จ", value=init_comp_time)
                
                display_image_gallery(ticket.get("image_after", ""), title="🖼️ รูปถ่ายหลังซ่อมปัจจุบัน")
                
                uploaded_images_a_new = st.file_uploader(
                    "📸 อัปโหลด/เปลี่ยน รูปถ่ายหลังซ่อมเสร็จ (เลือกได้หลายรูป)",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key="edit_img_a"
                )
                
                update_submitted = st.form_submit_button("💾 บันทึกการอัปเดต / ยกเลิกงาน", use_container_width=True)
                
                if update_submitted:
                    if not supabase:
                        st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                    else:
                        if uploaded_images_b_new:
                            img_before_b64 = compress_multiple_to_json(uploaded_images_b_new)
                        else:
                            img_before_b64 = str(ticket.get("image_before", "") or "")
                            
                        if uploaded_images_a_new:
                            img_after_b64 = compress_multiple_to_json(uploaded_images_a_new)
                        else:
                            img_after_b64 = str(ticket.get("image_after", "") or "")
                            
                        completed_at_str = None
                        comp_date_str = None
                        comp_time_str = None
                        
                        if new_status == "เสร็จสิ้น":
                            comp_date_str = str(completed_date)
                            comp_time_str = completed_time.strftime("%H:%M:%S")
                            completed_at_str = datetime.combine(completed_date, completed_time).replace(tzinfo=THAILAND_TZ).isoformat()
                            
                        created_at_str = datetime.combine(report_date_edit, report_time_edit).replace(tzinfo=THAILAND_TZ).isoformat()
                        
                        # ตัด received_at ออกเรียบร้อยเพื่อแก้ปัญหา PGRST204
                        update_data = {
                            "ticket_no": ticket_no_edit.strip(),
                            "reporter": reporter_edit,
                            "job_type": job_type_edit,
                            "department": department_edit.strip(),
                            "equipment": equipment_edit,
                            "description": description_edit,
                            "priority": priority_edit,
                            "report_date": str(report_date_edit),
                            "report_time": report_time_edit.strftime("%H:%M:%S"),
                            "created_at": created_at_str,
                            "image_before": img_before_b64,
                            "received_no": received_no_input.strip(),
                            "received_date": str(received_date_input) if received_no_input else "",
                            "received_time": received_time_input.strftime("%H:%M:%S") if received_no_input else "",
                            "status": new_status,
                            "technician": technician_name,
                            "cause": cause_input,
                            "solution": solution_input,
                            "parts_used": parts_used,
                            "parts_qty": parts_qty,
                            "completed_date": comp_date_str,
                            "completed_time": comp_time_str,
                            "completed_at": completed_at_str,
                            "image_after": img_after_b64
                        }
                        
                        try:
                            supabase.table("tickets").update(update_data).eq("id", ticket["id"]).execute()
                            st.success(f"✅ อัปเดตข้อมูลใบแจ้งซ่อม **{ticket_no_edit}** เรียบร้อยแล้ว (สถานะ: {new_status})!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"เกิดข้อผิดพลาดในการอัปเดต: {e}")

            # โซนสำหรับลบใบแจ้งซ่อมถาวรออกจากฐานข้อมูล
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("🚨 โซนอันตราย: ลบใบแจ้งซ่อมนี้ออกจากระบบถาวร"):
                st.warning(f"⚠️ คำเตือน: การลบใบแจ้งซ่อมเลขที่ **{ticket['ticket_no']}** จะลบข้อมูลออกจากระบบอย่างถาวร ไม่สามารถกู้คืนได้")
                confirm_delete = st.checkbox(f"ยืนยันต้องการลบใบแจ้งซ่อม {ticket['ticket_no']} ถาวร", key=f"del_chk_{ticket['id']}")
                if st.button("🗑️ ยืนยันลบข้อมูลออกจากฐานข้อมูล", disabled=not confirm_delete, type="primary", use_container_width=True):
                    try:
                        supabase.table("tickets").delete().eq("id", ticket["id"]).execute()
                        st.success(f"🗑️ ลบใบแจ้งซ่อม **{ticket['ticket_no']}** ออกจากระบบเรียบร้อยแล้ว")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการลบข้อมูล: {e}")

# =============================================================
# TAB 3: รายงาน & สถิติ
# =============================================================
with tab3:
    st.subheader("📊 สรุปรายงานและสถิติงานซ่อมบำรุง")
    
    if df.empty:
        st.info("ยังไม่มีข้อมูลสำหรับสรุปรายงาน")
    else:
        df_stats = df.copy()
        
        def calc_repair_time(row):
            if row["status"] == "เสร็จสิ้น" and pd.notna(row.get("completed_date")):
                try:
                    s_date = row['received_date'] if pd.notna(row.get('received_date')) and str(row.get('received_date')).strip() != "" else row['report_date']
                    s_time = row['received_time'] if pd.notna(row.get('received_time')) and str(row.get('received_time')).strip() != "" else row['report_time']
                    
                    if pd.isna(s_date) or str(s_date).strip() == "":
                        return None
                        
                    s_time_str = str(s_time).strip() if pd.notna(s_time) and str(s_time).strip() != "" else "00:00:00"
                    c_time_str = str(row['completed_time']).strip() if pd.notna(row['completed_time']) and str(row['completed_time']).strip() != "" else "00:00:00"
                    
                    start_dt = pd.to_datetime(f"{s_date} {s_time_str[:8]}")
                    end_dt = pd.to_datetime(f"{row['completed_date']} {c_time_str[:8]}")
                    if end_dt >= start_dt:
                        return end_dt - start_dt
                except Exception:
                    return None
            return None
            
        df_stats["repair_duration"] = df_stats.apply(calc_repair_time, axis=1)
        df_stats["ระยะเวลาซ่อมรวม"] = df_stats["repair_duration"].apply(format_timedelta)
        
        total_jobs = len(df_stats)
        pending_jobs = len(df_stats[df_stats["status"] == "รอดำเนินการ"])
        in_prog_jobs = len(df_stats[df_stats["status"] == "กำลังดำเนินการ"])
        done_jobs = len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
        cancel_jobs = len(df_stats[df_stats["status"] == "ยกเลิก"])
        
        valid_durations = df_stats["repair_duration"].dropna()
        avg_duration_str = "-"
        if not valid_durations.empty:
            avg_td = valid_durations.mean()
            avg_duration_str = format_timedelta(avg_td)
            
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("งานทั้งหมด", f"{total_jobs} งาน")
        m2.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
        m3.metric("🔄 กำลังซ่อม", f"{in_prog_jobs} งาน")
        m4.metric("✅ เสร็จสิ้น", f"{done_jobs} งาน")
        m5.metric("❌ ยกเลิก", f"{cancel_jobs} งาน")
        m6.metric("⏱️ เวลาซ่อมเฉลี่ย", avg_duration_str)
        
        st.markdown("---")
        
        col_g1, col_g2, col_g3 = st.columns(3)
        
        with col_g1:
            st.markdown("##### 📌 สัดส่วนตามสถานะงาน")
            status_counts = df_stats["status"].value_counts().reset_index()
            status_counts.columns = ["สถานะ", "จำนวน"]
            fig_status = px.pie(status_counts, names="สถานะ", values="จำนวน", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_status, use_container_width=True)
            
        with col_g2:
            st.markdown("##### 🚨 สัดส่วนระดับความเร่งด่วน")
            prio_counts = df_stats["priority"].value_counts().reset_index()
            prio_counts.columns = ["ความเร่งด่วน", "จำนวน"]
            fig_prio = px.bar(prio_counts, x="ความเร่งด่วน", y="จำนวน", color="ความเร่งด่วน", color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig_prio, use_container_width=True)
            
        with col_g3:
            st.markdown("##### 🏢 จำนวนงานแยกตามแผนก")
            dept_counts = df_stats["department"].value_counts().reset_index()
            dept_counts.columns = ["แผนก", "จำนวน"]
            fig_dept = px.bar(dept_counts, x="จำนวน", y="แผนก", orientation="h", color_discrete_sequence=["#3366cc"])
            st.plotly_chart(fig_dept, use_container_width=True)
            
        st.markdown("---")
        st.markdown("### 📄 ตารางรายงานสรุปงานซ่อม (เรียงตามวันที่แจ้ง)")
        
        def count_img_status(val):
            imgs = get_image_list_from_b64(val)
            return f"มี {len(imgs)} รูป" if imgs else "ไม่มี"
            
        df_stats["รูปถ่ายก่อนซ่อม"] = df_stats["image_before"].apply(count_img_status)
        df_stats["รูปถ่ายหลังซ่อม"] = df_stats["image_after"].apply(count_img_status)
        
        report_cols = [
            "ticket_no", "received_no", "reporter", "job_type", "department", "equipment", 
            "description", "status", "report_date", "report_time", "received_date", "received_time",
            "technician", "cause", "solution", "parts_used", "parts_qty", "completed_date", 
            "completed_time", "ระยะเวลาซ่อมรวม", "รูปถ่ายก่อนซ่อม", "รูปถ่ายหลังซ่อม"
        ]
        
        completed_df_display = df_stats[report_cols].copy()
        completed_df_display.columns = [
            "เลขที่ใบแจ้งซ่อม", "เลขที่รับ", "ผู้แจ้ง", "ประเภทงาน", "แผนก", "อุปกรณ์", 
            "อาการเสีย / รายละเอียด", "สถานะ", "วันที่แจ้ง", "เวลาแจ้ง", "วันที่รับ", "เวลาที่รับ",
            "ช่างผู้ซ่อม", "สาเหตุ", "วิธีแก้ไข", "อะไหล่ที่ใช้", "จำนวน", "วันที่เสร็จ", 
            "เวลาเสร็จ", "ระยะเวลาซ่อมรวม", "รูปก่อนซ่อม", "รูปหลังซ่อม"
        ]
        
        st.dataframe(apply_status_style(completed_df_display), use_container_width=True)
        
        csv_data = completed_df_display.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 ดาวน์โหลดรายงาน (CSV)",
            data=csv_data,
            file_name=f"repair_report_{get_thailand_now_dt().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
