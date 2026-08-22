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
        st.caption("ไม่มีไฟล์รูปหรือวิดีโอ")
        return
        
    st.markdown(f"**{title} ({len(media_list)} รายการ):**")
    
    MAX_COLS = 4
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
    elif val == "กำลังดำเนินการ":
        return "background-color: #cce5ff; color: #004085; font-weight: bold;"
    elif val == "รออะไหล่":
        return "background-color: #ffeba7; color: #855700; font-weight: bold;"
    elif val == "ยกเลิก":
        return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
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

# -------------------------------------------------------------
# Database Loader Functions
# -------------------------------------------------------------
def load_data_by_table(table_name="tickets", job_type_filter=None):
    if not supabase:
        return pd.DataFrame(columns=COLUMN_NAMES)
    try:
        res = supabase.table(table_name).select("*").execute()
        df = pd.DataFrame(res.data)
        if df.empty:
            return pd.DataFrame(columns=COLUMN_NAMES)
        for c in COLUMN_NAMES:
            if c not in df.columns:
                df[c] = ""
        if job_type_filter:
            df = df[df["job_type"] == job_type_filter]
        
        df["sort_dt"] = pd.to_datetime(df["report_date"].astype(str) + " " + df["report_time"].astype(str).fillna("00:00:00"), errors='coerce')
        df = df.sort_values(by=["sort_dt", "created_at"], ascending=[True, True]).drop(columns=["sort_dt"])
        return df
    except Exception:
        try:
            res = supabase.table("tickets").select("*").execute()
            df = pd.DataFrame(res.data)
            if df.empty:
                return pd.DataFrame(columns=COLUMN_NAMES)
            for c in COLUMN_NAMES:
                if c not in df.columns:
                    df[c] = ""
            if job_type_filter:
                df = df[df["job_type"] == job_type_filter]
            
            df["sort_dt"] = pd.to_datetime(df["report_date"].astype(str) + " " + df["report_time"].astype(str).fillna("00:00:00"), errors='coerce')
            df = df.sort_values(by=["sort_dt", "created_at"], ascending=[True, True]).drop(columns=["sort_dt"])
            return df
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
            return pd.DataFrame(columns=COLUMN_NAMES)

def save_data_to_supabase(primary_table, data):
    try:
        return supabase.table(primary_table).insert(data).execute()
    except Exception:
        return supabase.table("tickets").insert(data).execute()

def update_data_in_supabase(primary_table, data, record_id):
    try:
        return supabase.table(primary_table).update(data).eq("id", record_id).execute()
    except Exception:
        return supabase.table("tickets").update(data).eq("id", record_id).execute()

def generate_ticket_no(df, prefix="REP-"):
    now = get_thailand_now_dt()
    p_str = f"{prefix}{now.strftime('%Y%m%d')}-"
    if df.empty or "ticket_no" not in df.columns:
        return f"{p_str}001"
    
    today_tickets = df[df["ticket_no"].astype(str).str.startswith(p_str)]
    if today_tickets.empty:
        return f"{p_str}001"
    
    max_num = 0
    for t in today_tickets["ticket_no"].astype(str):
        try:
            num = int(t.split("-")[-1])
            if num > max_num:
                max_num = num
        except Exception:
            pass
    return f"{p_str}{max_num + 1:03d}"

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
# โหลดข้อมูลแยกส่วน
# -------------------------------------------------------------
df_repair = load_data_by_table("repair_tickets", job_type_filter="แจ้งซ่อม")
df_pm = load_data_by_table("pm_tickets", job_type_filter="PM")

# -------------------------------------------------------------
# Main App Layout (5 Tabs)
# -------------------------------------------------------------
st.title("🛠️ ระบบบันทึกงานแจ้งซ่อมบำรุง และ PM")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 บันทึกงานแจ้งซ่อม (Repair)",
    "⚙️ จัดการงานแจ้งซ่อม (Repair)",
    "📊 รายงาน & สถิติรวม",
    "📅 แผนงาน PM & บันทึกก่อนทำ (PM)",
    "✅ บันทึกผล PM & ตรวจสอบหลังทำ (PM)"
])

