import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from PIL import Image
import io
import base64
import json
import plotly.express as px
from supabase import create_client

# Set Streamlit Page Config
st.set_page_config(page_title="ระบบแจ้งซ่อมบำรุง / PM", layout="wide")

# Supabase Credentials
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")

@st.cache_resource
def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase_client()

# Thailand Timezone
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
        return pd.DataFrame(columns=COLUMN_NAMES)
    try:
        res = supabase.table("maintenance_jobs").select("*").execute()
        df = pd.DataFrame(res.data)
        if df.empty:
            return pd.DataFrame(columns=COLUMN_NAMES)
        for col in COLUMN_NAMES:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูลจาก Supabase: {e}")
        return pd.DataFrame(columns=COLUMN_NAMES)

def save_data(row_dict):
    if not supabase:
        st.error("ไม่ได้เชื่อมต่อ Supabase")
        return False
    try:
        supabase.table("maintenance_jobs").insert(row_dict).execute()
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}")
        return False

def update_data(job_id, update_dict):
    if not supabase:
        st.error("ไม่ได้เชื่อมต่อ Supabase")
        return False
    try:
        supabase.table("maintenance_jobs").update(update_dict).eq("id", job_id).execute()
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอัปเดตข้อมูล: {e}")
        return False

def delete_data(job_id):
    if not supabase:
        st.error("ไม่ได้เชื่อมต่อ Supabase")
        return False
    try:
        supabase.table("maintenance_jobs").delete().eq("id", job_id).execute()
        return True
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการลบข้อมูล: {e}")
        return False

# Main App Layout
st.title("🛠️ ระบบแจ้งซ่อมบำรุง / PM (Maintenance System)")

df = load_data()

tab1, tab2, tab3 = st.tabs(["📝 แจ้งซ่อมใหม่", "📋 รายการและอัปเดตงาน", "📊 รายงาน & สถิติ"])

