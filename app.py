import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from PIL import Image
import io
import base64
import json
import re
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
        val_str = val_str.split("+")[0].split(".")[0]
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
# Helper Functions จัดการรูปภาพและวิดีโอ
# -------------------------------------------------------------
def compress_and_to_base64(image_bytes, max_size=(300, 300), quality=50):
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

def process_media_files(file_list, max_size=(300, 300), quality=50):
    if not file_list:
        return ""
    media_list = []
    for file in file_list:
        filename = getattr(file, 'name', '').lower()
        if hasattr(file, 'getvalue'):
            file_bytes = file.getvalue()
        elif isinstance(file, bytes):
            file_bytes = file
        else:
            continue
            
        if any(filename.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.mkv']):
            mime = "video/mp4"
            if filename.endswith(".mov"): mime = "video/quicktime"
            elif filename.endswith(".avi"): mime = "video/x-msvideo"
            elif filename.endswith(".mkv"): mime = "video/x-matroska"
            
            b64_str = base64.b64encode(file_bytes).decode('utf-8')
            media_list.append(f"data:{mime};base64,{b64_str}")
        else:
            b64_str = compress_and_to_base64(file_bytes, max_size=max_size, quality=quality)
            if b64_str:
                media_list.append(f"data:image/jpeg;base64,{b64_str}")
                
    return json.dumps(media_list) if media_list else ""

def base64_to_image(b64_str):
    if not b64_str or pd.isna(b64_str) or str(b64_str).strip() == "":
        return None
    try:
        raw_b64 = str(b64_str).split(",")[-1]
        img_bytes = base64.b64decode(raw_b64)
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

def display_media_gallery(b64_val, title="📸/🎥 สื่อประกอบ (รูปถ่าย / วิดีโอ)"):
    media_list = get_image_list_from_b64(b64_val)
    if not media_list:
        return
        
    st.markdown(f"**{title} ({len(media_list)} รายการ):**")
    
    MAX_COLS = 5
    cols = st.columns(MAX_COLS)
    
    for idx, item in enumerate(media_list):
        with cols[idx % MAX_COLS]:
            if "video" in item or item.startswith("data:video"):
                st.video(item)
            else:
                img = base64_to_image(item)
                if img:
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

DEFAULT_DEPTS = ["สีฝุ่น", "สีน้ำมัน", "โซน 2"]

COLUMN_NAMES = [
    "id", "ticket_no", "reporter", "job_type", "department", "equipment", 
    "description", "priority", "status", "report_date", "report_time", 
    "created_at", "image_before", "received_no", "received_date", "received_time", 
    "technician", "detected_symptom", "cause", "solution", "parts_used", "parts_qty", 
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
# Main App Layout (แบบ 5 Tabs)
# -------------------------------------------------------------
df = load_data()

st.title("🛠️ ระบบบันทึกงานแจ้งซ่อมบำรุง และ PM")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 บันทึกงานแจ้งซ่อม / PM",
    "⚙️ จัดการสถานะ / อัปเดตงานซ่อม",
    "📊 รายงาน & สถิติ",
    "📅 แผนงาน PM & ปฏิทิน",
    "📦 คลังอะไหล่ & ตั้งค่าระบบ"
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
        
        description = st.text_area("อาการเสียเบื้องต้น / รายละเอียดงาน *", height=100)
        
        st.markdown("🕒 **วันและเวลาที่แจ้ง**")
        now_dt = get_thailand_now_dt()
        col_d1, col_t1 = st.columns(2)
        with col_d1:
            report_date = st.date_input("📅 วันที่แจ้ง", value=now_dt.date())
        with col_t1:
            report_time = st.time_input("⏰ เวลาที่แจ้ง", value=now_dt.time().replace(microsecond=0))
            
        priority = st.select_slider("ระดับความเร่งด่วน", options=["ปกติ", "ด่วน", "ด่วนที่สุด"], value="ปกติ")
        
        uploaded_media_b = st.file_uploader(
            "📸/🎥 อัปโหลดรูปถ่ายหรือวิดีโอก่อนซ่อม (เลือกได้หลายไฟล์: .jpg, .png, .mp4, .mov)", 
            type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
            accept_multiple_files=True
        )
        st.caption("💡 แนะนำให้ใช้วิดีโอสั้น (ไม่เกิน 15-20 MB) เพื่อความรวดเร็วในการประมวลผล")
        
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
                    media_b64 = process_media_files(uploaded_media_b) if uploaded_media_b else ""
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
                        "image_before": media_b64
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
            "received_date", "received_time", "technician", "detected_symptom", "cause", "solution", 
            "completed_date", "completed_time"
        ]
        
        df_show = df_filtered[display_cols].copy()
        df_show.columns = [
            "เลขที่ใบแจ้งซ่อม", "เลขที่รับ", "ผู้แจ้ง", "ประเภทงาน", "แผนก", "อุปกรณ์", 
            "อาการเบื้องต้น", "ความเร่งด่วน", "สถานะ", "วันที่แจ้ง", "เวลาแจ้ง", 
            "วันที่รับ", "เวลาที่รับ", "ผู้ซ่อม", "อาการที่ตรวจพบ", "สาเหตุ", "การแก้ไข", "วันที่เสร็จ", "เวลาเสร็จ"
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
                    description_edit = st.text_area("อาการเบื้องต้น / รายละเอียด", value=str(ticket["description"] or ""), height=70)
                
                st.markdown("🕒 **วันและเวลาที่แจ้ง (แก้ไขได้)**")
                col_rd, col_rt = st.columns(2)
                
                init_rep_date = parse_date(ticket["report_date"], now_dt.date())
                init_rep_time = parse_time(ticket["report_time"], now_dt.time().replace(microsecond=0))
                
                with col_rd:
                    report_date_edit = st.date_input("📅 วันที่แจ้ง", value=init_rep_date)
                with col_rt:
                    report_time_edit = st.time_input("⏰ เวลาที่แจ้ง", value=init_rep_time)
                
                display_media_gallery(ticket.get("image_before", ""), title="📸/🎥 สื่อประกอบก่อนซ่อมปัจจุบัน")
                
                uploaded_media_b_new = st.file_uploader(
                    "📸/🎥 เปลี่ยน/อัปโหลดเพิ่ม รูปหรือวิดีโอก่อนซ่อม",
                    type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
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
                
                # ช่องกรอก "อาการที่ตรวจพบ", "สาเหตุ", "การแก้ไข"
                col_sec1, col_sec2 = st.columns(2)
                with col_sec1:
                    detected_symptom_input = st.text_area(
                        "🔍 อาการที่ตรวจพบ (Symptom Found)", 
                        value=str(ticket.get("detected_symptom", "") or ""), 
                        height=100,
                        placeholder="ระบุรายละเอียดอาการเสียจริง หรือจุดที่ช่างตรวจพบเพิ่มเติม..."
                    )
                    cause_input = st.text_area(
                        "⚠️ สาเหตุของปัญหา / เหตุผลที่ยกเลิก", 
                        value=str(ticket.get("cause", "") or ""), 
                        height=100,
                        placeholder="ระบุต้นเหตุของความเสียหาย..."
                    )
                with col_sec2:
                    solution_input = st.text_area(
                        "🛠️ การแก้ไข / วิธีดำเนินการ (Action Taken)", 
                        value=str(ticket.get("solution", "") or ""), 
                        height=230,
                        placeholder="ระบุขั้นตอนและวิธีการปรับปรุงแก้ไข เครื่องจักร/อุปกรณ์..."
                    )
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    parts_used = st.text_area(
                        "🧩 อะไหล่ที่ใช้ (ระบุเป็นข้อๆ ได้)", 
                        value=str(ticket.get("parts_used", "") or ""), 
                        height=100,
                        placeholder="1. อะไหล่ A\n2. อะไหล่ B"
                    )
                with col_p2:
                    parts_qty = st.text_area(
                        "🔢 จำนวนอะไหล่", 
                        value=str(ticket.get("parts_qty", "") or ""), 
                        height=100,
                        placeholder="1. 2 ตัว\n2. 1 ชิ้น"
                    )
                    
                st.markdown("🕒 **วันและเวลาซ่อมเสร็จ**")
                col_cd, col_ct = st.columns(2)
                
                init_comp_date = parse_date(ticket.get("completed_date"), now_dt.date())
                init_comp_time = parse_time(ticket.get("completed_time"), now_dt.time().replace(microsecond=0))
                
                with col_cd:
                    completed_date = st.date_input("📅 วันที่ซ่อมเสร็จ", value=init_comp_date)
                with col_ct:
                    completed_time = st.time_input("⏰ เวลาที่ซ่อมเสร็จ", value=init_comp_time)
                
                display_media_gallery(ticket.get("image_after", ""), title="📸/🎥 สื่อประกอบหลังซ่อมปัจจุบัน")
                
                uploaded_media_a_new = st.file_uploader(
                    "📸/🎥 อัปโหลด/เปลี่ยน รูปหรือวิดีโอหลังซ่อมเสร็จ",
                    type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
                    accept_multiple_files=True,
                    key="edit_img_a"
                )
                
                update_submitted = st.form_submit_button("💾 บันทึกการอัปเดต / ยกเลิกงาน", use_container_width=True)
                
                if update_submitted:
                    if not supabase:
                        st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                    else:
                        if uploaded_media_b_new:
                            img_before_b64 = process_media_files(uploaded_media_b_new)
                        else:
                            img_before_b64 = str(ticket.get("image_before", "") or "")
                            
                        if uploaded_media_a_new:
                            img_after_b64 = process_media_files(uploaded_media_a_new)
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
                            "detected_symptom": detected_symptom_input,
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
        now_date = get_thailand_now_dt().date()
        
        st.markdown("##### 📅 เลือกช่วงเวลาเพื่อดูรายงาน")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            period_option = st.selectbox(
                "ช่วงเวลาการดูข้อมูล",
                [
                    "ทั้งหมด", 
                    "7 วันล่าสุด (รายสัปดาห์)", 
                    "30 วันล่าสุด (รายเดือน)", 
                    "ปีปัจจุบัน (รายปี)", 
                    "กำหนดช่วงวันที่เอง (Custom)"
                ]
            )
            
        df_stats["parsed_rep_date"] = pd.to_datetime(df_stats["report_date"], errors="coerce").dt.date
        
        if period_option == "7 วันล่าสุด (รายสัปดาห์)":
            start_date = now_date - timedelta(days=7)
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "30 วันล่าสุด (รายเดือน)":
            start_date = now_date - timedelta(days=30)
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "ปีปัจจุบัน (รายปี)":
            start_date = datetime(now_date.year, 1, 1).date()
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "กำหนดช่วงวันที่เอง (Custom)":
            with col_t2:
                custom_range = st.date_input(
                    "ระบุวันที่ (เริ่มต้น - สิ้นสุด)", 
                    value=[now_date - timedelta(days=30), now_date]
                )
                if isinstance(custom_range, (list, tuple)) and len(custom_range) == 2:
                    df_stats = df_stats[(df_stats["parsed_rep_date"] >= custom_range[0]) & (df_stats["parsed_rep_date"] <= custom_range[1])]
        
        if df_stats.empty:
            st.warning("⚠️ ไม่พบข้อมูลงานซ่อมซ่อมบำรุงตามช่วงเวลาที่เลือก")
        else:
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
            done_jobs = len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
            pending_jobs = len(df_stats[df_stats["status"] == "รอดำเนินการ"])
            in_prog_jobs = len(df_stats[df_stats["status"] == "กำลังดำเนินการ"])
            cancel_jobs = len(df_stats[df_stats["status"] == "ยกเลิก"])
            outstanding_jobs = pending_jobs + in_prog_jobs
            
            valid_durations = df_stats["repair_duration"].dropna()
            avg_duration_str = "-"
            total_duration_str = "-"
            if not valid_durations.empty:
                avg_td = valid_durations.mean()
                sum_td = valid_durations.sum()
                avg_duration_str = format_timedelta(avg_td)
                total_duration_str = format_timedelta(sum_td)
                
            m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
            m1.metric("📋 งานทั้งหมด", f"{total_jobs} งาน")
            m2.metric("✅ เสร็จสิ้นแล้ว", f"{done_jobs} งาน")
            m3.metric("⚠️ งานค้างสะสม", f"{outstanding_jobs} งาน")
            m4.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
            m5.metric("🔄 กำลังซ่อม", f"{in_prog_jobs} งาน")
            m6.metric("⏱️ เวลาซ่อมรวมทั้งหมด", total_duration_str)
            m7.metric("⏱️ เวลาซ่อมเฉลี่ย", avg_duration_str)
            
            st.markdown("---")
            
            # แถวที่ 1: กราฟงานค้างสะสม + กราฟสัดส่วนสถานะงาน
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("##### 🕒 กราฟงานค้างสะสมแยกตามอายุงาน (ยังไม่เสร็จ)")
                df_pending = df_stats[df_stats["status"].isin(["รอดำเนินการ", "กำลังดำเนินการ"])].copy()
                
                if df_pending.empty:
                    st.success("🎉 ไม่มีงานค้างสะสมในช่วงเวลาที่เลือก!")
                else:
                    def calc_age_days(r_date_val):
                        try:
                            r_date = pd.to_datetime(r_date_val).date()
                            return (now_date - r_date).days
                        except Exception:
                            return 0
                            
                    df_pending["age_days"] = df_pending["report_date"].apply(calc_age_days)
                    
                    def categorize_age(days):
                        if days < 7:
                            return "1. น้อยกว่า 7 วัน"
                        elif 7 <= days <= 15:
                            return "2. 7 - 15 วัน"
                        elif 16 <= days <= 30:
                            return "3. 16 - 30 วัน"
                        else:
                            return "4. มากกว่า 1 เดือน"
                            
                    df_pending["age_group"] = df_pending["age_days"].apply(categorize_age)
                    
                    age_order = ["1. น้อยกว่า 7 วัน", "2. 7 - 15 วัน", "3. 16 - 30 วัน", "4. มากกว่า 1 เดือน"]
                    age_counts = df_pending["age_group"].value_counts().reindex(age_order, fill_value=0).reset_index()
                    age_counts.columns = ["อายุงานค้าง", "จำนวนงาน"]
                    
                    age_display_map = {
                        "1. น้อยกว่า 7 วัน": "< 7 วัน",
                        "2. 7 - 15 วัน": "7 - 15 วัน",
                        "3. 16 - 30 วัน": "16 - 30 วัน",
                        "4. มากกว่า 1 เดือน": "> 1 เดือน"
                    }
                    age_counts["ช่วงอายุงาน"] = age_counts["อายุงานค้าง"].map(age_display_map)
                    
                    color_map = {
                        "< 7 วัน": "#2ecc71",
                        "7 - 15 วัน": "#f1c40f",
                        "16 - 30 วัน": "#e67e22",
                        "> 1 เดือน": "#e74c3c"
                    }
                    
                    fig_aging = px.bar(
                        age_counts, 
                        x="ช่วงอายุงาน", 
                        y="จำนวนงาน", 
                        text="จำนวนงาน",
                        color="ช่วงอายุงาน",
                        color_discrete_map=color_map,
                        title=f"รวมงานค้างทั้งหมด {len(df_pending)} รายการ"
                    )
                    fig_aging.update_traces(textposition='outside')
                    fig_aging.update_layout(showlegend=False, yaxis_title="จำนวนใบแจ้งซ่อม", xaxis_title="อายุงานค้าง")
                    st.plotly_chart(fig_aging, use_container_width=True)
                    
            with col_g2:
                st.markdown("##### 📌 สัดส่วนตามสถานะงานทั้งหมด")
                status_counts = df_stats["status"].value_counts().reset_index()
                status_counts.columns = ["สถานะ", "จำนวน"]
                fig_status = px.pie(status_counts, names="สถานะ", values="จำนวน", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_status, use_container_width=True)

            # แถวที่ 2: กราฟวิเคราะห์ประเภทงาน (แจ้งซ่อม VS PM)
            col_g5, col_g6 = st.columns(2)
            with col_g5:
                st.markdown("##### 🛠️ สัดส่วนประเภทงาน (แจ้งซ่อม VS PM)")
                job_type_counts = df_stats["job_type"].value_counts().reset_index()
                job_type_counts.columns = ["ประเภทงาน", "จำนวน"]
                fig_job_type = px.pie(
                    job_type_counts, 
                    names="ประเภทงาน", 
                    values="จำนวน", 
                    hole=0.4, 
                    color="ประเภทงาน",
                    color_discrete_map={"แจ้งซ่อม": "#3498db", "PM": "#2ecc71"}
                )
                fig_job_type.update_traces(textinfo='percent+label+value')
                st.plotly_chart(fig_job_type, use_container_width=True)

            with col_g6:
                st.markdown("##### 📅 สถานะงานประเภท PM แยกตามแผนก")
                df_pm = df_stats[df_stats["job_type"] == "PM"]
                if df_pm.empty:
                    st.info("ℹ️ ไม่พบข้อมูลงานประเภท PM ในช่วงเวลาที่เลือก")
                else:
                    pm_dept_status = df_pm.groupby(["department", "status"]).size().reset_index(name="จำนวน")
                    fig_pm_dept = px.bar(
                        pm_dept_status, 
                        x="department", 
                        y="จำนวน", 
                        color="status", 
                        barmode="stack",
                        color_discrete_map={
                            "เสร็จสิ้น": "#2ecc71",
                            "กำลังดำเนินการ": "#3498db",
                            "รอดำเนินการ": "#f1c40f",
                            "ยกเลิก": "#e74c3c"
                        }
                    )
                    fig_pm_dept.update_layout(xaxis_title="แผนก / โซน", yaxis_title="จำนวนงาน PM")
                    st.plotly_chart(fig_pm_dept, use_container_width=True)

            # แถวที่ 3: กราฟความเร่งด่วน + กราฟแยกตามแผนก
            col_g3, col_g4 = st.columns(2)
            with col_g3:
                st.markdown("##### 🚨 สัดส่วนระดับความเร่งด่วน")
                prio_counts = df_stats["priority"].value_counts().reset_index()
                prio_counts.columns = ["ความเร่งด่วน", "จำนวน"]
                fig_prio = px.bar(prio_counts, x="ความเร่งด่วน", y="จำนวน", color="ความเร่งด่วน", color_discrete_sequence=px.colors.qualitative.Set2)
                st.plotly_chart(fig_prio, use_container_width=True)
                
            with col_g4:
                st.markdown("##### 🏢 จำนวนงานรวมแยกตามแผนก")
                dept_counts = df_stats["department"].value_counts().reset_index()
                dept_counts.columns = ["แผนก", "จำนวน"]
                fig_dept = px.bar(
                    dept_counts, 
                    x="จำนวน", 
                    y="แผนก", 
                    orientation="h", 
                    color="แผนก",
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig_dept.update_layout(showlegend=False)
                st.plotly_chart(fig_dept, use_container_width=True)

            # สรุปสถิติการใช้อะไหล่และอุปกรณ์
            st.markdown("---")
            st.markdown("### 🧩 สรุปสถิติการใช้อะไหล่และอุปกรณ์ (Spare Parts Report)")

            def parse_parts_summary(df_in):
                items = []
                for idx, row in df_in.iterrows():
                    p_str = str(row.get("parts_used", "") or "").strip()
                    q_str = str(row.get("parts_qty", "") or "").strip()
                    
                    if not p_str or p_str.lower() == "nan":
                        continue
                        
                    p_lines = [line.strip() for line in p_str.split('\n') if line.strip()]
                    q_lines = [line.strip() for line in q_str.split('\n') if line.strip()]
                    
                    for i, p_line in enumerate(p_lines):
                        clean_part = re.sub(r'^\d+[\.\)]\s*|^[-\*]\s*', '', p_line).strip()
                        qty_val_raw = ""
                        if i < len(q_lines):
                            qty_val_raw = re.sub(r'^\d+[\.\)]\s*|^[-\*]\s*', '', q_lines[i]).strip()
                        
                        num_val = 1.0
                        unit_str = ""
                        if qty_val_raw and qty_val_raw != "-":
                            match = re.search(r'(\d+(?:\.\d+)?)', qty_val_raw)
                            if match:
                                try:
                                    num_val = float(match.group(1))
                                except ValueError:
                                    num_val = 1.0
                                unit_str = re.sub(r'\d+(?:\.\d+)?', '', qty_val_raw).strip()
                            else:
                                unit_str = qty_val_raw.strip()
                        
                        if clean_part:
                            items.append({
                                "ticket_no": row.get("ticket_no", ""),
                                "อะไหล่": clean_part,
                                "qty_num": num_val,
                                "unit": unit_str,
                                "raw_qty": qty_val_raw if qty_val_raw else "-"
                            })
                return pd.DataFrame(items)

            df_parts_parsed = parse_parts_summary(df_stats)

            if df_parts_parsed.empty:
                st.info("ℹ️ ยังไม่มีข้อมูลการบันทึกใช้อะไหล่ในช่วงเวลาที่เลือก")
            else:
                def get_unit(units_series):
                    unique_u = [u for u in units_series if u]
                    return unique_u[0] if unique_u else ""

                parts_summary = df_parts_parsed.groupby("อะไหล่").agg(
                    total_qty=("qty_num", "sum"),
                    unit=("unit", get_unit),
                    times_used=("อะไหล่", "count")
                ).reset_index()

                def format_qty_display(row):
                    q = row["total_qty"]
                    q_str = f"{int(q)}" if q.is_integer() else f"{q:.2f}"
                    if row["unit"]:
                        return f"{q_str} {row['unit']}"
                    return f"{q_str}"

                parts_summary["จำนวนที่ใช้งาน"] = parts_summary["total_qty"]
                parts_summary["จำนวนที่ใช้งาน (ระบุหน่วย)"] = parts_summary.apply(format_qty_display, axis=1)
                parts_summary = parts_summary.sort_values(by="total_qty", ascending=False)
                
                parts_summary_display = parts_summary[["อะไหล่", "จำนวนที่ใช้งาน (ระบุหน่วย)", "times_used"]].copy()
                parts_summary_display.columns = ["รายการอะไหล่ / อุปกรณ์", "จำนวนที่ใช้งาน", "จำนวนครั้งที่ซ่อม (งาน)"]
                
                total_parts_sum = parts_summary["total_qty"].sum()
                total_parts_sum_str = f"{int(total_parts_sum)}" if total_parts_sum.is_integer() else f"{total_parts_sum:.2f}"

                col_pmetric1, col_pmetric2 = st.columns(2)
                col_pmetric1.metric("📦 ประเภทอะไหล่ที่ถูกใช้งาน", f"{len(parts_summary)} ชนิด")
                col_pmetric2.metric("🔢 รวมจำนวนอะไหล่ที่เบิกใช้ทั้งหมด", f"{total_parts_sum_str} ชิ้น/หน่วย")
                
                col_pchart, col_ptable = st.columns([1, 1])
                with col_pchart:
                    st.markdown("##### 📊 10 อันดับอะไหล่ที่ใช้จำนวนมากที่สุด")
                    top10_parts = parts_summary.head(10).sort_values(by="total_qty", ascending=True)
                    fig_parts = px.bar(
                        top10_parts,
                        x="total_qty",
                        y="อะไหล่",
                        orientation="h",
                        text="จำนวนที่ใช้งาน (ระบุหน่วย)",
                        color="total_qty",
                        color_continuous_scale="Viridis"
                    )
                    fig_parts.update_traces(textposition="outside")
                    fig_parts.update_layout(showlegend=False, coloraxis_showscale=False, yaxis_title="", xaxis_title="จำนวนที่ใช้งาน")
                    st.plotly_chart(fig_parts, use_container_width=True)
                    
                with col_ptable:
                    st.markdown("##### 📋 ตารางรายละเอียดสรุปจำนวนการใช้อะไหล่")
                    st.dataframe(parts_summary_display, use_container_width=True, hide_index=True)
                
            st.markdown("---")
            st.markdown("### 📄 ตารางรายงานสรุปงานซ่อม (เรียงตามวันที่แจ้ง)")
            
            def count_media_status(val):
                items = get_image_list_from_b64(val)
                return f"มี {len(items)} ไฟล์" if items else "ไม่มี"
                
            df_stats["ไฟล์ประกอบก่อนซ่อม"] = df_stats["image_before"].apply(count_media_status)
            df_stats["ไฟล์ประกอบหลังซ่อม"] = df_stats["image_after"].apply(count_media_status)
            
            report_cols = [
                "ticket_no", "received_no", "reporter", "job_type", "department", "equipment", 
                "description", "status", "report_date", "report_time", "received_date", "received_time",
                "technician", "detected_symptom", "cause", "solution", "parts_used", "parts_qty", "completed_date", 
                "completed_time", "ระยะเวลาซ่อมรวม", "ไฟล์ประกอบก่อนซ่อม", "ไฟล์ประกอบหลังซ่อม"
            ]
            
            completed_df_display = df_stats[report_cols].copy()
            completed_df_display.columns = [
                "เลขที่ใบแจ้งซ่อม", "เลขที่รับ", "ผู้แจ้ง", "ประเภทงาน", "แผนก", "อุปกรณ์", 
                "อาการเบื้องต้น", "สถานะ", "วันที่แจ้ง", "เวลาแจ้ง", "วันที่รับ", "เวลาที่รับ",
                "ช่างผู้ซ่อม", "อาการที่ตรวจพบ", "สาเหตุ", "การแก้ไข", "อะไหล่ที่ใช้", "จำนวน", "วันที่เสร็จ", 
                "เวลาเสร็จ", "ระยะเวลาซ่อมรวม", "สื่อก่อนซ่อม", "สื่อหลังซ่อม"
            ]
            
            st.dataframe(apply_status_style(completed_df_display), use_container_width=True)
            
            csv_data = completed_df_display.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 ดาวน์โหลดรายงาน (CSV)",
                data=csv_data,
                file_name=f"repair_report_{get_thailand_now_dt().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

            # ตารางรายการงานล่าสุด (Work Order List & Drill-down)
            st.markdown("---")
            st.markdown("### 📋 ตารางรายการงานซ่อมล่าสุด (Work Order List Table)")
            st.caption("เลือกรายการจากตัวเลือกด้านล่างเพื่อ Drill-down ดูรายละเอียดงานฉบับเต็มได้ทันที")

            if not df_stats.empty:
                df_recent = df_stats.tail(10).iloc[::-1].copy()

                recent_cols = ["ticket_no", "reporter", "job_type", "equipment", "status", "technician"]
                df_recent_display = df_recent[recent_cols].copy()
                df_recent_display.columns = [
                    "เลขที่ใบแจ้งซ่อม (Ticket)", 
                    "ชื่อผู้แจ้ง", 
                    "ประเภทงาน",
                    "อุปกรณ์ / เครื่องจักร", 
                    "สถานะ", 
                    "ช่างผู้รับผิดชอบ"
                ]

                st.dataframe(apply_status_style(df_recent_display), use_container_width=True)

                recent_tickets_list = df_recent["ticket_no"].tolist()

                col_sel1, _ = st.columns([2, 1])
                with col_sel1:
                    selected_dd_ticket = st.selectbox(
                        "🔍 เลือกใบแจ้งซ่อมเพื่อดูรายละเอียด (Drill-down):",
                        options=recent_tickets_list,
                        index=0,
                        key="dd_selectbox_recent_work_orders"
                    )

                if selected_dd_ticket:
                    t_detail = df_recent[df_recent["ticket_no"] == selected_dd_ticket].iloc[0]
                    
                    with st.expander(f"🔎 รายละเอียด Drill-down: ใบแจ้งซ่อม {t_detail['ticket_no']} [{t_detail['status']}]", expanded=True):
                        col_d1, col_d2, col_d3 = st.columns(3)
                        with col_d1:
                            st.markdown(f"**เลขที่ใบแจ้งซ่อม:** `{t_detail.get('ticket_no', '-')}`")
                            st.markdown(f"**ชื่อผู้แจ้ง:** {t_detail.get('reporter', '-')}")
                            st.markdown(f"**ประเภทงาน:** {t_detail.get('job_type', '-')}")
                            st.markdown(f"**แผนก / โซน:** {t_detail.get('department', '-')}")
                        with col_d2:
                            st.markdown(f"**อุปกรณ์/เครื่องจักร:** {t_detail.get('equipment', '-')}")
                            st.markdown(f"**ระดับความเร่งด่วน:** {t_detail.get('priority', '-')}")
                            st.markdown(f"**สถานะปัจจุบัน:** `{t_detail.get('status', '-')}`")
                            st.markdown(f"**วันที่แจ้งซ่อม:** {t_detail.get('report_date', '-')} {t_detail.get('report_time', '')}")
                        with col_d3:
                            st.markdown(f"**เลขที่รับงาน:** {t_detail.get('received_no', '-')}")
                            st.markdown(f"**ช่างผู้รับผิดชอบ:** {t_detail.get('technician', '-')}")
                            st.markdown(f"**วันที่เสร็จสิ้น:** {t_detail.get('completed_date', '-')} {t_detail.get('completed_time', '')}")
                            st.markdown(f"**ระยะเวลาซ่อมรวม:** {t_detail.get('ระยะเวลาซ่อมรวม', '-')}")

                        st.markdown("---")
                        st.markdown(f"**📌 อาการเสียเบื้องต้น (ที่ผู้แจ้งระบุ):** {t_detail.get('description', '-')}")
                        st.markdown(f"**🔍 อาการที่ตรวจพบจริง (โดยช่าง):** {t_detail.get('detected_symptom', '-')}")
                        st.markdown(f"**⚠️ สาเหตุของปัญหา:** {t_detail.get('cause', '-')}")
                        st.markdown(f"**🛠️ การแก้ไข / วิธีดำเนินการ:** {t_detail.get('solution', '-')}")
                        
                        p_used = str(t_detail.get('parts_used', '') or '').strip()
                        p_qty = str(t_detail.get('parts_qty', '') or '').strip()
                        
                        col_part1, col_part2 = st.columns(2)
                        with col_part1:
                            st.markdown("**🧩 อะไหล่ที่ใช้:**")
                            if p_used:
                                st.text(p_used)
                            else:
                                st.write("-")
                        with col_part2:
                            st.markdown("**🔢 จำนวนอะไหล่:**")
                            if p_qty:
                                st.text(p_qty)
                            else:
                                st.write("-")

                        st.markdown("---")
                        col_img1, col_img2 = st.columns(2)
                        with col_img1:
                            display_media_gallery(t_detail.get("image_before", ""), title="📸/🎥 สื่อประกอบก่อนซ่อม (Before)")
                        with col_img2:
                            display_media_gallery(t_detail.get("image_after", ""), title="📸/🎥 สื่อประกอบหลังซ่อม (After)")

# =============================================================
# TAB 4: แผนงาน PM & ปฏิทินการบำรุงรักษา
# =============================================================
with tab4:
    st.subheader("📅 ตารางวางแผนการบำรุงรักษาเชิงป้องกัน (PM Schedule)")
    st.caption("ระบบติดตามรอบการทำ PM เครื่องจักรล่วงหน้า เพื่อป้องกันเครื่องจักรหยุดทำงานโดยไม่คาดคิด")
    
    df_pm_all = df[df["job_type"] == "PM"] if not df.empty else pd.DataFrame()
    
    col_pm1, col_pm2 = st.columns([1, 2])
    
    with col_pm1:
        st.markdown("#### ➕ วางแผน PM ล่วงหน้า")
        with st.form("add_pm_plan_form", clear_on_submit=True):
            pm_equip = st.text_input("อุปกรณ์ / เครื่องจักร *", placeholder="เช่น เครื่องอัดอากาศ No.1")
            
            existing_depts_pm = df["department"].dropna().unique().tolist() if not df.empty and "department" in df.columns else []
            all_depts_pm = list(dict.fromkeys(DEFAULT_DEPTS + [d for d in existing_depts_pm if d]))
            
            pm_dept = st.selectbox("แผนก / โซน *", all_depts_pm)
            pm_freq = st.selectbox("ความถี่ในการทำ PM", ["ทุก 1 สัปดาห์", "ทุก 1 เดือน", "ทุก 3 เดือน", "ทุก 6 เดือน", "ทุก 1 ปี"])
            pm_next_date = st.date_input("📅 วันที่กำหนดทำ PM ครั้งถัดไป", value=get_thailand_now_dt().date())
            pm_note = st.text_area("รายละเอียดการตรวจเช็ก (Checklist)", placeholder="- เช็กน้ำมันเครื่อง\n- ทำความสะอาดฟิลเตอร์")
            
            btn_save_pm = st.form_submit_button("💾 บันทึกแผน PM", use_container_width=True)
            if btn_save_pm:
                if not pm_equip.strip():
                    st.error("❌ กรุณาระบุชื่ออุปกรณ์/เครื่องจักร")
                elif not supabase:
                    st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                else:
                    pm_ticket_no = generate_default_ticket_no(df)
                    new_pm_data = {
                        "ticket_no": pm_ticket_no,
                        "reporter": "ระบบวางแผน PM",
                        "job_type": "PM",
                        "department": pm_dept,
                        "equipment": pm_equip.strip(),
                        "description": f"[แผน PM: {pm_freq}] {pm_note.strip()}",
                        "priority": "ปกติ",
                        "status": "รอดำเนินการ",
                        "report_date": str(pm_next_date),
                        "report_time": "08:00:00",
                        "created_at": datetime.combine(pm_next_date, datetime.min.time()).replace(tzinfo=THAILAND_TZ).isoformat()
                    }
                    try:
                        supabase.table("tickets").insert(new_pm_data).execute()
                        st.success(f"✅ บันทึกแผน PM เรียบร้อย! ออกใบงานเลขที่: **{pm_ticket_no}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

    with col_pm2:
        st.markdown("#### 📋 รายการงาน PM ทั้งหมดในระบบ")
        if df_pm_all.empty:
            st.info("ยังไม่มีข้อมูลแผนงาน PM ในระบบ")
        else:
            pm_status_filter = st.multiselect("กรองสถานะ PM", ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"], default=["รอดำเนินการ", "กำลังดำเนินการ"])
            df_pm_show = df_pm_all[df_pm_all["status"].isin(pm_status_filter)]
            
            if df_pm_show.empty:
                st.warning("ไม่พบรายการ PM ตามสถานะที่กรอง")
            else:
                pm_display_cols = ["ticket_no", "report_date", "department", "equipment", "description", "technician", "status"]
                df_pm_view = df_pm_show[pm_display_cols].copy()
                df_pm_view.columns = ["เลขที่ใบงาน", "กำหนดวันที่ทำ", "แผนก", "อุปกรณ์/เครื่องจักร", "รายละเอียด PM", "ช่างผู้รับผิดชอบ", "สถานะ"]
                
                st.dataframe(apply_status_style(df_pm_view), use_container_width=True)

# =============================================================
# TAB 5: คลังอะไหล่ & ตั้งค่าระบบ
# =============================================================
with tab5:
    st.subheader("📦 จัดการสต็อกอะไหล่ & ตั้งค่าระบบ (Master Settings)")
    
    sub_tab1, sub_tab2 = st.tabs(["🧩 รายการอะไหล่ & สต็อก", "⚙️ จัดการข้อมูลหลัก (Master Data)"])
    
    with sub_tab1:
        st.markdown("#### 📊 บริหารจัดการคลังอะไหล่ซ่อมบำรุง")
        st.caption("สรุปข้อมูลอะไหล่ทั้งหมดที่เคยถูกบันทึกใช้จริงในระบบ เพื่ออำนวยความสะดวกในการสั่งซื้อเติมสต็อก")
        
        if not df.empty and "parts_used" in df.columns:
            df_parts_summary_tab5 = parse_parts_summary(df)
            if not df_parts_summary_tab5.empty:
                def get_unit_tab5(units_series):
                    unique_u = [u for u in units_series if u]
                    return unique_u[0] if unique_u else ""

                parts_agg = df_parts_summary_tab5.groupby("อะไหล่").agg(
                    total_qty=("qty_num", "sum"),
                    unit=("unit", get_unit_tab5),
                    times_used=("อะไหล่", "count")
                ).reset_index()

                def format_qty_display_tab5(row):
                    q = row["total_qty"]
                    q_str = f"{int(q)}" if q.is_integer() else f"{q:.2f}"
                    if row["unit"]:
                        return f"{q_str} {row['unit']}"
                    return f"{q_str}"

                parts_agg["จำนวนรวมที่ใช้"] = parts_agg.apply(format_qty_display_tab5, axis=1)
                parts_agg = parts_agg.sort_values(by="total_qty", ascending=False)
                
                show_parts_tab5 = parts_agg[["อะไหล่", "จำนวนรวมที่ใช้", "times_used"]].copy()
                show_parts_tab5.columns = ["รายการอะไหล่ / อุปกรณ์", "จำนวนรวมที่เบิกใช้แล้ว", "จำนวนงานซ่อมที่ใช้"]
                
                col_st1, col_st2 = st.columns([2, 1])
                with col_st1:
                    st.dataframe(show_parts_tab5, use_container_width=True, hide_index=True)
                with col_st2:
                    st.metric("📦 ชนิดอะไหล่ทั้งหมดในระบบ", f"{len(show_parts_tab5)} รายการ")
                    st.metric("🔁 รวมการเบิกใช้ทั้งหมด", f"{parts_agg['times_used'].sum()} ครั้ง")
            else:
                st.info("ยังไม่มีข้อมูลการบันทึกเบิกใช้อะไหล่ในระบบ")
        else:
            st.info("ยังไม่มีข้อมูลงานซ่อมในระบบ")

    with sub_tab2:
        st.markdown("#### 🛠️ ตั้งค่าข้อมูลหลักของระบบ (Master Data Overview)")
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            st.markdown("**🏢 รายชื่อแผนก / โซน ที่มีในระบบ:**")
            all_depts_current = list(dict.fromkeys(DEFAULT_DEPTS + [d for d in df["department"].dropna().unique().tolist() if d]))
            for d_idx, dept in enumerate(all_depts_current, 1):
                st.markdown(f"{d_idx}. {dept}")
            st.caption("💡 สามารถเพิ่มแผนกใหม่ได้ง่ายๆ ผ่านฟอร์มบันทึกแจ้งซ่อมใน Tab 1 และ Tab 2")
            
        with col_m2:
            st.markdown("**👨‍🔧 รายชื่อช่างซ่อมในระบบ (จากประวัติงาน):**")
            if not df.empty and "technician" in df.columns:
                techs = [t.strip() for t in df["technician"].dropna().unique().tolist() if str(t).strip() != ""]
                if techs:
                    for t_idx, t in enumerate(techs, 1):
                        st.markdown(f"{t_idx}. {t}")
                else:
                    st.write("ยังไม่มีประวัติการบันทึกชื่อช่างซ่อม")
            else:
                st.write("ยังไม่มีประวัติการบันทึกชื่อช่างซ่อม")