# =============================================================
# TAB 1: บันทึกงานแจ้งซ่อม (Repair Only)
# =============================================================
with tab1:
    st.subheader("📋 ฟอร์มบันทึกงานแจ้งซ่อมทั่วไป")
    
    default_ticket_no = generate_ticket_no(df_repair, prefix="REP-")
    existing_depts = df_repair["department"].dropna().unique().tolist() if not df_repair.empty else []
    all_depts = list(dict.fromkeys(DEFAULT_DEPTS + [d for d in existing_depts if d]))
    dept_options = all_depts + ["➕ พิมพ์ระบุแผนกใหม่..."]
    
    with st.form("repair_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            ticket_no = st.text_input("ลำดับที่ *", value=default_ticket_no, placeholder="เช่น REP-20260819-001")
        with col2:
            reporter = st.text_input("ชื่อผู้แจ้ง *")
            
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
            "📸/🎥 อัปโหลดรูปถ่ายหรือวิดีโอก่อนซ่อม (เลือกได้หลายไฟล์)", 
            type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
            accept_multiple_files=True,
            key="repair_media_b"
        )
        
        submitted = st.form_submit_button("💾 บันทึกใบแจ้งซ่อม", use_container_width=True)
        
        if submitted:
            if not ticket_no.strip() or not reporter.strip() or not department.strip() or not equipment.strip() or not description.strip():
                st.error("❌ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")
            elif not supabase:
                st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
            else:
                media_b64 = process_media_files(uploaded_media_b) if uploaded_media_b else ""
                created_at_str = datetime.combine(report_date, report_time).replace(tzinfo=THAILAND_TZ).isoformat()
                
                new_data = {
                    "ticket_no": ticket_no.strip(),
                    "reporter": reporter,
                    "job_type": "แจ้งซ่อม",
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
                    save_data_to_supabase("repair_tickets", new_data)
                    st.success(f"✅ บันทึกใบแจ้งซ่อมลำดับที่ **{ticket_no}** เรียบร้อยแล้ว!")
                    st.rerun()
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}")