# --- TAB 1: NEW TICKET ---
with tab1:
    st.header("แบบฟอร์มแจ้งซ่อม / PM")
    with st.form("repair_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            reporter = st.text_input("ผู้แจ้งซ่อม *")
            job_type = st.selectbox("ประเภทงาน *", ["งานซ่อมทั่วไป", "PM (บำรุงรักษาเชิงป้องกัน)", "ปรับปรุง/แก้ไข"])
            
            dept_options = list(set(DEFAULT_DEPTS + [d for d in df["department"].dropna().unique() if d]))
            department = st.selectbox("แผนก/โซน *", dept_options)
            
        with c2:
            equipment = st.text_input("เครื่องจักร / อุปกรณ์ *")
            priority = st.selectbox("ความเร่งด่วน *", ["ปกติ", "ด่วน", "ด่วนที่สุด"])
            uploaded_files = st.file_uploader("รูปภาพประกอบก่อนซ่อม (แนบได้หลายรูป)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
            
        description = st.text_area("รายละเอียดอาการเสีย / งาน PM *")
        
        submitted = st.form_submit_button("🚀 บันทึกการแจ้งซ่อม", use_container_width=True)
        
        if submitted:
            if not reporter or not equipment or not description:
                st.error("กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")
            else:
                now_dt = get_thailand_now_dt()
                ticket_no = f"TK-{now_dt.strftime('%Y%m%d%H%M%S')}"
                b64_img = compress_multiple_to_json(uploaded_files) if uploaded_files else ""
                
                new_row = {
                    "ticket_no": ticket_no,
                    "reporter": reporter,
                    "job_type": job_type,
                    "department": department,
                    "equipment": equipment,
                    "description": description,
                    "priority": priority,
                    "status": "รอดำเนินการ",
                    "report_date": str(now_dt.date()),
                    "report_time": now_dt.strftime("%H:%M:%S"),
                    "created_at": now_dt.isoformat(),
                    "image_before": b64_img,
                    "received_no": "",
                    "received_date": "",
                    "received_time": "",
                    "technician": "",
                    "cause": "",
                    "solution": "",
                    "parts_used": "",
                    "parts_qty": "",
                    "completed_date": "",
                    "completed_time": "",
                    "completed_at": "",
                    "image_after": ""
                }
                
                if save_data(new_row):
                    st.success(f"บันทึกข้อมูลเรียบร้อยแล้ว! รหัสใบแจ้งซ่อม: {ticket_no}")
                    st.rerun()

# --- TAB 2: LIST & UPDATE ---
with tab2:
    st.header("รายการแจ้งซ่อมและอัปเดตสถานะ")
    if df.empty:
        st.info("ยังไม่มีข้อมูลการแจ้งซ่อม")
    else:
        # Filter Status
        status_options = ["ทั้งหมด", "รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"]
        selected_status = st.selectbox("กรองตามสถานะงาน:", status_options)
        
        df_filtered = df.copy()
        if selected_status != "ทั้งหมด":
            df_filtered = df_filtered[df_filtered["status"] == selected_status]
            
        # Select Job to update
        job_list = [f"{row['ticket_no']} | {row['equipment']} ({row['status']})" for _, row in df_filtered.iterrows()]
        
        if job_list:
            selected_job_str = st.selectbox("เลือกงานที่ต้องการดู/อัปเดต:", job_list)
            selected_ticket = selected_job_str.split(" | ")[0]
            job_data = df[df["ticket_no"] == selected_ticket].iloc[0]
            
            st.divider()
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.subheader("📋 รายละเอียดงานแจ้งซ่อม")
                st.write(f"**รหัส:** {job_data['ticket_no']}")
                st.write(f"**ผู้แจ้ง:** {job_data['reporter']}")
                st.write(f"**ประเภท:** {job_data['job_type']}")
                st.write(f"**แผนก:** {job_data['department']}")
                st.write(f"**เครื่องจักร:** {job_data['equipment']}")
                st.write(f"**ความเร่งด่วน:** {job_data['priority']}")
                st.write(f"**สถานะปัจจุบัน:** {job_data['status']}")
                st.write(f"**วันที่แจ้ง:** {job_data['report_date']} {job_data['report_time']}")
                st.write(f"**รายละเอียด:** {job_data['description']}")
                
                if job_data['received_no']:
                    st.write(f"**เลขที่รับงาน:** {job_data['received_no']}")
                    st.write(f"**วันที่รับงาน:** {job_data['received_date']} {job_data['received_time']}")
                    st.write(f"**ช่างผู้รับผิดชอบ:** {job_data['technician']}")
                    
                display_image_gallery(job_data.get('image_before'), "🖼️ รูปถ่ายก่อนซ่อม")
                
                if job_data['status'] == "เสร็จสิ้น":
                    st.write(f"**วันที่เสร็จ:** {job_data['completed_date']} {job_data['completed_time']}")
                    st.write(f"**สาเหตุ:** {job_data['cause']}")
                    st.write(f"**การแก้ไข:** {job_data['solution']}")
                    st.write(f"**อะไหล่ที่ใช้:** {job_data['parts_used']} (จำนวน: {job_data['parts_qty']})")
                    display_image_gallery(job_data.get('image_after'), "🖼️ รูปถ่ายหลังซ่อม")
                    
            with col_right:
                st.subheader("✏️ อัปเดตสถานะและข้อมูลการซ่อม")
                with st.form("update_form"):
                    new_status = st.selectbox("เปลี่ยนสถานะ:", ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"], 
                                              index=["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"].index(job_data['status']))
                    
                    now_dt = get_thailand_now_dt()
                    def_date = now_dt.date()
                    def_time = now_dt.time()
                    
                    st.markdown("---")
                    st.write("**ข้อมูลการรับงาน (เมื่อเปลี่ยนเป็น 'กำลังดำเนินการ')**")
                    rec_no = st.text_input("เลขที่รับงาน / ใบสั่งซ่อม", value=str(job_data['received_no'] or ""))
                    rec_date = st.date_input("วันที่รับงาน", value=parse_date(job_data['received_date'], def_date))
                    rec_time = st.time_input("เวลาที่รับงาน", value=parse_time(job_data['received_time'], def_time))
                    tech_name = st.text_input("ชื่อช่างผู้รับผิดชอบ", value=str(job_data['technician'] or ""))
                    
                    st.markdown("---")
                    st.write("**ข้อมูลการซ่อมเสร็จ (เมื่อเปลี่ยนเป็น 'เสร็จสิ้น')**")
                    comp_date = st.date_input("วันที่ซ่อมเสร็จ", value=parse_date(job_data['completed_date'], def_date))
                    comp_time = st.time_input("เวลาที่ซ่อมเสร็จ", value=parse_time(job_data['completed_time'], def_time))
                    cause = st.text_area("สาเหตุของปัญหา", value=str(job_data['cause'] or ""))
                    solution = st.text_area("วิธีแก้ไขปัญหา", value=str(job_data['solution'] or ""))
                    parts_used = st.text_input("อะไหล่/อุปกรณ์ที่ใช้", value=str(job_data['parts_used'] or ""))
                    parts_qty = st.text_input("จำนวนอะไหล่", value=str(job_data['parts_qty'] or ""))
                    after_files = st.file_uploader("รูปภาพหลังซ่อม (แนบได้หลายรูป)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
                    
                    btn_update = st.form_submit_button("💾 อัปเดตข้อมูล", use_container_width=True)
                    
                    if btn_update:
                        up_dict = {
                            "status": new_status,
                            "received_no": rec_no,
                            "received_date": str(rec_date),
                            "received_time": rec_time.strftime("%H:%M:%S"),
                            "technician": tech_name,
                            "cause": cause,
                            "solution": solution,
                            "parts_used": parts_used,
                            "parts_qty": parts_qty
                        }
                        
                        if new_status == "เสร็จสิ้น":
                            up_dict["completed_date"] = str(comp_date)
                            up_dict["completed_time"] = comp_time.strftime("%H:%M:%S")
                            up_dict["completed_at"] = f"{comp_date}T{comp_time.strftime('%H:%M:%S')}"
                            
                            if after_files:
                                b64_after = compress_multiple_to_json(after_files)
                                if b64_after:
                                    up_dict["image_after"] = b64_after
                                    
                        if update_data(job_data["id"], up_dict):
                            st.success("อัปเดตข้อมูลสำเร็จ!")
                            st.rerun()

# --- TAB 3: STATS & REPORTS ---
with tab3:
    st.header("📊 รายงานสรุปสถิติการแจ้งซ่อม")
    
    if df.empty:
        st.info("ยังไม่มีข้อมูลสำหรับประมวลผลสถิติ")
    else:
        # Filter
        col1, col2 = st.columns(2)
        with col1:
            dept_filter = st.multiselect("กรองตามแผนก:", options=list(df["department"].unique()), default=list(df["department"].unique()))
        with col2:
            status_filter = st.multiselect("กรองตามสถานะ:", options=list(df["status"].unique()), default=list(df["status"].unique()))
            
        df_stats = df[(df["department"].isin(dept_filter)) & (df["status"].isin(status_filter))].copy()
        
        # Calculations
        total_jobs = len(df_stats)
        done_jobs = len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
        pending_jobs = len(df_stats[df_stats["status"] == "รอดำเนินการ"])
        in_prog_jobs = len(df_stats[df_stats["status"] == "กำลังดำเนินการ"])
        outstanding_jobs = pending_jobs + in_prog_jobs
        
        # คำนวณระยะเวลาซ่อม (คิดจากเวลาที่รับงานจนถึงเวลาที่เสร็จ หากไม่มีเวลาที่รับงานให้ใช้เวลาแจ้งซ่อมแทน)
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
        
        valid_durations = df_stats["repair_duration"].dropna()
        avg_duration_str = "-"
        total_duration_str = "-"
        if not valid_durations.empty:
            avg_td = valid_durations.mean()
            avg_duration_str = format_timedelta(avg_td)
            
            total_td = valid_durations.sum()
            total_duration_str = format_timedelta(total_td)
            
        # Display Metrics
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        m1.metric("📋 งานทั้งหมด", f"{total_jobs} งาน")
        m2.metric("✅ เสร็จสิ้นแล้ว", f"{done_jobs} งาน")
        m3.metric("⚠️ งานค้างสะสม", f"{outstanding_jobs} งาน")
        m4.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
        m5.metric("🔄 กำลังซ่อม", f"{in_prog_jobs} งาน")
        m6.metric("⏱️ เวลาซ่อมรวมทั้งหมด", total_duration_str)
        m7.metric("⏱️ เวลาซ่อมเฉลี่ย", avg_duration_str)
        
        st.divider()
        
        # Charts
        c_chart1, c_chart2 = st.columns(2)
        with c_chart1:
            st.subheader("📊 จำนวนงานแยกตามแผนก")
            if not df_stats.empty:
                fig_dept = px.bar(df_stats['department'].value_counts().reset_index(), 
                                  x='department', y='count', labels={'department': 'แผนก', 'count': 'จำนวนงาน'},
                                  color='department')
                st.plotly_chart(fig_dept, use_container_width=True)
                
        with c_chart2:
            st.subheader("🍰 สัดส่วนสถานะงาน")
            if not df_stats.empty:
                fig_status = px.pie(df_stats, names='status', title='สัดส่วนสถานะงานทั้งหมด', hole=0.4)
                st.plotly_chart(fig_status, use_container_width=True)
                # คำนวณระยะเวลาซ่อม (คิดจากเวลาที่รับงานจนถึงเวลาที่เสร็จ)
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
        
        valid_durations = df_stats["repair_duration"].dropna()
        avg_duration_str = "-"
        total_duration_str = "-"
        if not valid_durations.empty:
            avg_td = valid_durations.mean()
            avg_duration_str = format_timedelta(avg_td)
            total_td = valid_durations.sum()                  # 🟢 รวมเวลาซ่อมทั้งหมด
            total_duration_str = format_timedelta(total_td)   # 🟢 แปลงรูปแบบวัน/ชม./นาที
            
        # Display Metrics (ขยายเป็น 7 คอลัมน์)
        m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
        m1.metric("📋 งานทั้งหมด", f"{total_jobs} งาน")
        m2.metric("✅ เสร็จสิ้นแล้ว", f"{done_jobs} งาน")
        m3.metric("⚠️ งานค้างสะสม", f"{outstanding_jobs} งาน")
        m4.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
        m5.metric("🔄 กำลังซ่อม", f"{in_prog_jobs} งาน")
        m6.metric("⏱️ เวลาซ่อมรวมทั้งหมด", total_duration_str) # 🟢 แสดงเวลารวม
        m7.metric("⏱️ เวลาซ่อมเฉลี่ย", avg_duration_str)      # 🟢 แสดงเวลาเฉลี่ย