# =============================================================
# TAB 2: จัดการงานแจ้งซ่อม (Repair Only)
# =============================================================
with tab2:
    st.subheader("⚙️ จัดการสถานะและอัปเดตงานแจ้งซ่อม")
    
    if df_repair.empty:
        st.info("ยังไม่มีข้อมูลใบแจ้งซ่อมในระบบ")
    else:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            status_filter = st.multiselect("กรองตามสถานะ", options=["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่", "เสร็จสิ้น", "ยกเลิก"], default=["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่", "ยกเลิก"])
        with col_f2:
            search_kw = st.text_input("🔍 ค้นหา (ลำดับที่ / เลขที่รับ / ชื่อผู้แจ้ง / อุปกรณ์)", "", key="repair_search")
            
        df_filtered = df_repair.copy()
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
            
        st.markdown(f"**รายการใบแจ้งซ่อม ({len(df_filtered)} รายการ):**")
        
        display_cols = [
            "ticket_no", "received_no", "reporter", "department", "equipment", 
            "description", "priority", "status", "report_date", "report_time", 
            "received_date", "received_time", "technician", "detected_symptom", "cause", "solution", 
            "completed_date", "completed_time"
        ]
        
        df_show = df_filtered[display_cols].copy()
        df_show.columns = [
            "ลำดับที่", "เลขที่รับ", "ผู้แจ้ง", "แผนก", "อุปกรณ์", 
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
            selected_ticket_no = st.selectbox("เลือกลำดับที่เพื่อจัดการ:", ticket_list, key="sel_rep_ticket")
            ticket = df_repair[df_repair["ticket_no"] == selected_ticket_no].iloc[0]
            
            with st.form("update_repair_form"):
                st.markdown("#### 1️⃣ ข้อมูลการแจ้งซ่อม (ฝั่งผู้แจ้ง)")
                col_e0, col_e1, col_e3, col_e4 = st.columns(4)
                with col_e0:
                    ticket_no_edit = st.text_input("ลำดับที่", value=str(ticket["ticket_no"] or ""))
                with col_e1:
                    reporter_edit = st.text_input("ผู้แจ้งซ่อม", value=str(ticket["reporter"] or ""))
                
                curr_ticket_dept = str(ticket["department"] or "")
                edit_dept_options = all_depts + ["➕ พิมพ์ระบุแผนกใหม่..."]
                curr_dept_idx = edit_dept_options.index(curr_ticket_dept) if curr_ticket_dept in edit_dept_options else len(edit_dept_options) - 1
                
                with col_e3:
                    dept_choice_edit = st.selectbox("แผนก / โซน", edit_dept_options, index=curr_dept_idx, key="edit_rep_dept")
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
                
                st.markdown("🕒 **วันและเวลาที่แจ้ง**")
                col_rd, col_rt = st.columns(2)
                
                now_dt_rep = get_thailand_now_dt()
                init_rep_date = parse_date(ticket["report_date"], now_dt_rep.date())
                init_rep_time = parse_time(ticket["report_time"], now_dt_rep.time().replace(microsecond=0))
                
                with col_rd:
                    report_date_edit = st.date_input("📅 วันที่แจ้ง", value=init_rep_date, key="edit_rep_date")
                with col_rt:
                    report_time_edit = st.time_input("⏰ เวลาที่แจ้ง", value=init_rep_time, key="edit_rep_time")
                
                display_media_gallery(ticket.get("image_before", ""), title="📸/🎥 สื่อประกอบก่อนซ่อมปัจจุบัน")
                
                uploaded_media_b_new = st.file_uploader(
                    "📸/🎥 เปลี่ยน/อัปโหลดเพิ่ม รูปหรือวิดีโอก่อนซ่อม",
                    type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
                    accept_multiple_files=True,
                    key="edit_rep_img_b"
                )
                
                st.markdown("---")
                st.markdown("#### 2️⃣ การดำเนินงานของช่าง (ฝั่งผู้ซ่อม)")
                
                curr_rcv_no = str(ticket.get("received_no", "") or "").strip()
                if not curr_rcv_no:
                    curr_rcv_no = generate_default_received_no(df_repair)
                    
                col_rcv1, col_rcv2, col_rcv3 = st.columns(3)
                with col_rcv1:
                    received_no_input = st.text_input("เลขที่รับงาน / ใบรับ", value=curr_rcv_no)
                
                init_rcv_date = parse_date(ticket.get("received_date"), now_dt_rep.date())
                init_rcv_time = parse_time(ticket.get("received_time"), now_dt_rep.time().replace(microsecond=0))
                
                with col_rcv2:
                    received_date_input = st.date_input("📅 วันที่รับงาน", value=init_rcv_date, key="rcv_rep_date")
                with col_rcv3:
                    received_time_input = st.time_input("⏰ เวลาที่รับงาน", value=init_rcv_time, key="rcv_rep_time")
                
                status_options = ["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่", "เสร็จสิ้น", "ยกเลิก"]
                curr_status = str(ticket["status"] or "รอดำเนินการ")
                status_idx = status_options.index(curr_status) if curr_status in status_options else 0
                
                col_u1, col_u2 = st.columns(2)
                with col_u1:
                    new_status = st.selectbox("สถานะงาน *", status_options, index=status_idx, key="rep_status_edit")
                with col_u2:
                    technician_name = st.text_input("ชื่อผู้ซ่อม / ช่างผู้รับผิดชอบ", value=str(ticket.get("technician", "") or ""))
                
                col_sec1, col_sec2 = st.columns(2)
                with col_sec1:
                    detected_symptom_input = st.text_area("🔍 อาการที่ตรวจพบ (Symptom Found)", value=str(ticket.get("detected_symptom", "") or ""), height=100)
                    cause_input = st.text_area("⚠️ สาเหตุของปัญหา / เหตุผลที่ยกเลิก", value=str(ticket.get("cause", "") or ""), height=100)
                with col_sec2:
                    solution_input = st.text_area("🛠️ การแก้ไข / วิธีดำเนินการ", value=str(ticket.get("solution", "") or ""), height=210)
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    parts_used = st.text_area("🧩 อะไหล่ที่ใช้", value=str(ticket.get("parts_used", "") or ""), height=100)
                with col_p2:
                    parts_qty = st.text_area("🔢 จำนวนอะไหล่", value=str(ticket.get("parts_qty", "") or ""), height=100)
                    
                st.markdown("🕒 **วันและเวลาซ่อมเสร็จ**")
                col_cd, col_ct = st.columns(2)
                
                init_comp_date = parse_date(ticket.get("completed_date"), now_dt_rep.date())
                init_comp_time = parse_time(ticket.get("completed_time"), now_dt_rep.time().replace(microsecond=0))
                
                with col_cd:
                    completed_date = st.date_input("📅 วันที่ซ่อมเสร็จ", value=init_comp_date, key="rep_comp_date")
                with col_ct:
                    completed_time = st.time_input("⏰ เวลาที่ซ่อมเสร็จ", value=init_comp_time, key="rep_comp_time")
                
                display_media_gallery(ticket.get("image_after", ""), title="📸/🎥 สื่อประกอบหลังซ่อมปัจจุบัน")
                
                uploaded_media_a_new = st.file_uploader(
                    "📸/🎥 อัปโหลด/เปลี่ยน รูปหรือวิดีโอหลังซ่อมเสร็จ",
                    type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
                    accept_multiple_files=True,
                    key="edit_rep_img_a"
                )
                
                update_submitted = st.form_submit_button("💾 บันทึกการอัปเดตงานซ่อม", use_container_width=True)
                
                if update_submitted:
                    if not supabase:
                        st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                    else:
                        img_before_b64 = process_media_files(uploaded_media_b_new) if uploaded_media_b_new else str(ticket.get("image_before", "") or "")
                        img_after_b64 = process_media_files(uploaded_media_a_new) if uploaded_media_a_new else str(ticket.get("image_after", "") or "")
                            
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
                            "job_type": "แจ้งซ่อม",
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
                            update_data_in_supabase("repair_tickets", update_data, ticket["id"])
                            st.success(f"✅ อัปเดตข้อมูลลำดับที่ **{ticket_no_edit}** เรียบร้อยแล้ว!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"เกิดข้อผิดพลาดในการอัปเดต: {e}")

# =============================================================
# TAB 3: รายงาน & สถิติรวม
# =============================================================
with tab3:
    st.subheader("📊 สรุปรายงานและสถิติภาพรวม")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        data_scope = st.selectbox("เลือกชุดข้อมูลที่ต้องการสรุป", ["งานแจ้งซ่อม (Tab 1-2)", "งาน PM (Tab 4-5)", "รวมทั้งหมด (แจ้งซ่อม + PM)"])
    
    if data_scope == "งานแจ้งซ่อม (Tab 1-2)":
        df_stats = df_repair.copy()
    elif data_scope == "งาน PM (Tab 4-5)":
        df_stats = df_pm.copy()
    else:
        df_stats = pd.concat([df_repair, df_pm], ignore_index=True)
        
    if df_stats.empty:
        st.info("ยังไม่มีข้อมูลสำหรับสรุปรายงานในหมวดนี้")
    else:
        now_date = get_thailand_now_dt().date()
        
        with col_s2:
            period_option = st.selectbox("ช่วงเวลาการดูข้อมูล", ["ทั้งหมด", "7 วันล่าสุด", "30 วันล่าสุด", "ปีปัจจุบัน", "กำหนดช่วงวันที่เอง"])
            
        df_stats["parsed_rep_date"] = pd.to_datetime(df_stats["report_date"], errors="coerce").dt.date
        
        if period_option == "7 วันล่าสุด":
            start_date = now_date - timedelta(days=7)
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "30 วันล่าสุด":
            start_date = now_date - timedelta(days=30)
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "ปีปัจจุบัน":
            start_date = datetime(now_date.year, 1, 1).date()
            df_stats = df_stats[(df_stats["parsed_rep_date"] >= start_date) & (df_stats["parsed_rep_date"] <= now_date)]
        elif period_option == "กำหนดช่วงวันที่เอง":
            custom_range = st.date_input("ระบุวันที่ (เริ่มต้น - สิ้นสุด)", value=[now_date - timedelta(days=30), now_date], key="stats_custom_range")
            if isinstance(custom_range, (list, tuple)) and len(custom_range) == 2:
                df_stats = df_stats[(df_stats["parsed_rep_date"] >= custom_range[0]) & (df_stats["parsed_rep_date"] <= custom_range[1])]
        
        if df_stats.empty:
            st.warning("⚠️ ไม่พบข้อมูลตามช่วงเวลาที่เลือก")
        else:
            def calc_repair_time(row):
                if row["status"] == "เสร็จสิ้น" and pd.notna(row.get("completed_date")):
                    try:
                        s_date = row['received_date'] if pd.notna(row.get('received_date')) and str(row.get('received_date')).strip() != "" else row['report_date']
                        s_time = row['received_time'] if pd.notna(row.get('received_time')) and str(row.get('received_time')).strip() != "" else row['report_time']
                        
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
            
            total_jobs = len(df_stats)
            done_jobs = len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
            pending_jobs = len(df_stats[df_stats["status"] == "รอดำเนินการ"])
            in_prog_jobs = len(df_stats[df_stats["status"] == "กำลังดำเนินการ"])
            outstanding_jobs = pending_jobs + in_prog_jobs
            
            valid_durations = df_stats["repair_duration"].dropna()
            avg_duration_str = format_timedelta(valid_durations.mean()) if not valid_durations.empty else "-"
            total_duration_str = format_timedelta(valid_durations.sum()) if not valid_durations.empty else "-"
                
            m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
            m1.metric("📋 งานทั้งหมด", f"{total_jobs} งาน")
            m2.metric("✅ เสร็จสิ้นแล้ว", f"{done_jobs} งาน")
            m3.metric("⚠️ งานค้างสะสม", f"{outstanding_jobs} งาน")
            m4.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
            m5.metric("🔄 กำลังซ่อม", f"{in_prog_jobs} งาน")
            m6.metric("⏱️ เวลาซ่อมรวม", total_duration_str)
            m7.metric("⏱️ เวลาเฉลี่ย/งาน", avg_duration_str)
            
            st.markdown("---")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("##### 🕒 กราฟงานค้างสะสมแยกตามอายุงาน")
                df_pending = df_stats[df_stats["status"].isin(["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่"])].copy()
                
                if df_pending.empty:
                    st.success("🎉 ไม่มีงานค้างสะสมในช่วงเวลาที่เลือก!")
                else:
                    df_pending["age_days"] = df_pending["report_date"].apply(lambda d: (now_date - pd.to_datetime(d).date()).days if pd.notna(d) else 0)
                    df_pending["age_group"] = df_pending["age_days"].apply(lambda d: "< 7 วัน" if d < 7 else ("7 - 15 วัน" if d <= 15 else ("16 - 30 วัน" if d <= 30 else "> 1 เดือน")))
                    
                    age_order = ["< 7 วัน", "7 - 15 วัน", "16 - 30 วัน", "> 1 เดือน"]
                    age_counts = df_pending["age_group"].value_counts().reindex(age_order, fill_value=0).reset_index()
                    age_counts.columns = ["ช่วงอายุงาน", "จำนวนงาน"]
                    
                    fig_aging = px.bar(age_counts, x="ช่วงอายุงาน", y="จำนวนงาน", text="จำนวนงาน", color="ช่วงอายุงาน",
                                       color_discrete_map={"< 7 วัน": "#2ecc71", "7 - 15 วัน": "#f1c40f", "16 - 30 วัน": "#e67e22", "> 1 เดือน": "#e74c3c"})
                    fig_aging.update_traces(textposition='outside')
                    st.plotly_chart(fig_aging, use_container_width=True)
                    
            with col_g2:
                st.markdown("##### 📌 สัดส่วนตามสถานะงาน")
                status_counts = df_stats["status"].value_counts().reset_index()
                status_counts.columns = ["สถานะ", "จำนวน"]
                fig_status = px.pie(status_counts, names="สถานะ", values="จำนวน", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_status, use_container_width=True)

# =============================================================
# TAB 4: แผนงาน PM & บันทึกก่อนทำ (PM Only)
# =============================================================
with tab4:
    st.subheader("📅 แผนงาน PM & บันทึกข้อมูลก่อนทำ (PM - Before Action)")
    st.caption("ระบบวางแผนการบำรุงรักษาเชิงป้องกัน (PM) และบันทึกรูปถ่าย/วิดีโอสภาพเครื่องจักรก่อนทำ PM (แยกจากงานแจ้งซ่อม)")
    
    col_pm1, col_pm2 = st.columns([1, 2])
    
    now_dt_pm = get_thailand_now_dt()
    
    with col_pm1:
        st.markdown("#### ➕ วางแผน / ออกใบงาน PM ใหม่")
        default_pm_no = generate_ticket_no(df_pm, prefix="PM-")
        
        with st.form("add_pm_plan_form", clear_on_submit=True):
            pm_no = st.text_input("ลำดับที่ PM *", value=default_pm_no)
            pm_equip = st.text_input("อุปกรณ์ / เครื่องจักร *", placeholder="เช่น เครื่องอัดอากาศ No.1")
            
            existing_depts_pm = df_pm["department"].dropna().unique().tolist() if not df_pm.empty else []
            all_depts_pm = list(dict.fromkeys(DEFAULT_DEPTS + [d for d in existing_depts_pm if d]))
            
            pm_dept = st.selectbox("แผนก / โซน *", all_depts_pm, key="pm_dept_sel")
            
            st.markdown("🕒 **วันและเวลาที่ตรวจพบ * **")
            col_pm_dd, col_pm_dt = st.columns(2)
            with col_pm_dd:
                pm_detected_date = st.date_input("📅 วันที่ตรวจพบ", value=now_dt_pm.date(), key="pm_det_date")
            with col_pm_dt:
                pm_detected_time = st.time_input("⏰ เวลาที่ตรวจพบ", value=now_dt_pm.time().replace(microsecond=0), key="pm_det_time")
                
            pm_note = st.text_area("รายละเอียดการตรวจเช็ก (Checklist)", placeholder="- เช็กน้ำมันเครื่อง\n- ทำความสะอาดฟิลเตอร์")
            
            uploaded_pm_media_before = st.file_uploader(
                "📸/🎥 รูปถ่ายหรือวิดีโอก่อนทำ PM", 
                type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
                accept_multiple_files=True,
                key="pm_media_b_upload"
            )
            
            btn_save_pm = st.form_submit_button("💾 บันทึกแผน PM (ก่อนทำ)", use_container_width=True)
            if btn_save_pm:
                if not pm_equip.strip() or not pm_no.strip():
                    st.error("❌ กรุณาระบุลำดับที่และชื่ออุปกรณ์/เครื่องจักร")
                elif not supabase:
                    st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                else:
                    pm_media_b64 = process_media_files(uploaded_pm_media_before) if uploaded_pm_media_before else ""
                    created_at_str = datetime.combine(pm_detected_date, pm_detected_time).replace(tzinfo=THAILAND_TZ).isoformat()
                    
                    new_pm_data = {
                        "ticket_no": pm_no.strip(),
                        "reporter": "ระบบวางแผน PM",
                        "job_type": "PM",
                        "department": pm_dept,
                        "equipment": pm_equip.strip(),
                        "description": pm_note.strip(),
                        "priority": "ปกติ",
                        "status": "รอดำเนินการ",
                        "report_date": str(pm_detected_date),
                        "report_time": pm_detected_time.strftime("%H:%M:%S"),
                        "created_at": created_at_str,
                        "image_before": pm_media_b64
                    }
                    try:
                        save_data_to_supabase("pm_tickets", new_pm_data)
                        st.success(f"✅ บันทึกแผน PM เรียบร้อย! ออกลำดับที่: **{pm_no}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

    with col_pm2:
        st.markdown("#### 📋 รายการงาน PM และสื่อประกอบก่อนทำ")
        if df_pm.empty:
            st.info("ยังไม่มีข้อมูลแผนงาน PM ในระบบ")
        else:
            pm_status_filter = st.multiselect("กรองสถานะ PM", ["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่", "เสร็จสิ้น", "ยกเลิก"], default=["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่"], key="pm_status_f")
            df_pm_show = df_pm[df_pm["status"].isin(pm_status_filter)]
            
            if df_pm_show.empty:
                st.warning("ไม่พบรายการ PM ตามสถานะที่กรอง")
            else:
                pm_display_cols = ["ticket_no", "report_date", "report_time", "department", "equipment", "description", "status"]
                df_pm_view = df_pm_show[pm_display_cols].copy()
                df_pm_view.columns = ["ลำดับที่", "วันที่ตรวจพบ", "เวลาที่ตรวจพบ", "แผนก", "อุปกรณ์/เครื่องจักร", "รายละเอียด PM", "สถานะ"]
                
                st.dataframe(apply_status_style(df_pm_view), use_container_width=True)

                st.markdown("---")
                st.markdown("#### 🔍 ตรวจสอบสื่อประกอบ (รูปถ่าย / วิดีโอ) **ก่อนทำ PM**")
                selected_pm_ticket = st.selectbox(
                    "เลือกลำดับที่ PM เพื่อดูรูปภาพ/วิดีโอก่อนทำ:", 
                    df_pm_show["ticket_no"].tolist(),
                    key="sel_pm_media_b_view"
                )
                
                if selected_pm_ticket:
                    pm_item = df_pm_show[df_pm_show["ticket_no"] == selected_pm_ticket].iloc[0]
                    display_media_gallery(pm_item.get("image_before", ""), title="📸/🎥 สื่อประกอบก่อนทำ PM (Before Action)")

# =============================================================
# TAB 5: บันทึกผล PM & ตรวจสอบหลังทำ (PM Only)
# =============================================================
with tab5:
    st.subheader("✅ บันทึกผล PM & ตรวจสอบงานหลังทำ (PM - After Action)")
    st.caption("บันทึกผลการทำ PM, รูปถ่าย/วิดีโอหลังทำเสร็จ และเปรียบเทียบรูปภาพ ก่อนทำ VS หลังทำ ของงาน PM")

    st_sub1, st_sub2, st_sub3 = st.tabs([
        "📝 บันทึกผลการทำ PM (หลังทำ)", 
        "📸 ตรวจสอบสื่อประกอบ (ก่อนทำ VS หลังทำ)",
        "📊 ตารางประวัติงาน PM ทั้งหมด"
    ])

    # Sub-tab 1: บันทึกผลการทำ PM
    with st_sub1:
        st.markdown("#### 🛠️ บันทึกผลการดำเนินงาน PM / ปิดงาน (หลังทำ)")
        
        if df_pm.empty:
            st.info("ยังไม่มีข้อมูลใบงาน PM ในระบบ")
        else:
            active_pm_tickets = df_pm[df_pm["status"].isin(["รอดำเนินการ", "กำลังดำเนินการ", "รออะไหล่"])]["ticket_no"].tolist()
            all_pm_tickets_list = df_pm["ticket_no"].tolist()
            
            selected_after_ticket = st.selectbox(
                "เลือกลำดับที่ PM เพื่อบันทึกผลหลังทำ:",
                options=active_pm_tickets if active_pm_tickets else all_pm_tickets_list,
                key="pm_after_ticket_sel"
            )
            
            if selected_after_ticket:
                target_item = df_pm[df_pm["ticket_no"] == selected_after_ticket].iloc[0]
                
                st.info(f"📌 **ลำดับที่:** {target_item.get('ticket_no')} | **อุปกรณ์:** {target_item.get('equipment')} | **แผนก:** {target_item.get('department')}")
                
                with st.form("pm_after_form"):
                    col_af1, col_af2 = st.columns(2)
                    with col_af1:
                        tech_name = st.text_input("ช่างผู้รับผิดชอบ / ผู้ตรวจเช็ก *", value=str(target_item.get("technician", "") or ""))
                        after_status = st.selectbox("สถานะหลังดำเนินงาน *", ["เสร็จสิ้น", "กำลังดำเนินการ", "รออะไหล่", "ยกเลิก"], index=0, key="pm_status_af")
                    with col_af2:
                        now_dt_after = get_thailand_now_dt()
                        init_c_date = parse_date(target_item.get("completed_date"), now_dt_after.date())
                        init_c_time = parse_time(target_item.get("completed_time"), now_dt_after.time().replace(microsecond=0))
                        
                        col_cd1, col_ct1 = st.columns(2)
                        with col_cd1:
                            comp_date_in = st.date_input("📅 วันที่ทำเสร็จ", value=init_c_date, key="pm_cd_in")
                        with col_ct1:
                            comp_time_in = st.time_input("⏰ เวลาที่ทำเสร็จ", value=init_c_time, key="pm_ct_in")
                            
                    col_af3, col_af4 = st.columns(2)
                    with col_af3:
                        symptom_after = st.text_area("🔍 อาการที่ตรวจพบ / สภาพการทำงาน", value=str(target_item.get("detected_symptom", "") or ""), height=100)
                        solution_after = st.text_area("🛠️ ผลการทำ PM / วิธีการแก้ไข (หลังทำ) *", value=str(target_item.get("solution", "") or ""), height=100)
                    with col_af4:
                        parts_after = st.text_area("🧩 อะไหล่/วัสดุอุปกรณ์ที่ใช้", value=str(target_item.get("parts_used", "") or ""), height=100)
                        qty_after = st.text_area("🔢 จำนวนอะไหล่", value=str(target_item.get("parts_qty", "") or ""), height=100)
                    
                    st.markdown("---")
                    st.markdown("#### 📸/🎥 อัปโหลดรูปภาพ / วิดีโอ **หลังทำ PM (After Action)**")
                    
                    display_media_gallery(target_item.get("image_after", ""), title="สื่อประกอบหลังทำปัจจุบัน")
                    
                    uploaded_pm_media_after = st.file_uploader(
                        "📸/🎥 อัปโหลดรูปถ่ายหรือวิดีโอผลงาน (หลังทำ PM)", 
                        type=["jpg", "jpeg", "png", "mp4", "mov", "avi", "mkv"],
                        accept_multiple_files=True,
                        key="pm_media_after_upload"
                    )
                    
                    btn_save_after = st.form_submit_button("💾 บันทึกผลการทำ PM", use_container_width=True)
                    
                    if btn_save_after:
                        if not tech_name.strip():
                            st.error("❌ กรุณาระบุชื่อช่างผู้รับผิดชอบ")
                        elif not supabase:
                            st.error("❌ ไม่สามารถเชื่อมต่อระบบฐานข้อมูลได้")
                        else:
                            media_after_b64 = process_media_files(uploaded_pm_media_after) if uploaded_pm_media_after else str(target_item.get("image_after", "") or "")
                                
                            c_at_str = None
                            c_d_str = None
                            c_t_str = None
                            
                            if after_status == "เสร็จสิ้น":
                                c_d_str = str(comp_date_in)
                                c_t_str = comp_time_in.strftime("%H:%M:%S")
                                c_at_str = datetime.combine(comp_date_in, comp_time_in).replace(tzinfo=THAILAND_TZ).isoformat()
                                
                            update_after_data = {
                                "technician": tech_name.strip(),
                                "status": after_status,
                                "detected_symptom": symptom_after,
                                "solution": solution_after,
                                "parts_used": parts_after,
                                "parts_qty": qty_after,
                                "completed_date": c_d_str,
                                "completed_time": c_t_str,
                                "completed_at": c_at_str,
                                "image_after": media_after_b64
                            }
                            
                            try:
                                update_data_in_supabase("pm_tickets", update_after_data, target_item["id"])
                                st.success(f"✅ บันทึกผลหลังทำ PM ลำดับที่ **{target_item.get('ticket_no')}** เรียบร้อยแล้ว!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"เกิดข้อผิดพลาดในการบันทึก: {e}")

    # Sub-tab 2: เปรียบเทียบ Before vs After
    with st_sub2:
        st.markdown("#### 📸 เปรียบเทียบสื่อประกอบ Before VS After ของงาน PM")
        
        if df_pm.empty:
            st.info("ยังไม่มีข้อมูลใบงาน PM ในระบบ")
        else:
            compare_ticket_no = st.selectbox(
                "เลอร์กลำดับที่ PM เพื่อเปรียบเทียบรูปภาพ/วิดีโอ:",
                df_pm["ticket_no"].tolist(),
                key="pm_compare_media_sel"
            )
            
            if compare_ticket_no:
                c_item = df_pm[df_pm["ticket_no"] == compare_ticket_no].iloc[0]
                st.markdown(f"**ลำดับที่:** `{c_item.get('ticket_no')}` | **อุปกรณ์:** {c_item.get('equipment')} | **สถานะ:** {c_item.get('status')}")
                
                col_comp1, col_comp2 = st.columns(2)
                with col_comp1:
                    st.markdown("### 🔴 ก่อนทำ PM (Before Action)")
                    display_media_gallery(c_item.get("image_before", ""), title="สื่อประกอบก่อนทำ PM")
                with col_comp2:
                    st.markdown("### 🟢 หลังทำ PM (After Action)")
                    display_media_gallery(c_item.get("image_after", ""), title="สื่อประกอบหลังทำ PM")

    # Sub-tab 3: สรุปประวัติงาน PM
    with st_sub3:
        st.markdown("#### 📜 ตารางสรุปผลงาน PM ทั้งหมด")
        if df_pm.empty:
            st.info("ยังไม่มีข้อมูลประวัติงาน PM")
        else:
            show_cols = ["ticket_no", "department", "equipment", "technician", "solution", "completed_date", "status"]
            df_pm_after_view = df_pm[show_cols].copy()
            df_pm_after_view.columns = ["ลำดับที่", "แผนก", "อุปกรณ์", "ช่างผู้ทำ", "ผลการทำ PM", "วันที่เสร็จ", "สถานะ"]
            st.dataframe(apply_status_style(df_pm_after_view), use_container_width=True)
