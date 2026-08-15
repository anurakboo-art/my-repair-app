import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import io
import base64
import plotly.express as px

# =============================================================================
# 1. การตั้งค่าหน้าเว็บ (Page Configuration)
# =============================================================================
st.set_page_config(
    page_title="ระบบแจ้งซ่อมและติดตามงานซ่อม (E-Maintenance System)",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# 2. ฟังก์ชันช่วยงาน (Helper Functions)
# =============================================================================
def image_to_base64(uploaded_file):
    """แปลงไฟล์ภาพที่อัปโหลดเป็นข้อความ Base64"""
    if uploaded_file is not None:
        try:
            image = Image.open(uploaded_file)
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception:
            return ""
    return ""

def display_image_gallery(base64_str, title="📸 รูปถ่าย"):
    """แสดงรูปถ่ายจาก Base64"""
    st.markdown(f"**{title}**")
    if base64_str and isinstance(base64_str, str) and len(base64_str) > 10:
        try:
            img_bytes = base64.b64decode(base64_str)
            image = Image.open(io.BytesIO(img_bytes))
            st.image(image, use_container_width=True)
        except Exception:
            st.warning("⚠️ ไม่สามารถเปิดรูปถ่ายได้")
    else:
        st.info("📷 ไม่มีรูปถ่าย")

def apply_status_style(df_input):
    """ใส่สีเน้นไฮไลต์ตามสถานะงานซ่อม"""
    def highlight_status(val):
        if val == "รอดำเนินการ":
            return 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
        elif val == "กำลังดำเนินการ":
            return 'background-color: #fff3cd; color: #856404; font-weight: bold;'
        elif val == "เสร็จสิ้นแล้ว":
            return 'background-color: #d4edda; color: #155724; font-weight: bold;'
        elif val == "ยกเลิก":
            return 'background-color: #e2e3e5; color: #383d41; font-weight: bold;'
        return ''
    
    if "สถานะ" in df_input.columns:
        return df_input.style.map(highlight_status, subset=['สถานะ'])
    return df_input

# =============================================================================
# 3. เริ่มต้นสร้างข้อมูลจำลองใน Session State (Mock Data Initializer)
# =============================================================================
if "maintenance_data" not in st.session_state:
    st.session_state.maintenance_data = pd.DataFrame([
        {
            "id": "1",
            "ticket_no": "REP-20260815-001",
            "reporter": "สมชาย ใจดี",
            "job_type": "แจ้งซ่อมทั่วไป",
            "department": "ฝ่ายผลิต (สีฝุ่น)",
            "equipment": "Conveyor Line 1",
            "description": "มอเตอร์มีเสียงดังผิดปกติและเกิดความร้อนสูง",
            "priority": "ด่วน",
            "status": "กำลังดำเนินการ",
            "report_date": "2026-08-15",
            "report_time": "09:00:00",
            "created_at": "2026-08-15T09:00:00",
            "image_before": "",
            "received_no": "RCV-20260815-001",
            "received_date": "2026-08-15",
            "received_time": "09:30:00",
            "technician": "ช่างวิชัย",
            "cause": "สายพานตึงเกินไป และตลับลูกปืนเริ่มเสื่อมสภาพ",
            "solution": "ปรับความตึงสายพาน และหยอดอัดจาระบีลูกปืน",
            "parts_used": "จาระบีทนความร้อน SKF",
            "parts_qty": "1 กระปุก",
            "completed_date": "",
            "completed_time": "",
            "completed_at": "",
            "image_after": ""
        },
        {
            "id": "2",
            "ticket_no": "REP-20260814-002",
            "reporter": "สมหญิง รักดี",
            "job_type": "แจ้งซ่อมด่วน",
            "department": "คลังสินค้า",
            "equipment": "Forklift #02",
            "description": "ระบบไฮดรอลิกยกไม่ขึ้น รั่วซึม",
            "priority": "ด่วนที่สุด",
            "status": "เสร็จสิ้นแล้ว",
            "report_date": "2026-08-14",
            "report_time": "13:15:00",
            "created_at": "2026-08-14T13:15:00",
            "image_before": "",
            "received_no": "RCV-20260814-002",
            "received_date": "2026-08-14",
            "received_time": "13:30:00",
            "technician": "ช่างสมศักดิ์",
            "cause": "ซีลยางไฮดรอลิกเสื่อมสภาพตามอายุใช้งาน",
            "solution": "เปลี่ยนชุดซีลยางไฮดรอลิกใหม่ และเติมน้ำมันไฮดรอลิก",
            "parts_used": "Hydraulic Seal Kit, น้ำมัน ISO VG 46",
            "parts_qty": "1 ชุด, 5 ลิตร",
            "completed_date": "2026-08-14",
            "completed_time": "16:45:00",
            "completed_at": "2026-08-14T16:45:00",
            "image_after": ""
        },
        {
            "id": "3",
            "ticket_no": "REP-20260815-003",
            "reporter": "อนันต์ มีสุข",
            "job_type": "แจ้งซ่อมทั่วไป",
            "department": "ฝ่ายสำนักงาน",
            "equipment": "เครื่องปรับอากาศ ห้องประชุม A",
            "description": "แอร์ไม่เย็น มีแต่ลมร้อน",
            "priority": "ปกติ",
            "status": "รอดำเนินการ",
            "report_date": "2026-08-15",
            "report_time": "10:30:00",
            "created_at": "2026-08-15T10:30:00",
            "image_before": "",
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
    ])

# ตัวแปร DataFrame หลักของระบบ
df = st.session_state.maintenance_data

# =============================================================================
# 4. ส่วนหัวของโปรแกรม (Header Section)
# =============================================================================
st.title("🛠️ ระบบแจ้งซ่อมและติดตามงานซ่อมออนไลน์ (E-Maintenance)")
st.caption("ระบบจัดการใบแจ้งซ่อม ติดตามสถานะงานซ่อม และวิเคราะห์สถิติการบำรุงรักษาโรงงาน")

tab1, tab2, tab3 = st.tabs([
    "📝 1. แจ้งซ่อม (New Ticket)",
    "⚙️ 2. ติดตาม & อัปเดตสถานะงานซ่อม (Track & Update)",
    "📊 3. รายงาน & สถิติ (Reports & Analytics)"
])

# =============================================================================
# TAB 1: ฟอร์มแจ้งซ่อม (Create New Maintenance Ticket)
# =============================================================================
with tab1:
    st.header("📝 แบบฟอร์มบันทึกการแจ้งซ่อม")
    st.write("กรุณากรอกข้อมูลการแจ้งซ่อมให้ครบถ้วนเพื่อส่งเรื่องให้ทีมช่างดำเนินการ")
    
    with st.form("repair_request_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            reporter_name = st.text_input("👤 ชื่อผู้แจ้งซ่อม *", placeholder="เช่น สมชาย ใจดี")
            job_type = st.selectbox("🏷️ ประเภทงาน *", ["แจ้งซ่อมทั่วไป", "แจ้งซ่อมด่วน", "บำรุงรักษาเชิงป้องกัน (PM)", "ปรับปรุง/ดัดแปลง"])
            department = st.selectbox("🏢 แผนก/ฝ่ายที่แจ้ง *", ["ฝ่ายผลิต (สีฝุ่น)", "ฝ่ายผลิต (ชุบ)", "คลังสินค้า", "ฝ่ายสำนักงาน", "ฝ่ายจัดซื้อ", "ฝ่าย QC"])
            equipment = st.text_input("⚙️ อุปกรณ์ / เครื่องจักรที่ชำรุด *", placeholder="เช่น Conveyor Line 1, เครื่องปั๊มน้ำ #2")
            
        with col2:
            priority = st.select_slider("🚨 ระดับความเร่งด่วน *", options=["ปกติ", "ด่วน", "ด่วนที่สุด"], value="ปกติ")
            report_date = st.date_input("📅 วันที่แจ้ง", value=datetime.now())
            report_time = st.time_input("⏰ เวลาที่แจ้ง", value=datetime.now().time())
            before_image_file = st.file_uploader("📸 รูปถ่ายก่อนซ่อม / รูปอาการเสีย (ถ้ามี)", type=["jpg", "png", "jpeg"])
            
        description = st.text_area("📝 รายละเอียดอาการเสีย / ปัญหาที่พบ *", placeholder="ระบุอาการเสียโดยละเอียด เช่น มีเสียงดัง ความร้อนสูง น้ำมันรั่วซึม...")
        
        submitted = st.form_submit_button("🚀 บันทึกส่งแจ้งซ่อม", use_container_width=True)
        
        if submitted:
            if not reporter_name or not equipment or not description:
                st.error("❌ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")
            else:
                # เจนเนอเรต Ticket Number
                today_str = datetime.now().strftime("%Y%m%d")
                new_id = str(len(st.session_state.maintenance_data) + 1)
                ticket_no = f"REP-{today_str}-{new_id.zfill(3)}"
                
                # แปลงไฟล์รูปภาพเป็น Base64
                img_b64 = image_to_base64(before_image_file)
                
                # สร้าง record ใหม่
                new_record = {
                    "id": new_id,
                    "ticket_no": ticket_no,
                    "reporter": reporter_name,
                    "job_type": job_type,
                    "department": department,
                    "equipment": equipment,
                    "description": description,
                    "priority": priority,
                    "status": "รอดำเนินการ",
                    "report_date": report_date.strftime("%Y-%m-%d"),
                    "report_time": report_time.strftime("%H:%M:%S"),
                    "created_at": datetime.now().isoformat(),
                    "image_before": img_b64,
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
                
                # บันทึกลง Session State
                st.session_state.maintenance_data = pd.concat([st.session_state.maintenance_data, pd.DataFrame([new_record])], ignore_index=True)
                st.success(f"🎉 บันทึกการแจ้งซ่อมเรียบร้อยแล้ว! หมายเลข Ticket: **{ticket_no}**")

# =============================================================================
# TAB 2: ติดตาม & อัปเดตสถานะงานซ่อม (Track & Update Work Orders)
# =============================================================================
with tab2:
    st.header("⚙️ ตารางติดตามและบันทึกการซ่อมบำรุง")
    
    # ตัวกรองข้อมูลงานซ่อม
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        status_filter = st.multiselect("📌 กรองตามสถานะ:", ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้นแล้ว", "ยกเลิก"], default=["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้นแล้ว"])
    with col_f2:
        dept_filter = st.selectbox("🏢 กรองตามแผนก:", ["ทั้งหมด"] + list(df["department"].unique()))
    with col_f3:
        search_kw = st.text_input("🔍 ค้นหา (Ticket / ผู้แจ้ง / อุปกรณ์):", placeholder="พิมพ์คำค้นหา...")
        
    # กรอง Dataframe
    df_show = df.copy()
    if status_filter:
        df_show = df_show[df_show["status"].isin(status_filter)]
    if dept_filter != "ทั้งหมด":
        df_show = df_show[df_show["department"] == dept_filter]
    if search_kw:
        df_show = df_show[
            df_show["ticket_no"].str.contains(search_kw, case=False, na=False) |
            df_show["reporter"].str.contains(search_kw, case=False, na=False) |
            df_show["equipment"].str.contains(search_kw, case=False, na=False)
        ]

    # แสดงตาราง Master Data
    st.markdown("#### 📋 รายการใบแจ้งซ่อมในระบบ")
    display_cols = ["ticket_no", "report_date", "reporter", "department", "equipment", "priority", "status", "technician"]
    df_table_view = df_show[display_cols].copy()
    df_table_view.columns = ["เลข Ticket", "วันที่แจ้ง", "ผู้แจ้ง", "แผนก", "อุปกรณ์", "ความเร่งด่วน", "สถานะ", "ช่างรับผิดชอบ"]
    
    st.dataframe(apply_status_style(df_table_view), use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # 🛠️ ฟอร์มบันทึกอัปเดตงานซ่อมสำหรับช่าง
    st.markdown("### 👨‍🔧 ปรับปรุงสถานะ & บันทึกผลการซ่อม")
    
    if df.empty:
        st.info("ไม่มีรายการงานซ่อมในระบบ")
    else:
        ticket_options = df["ticket_no"].tolist()
        selected_ticket = st.selectbox("เลือก Ticket ที่ต้องการปรับปรุงสถานะ:", options=ticket_options)
        
        # ดึงข้อมูล row ปัจจุบัน
        curr_row = df[df["ticket_no"] == selected_ticket].iloc[0]
        curr_idx = df[df["ticket_no"] == selected_ticket].index[0]
        
        with st.form("update_repair_form"):
            st.info(f"📌 กำลังปรับปรุงข้อมูลรายการ: **{curr_row['ticket_no']}** ({curr_row['equipment']} - แจ้งโดย {curr_row['reporter']})")
            
            u_col1, u_col2 = st.columns(2)
            with u_col1:
                new_status = st.selectbox("📌 อัปเดตสถานะงาน *", ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้นแล้ว", "ยกเลิก"], index=["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้นแล้ว", "ยกเลิก"].index(curr_row["status"]))
                tech_name = st.text_input("👨‍🔧 ช่างผู้รับผิดชอบ *", value=curr_row["technician"] or "")
                parts_used = st.text_input("🔩 อะไหล่ที่ใช้", value=curr_row["parts_used"] or "", placeholder="เช่น ลูกปืน SKF 6204")
                parts_qty = st.text_input("🔢 จำนวนอะไหล่", value=curr_row["parts_qty"] or "", placeholder="เช่น 2 ชิ้น")
                
            with u_col2:
                comp_date = st.date_input("📅 วันที่ซ่อมเสร็จ", value=datetime.now() if not curr_row["completed_date"] else datetime.strptime(curr_row["completed_date"], "%Y-%m-%d"))
                comp_time = st.time_input("⏰ เวลาที่ซ่อมเสร็จ", value=datetime.now().time() if not curr_row["completed_time"] else datetime.strptime(curr_row["completed_time"], "%H:%M:%S").time())
                after_image_file = st.file_uploader("📸 รูปถ่ายหลังซ่อมเสร็จ (After)", type=["jpg", "png", "jpeg"])
                
            cause = st.text_area("🛠️ สาเหตุของปัญหา", value=curr_row["cause"] or "", placeholder="ระบุสาเหตุที่ตรวจพบ...")
            solution = st.text_area("🔧 วิธีการแก้ไข / งานที่ปฏิบัติ", value=curr_row["solution"] or "", placeholder="ระบุวิธีการแก้ไข...")
            
            btn_update = st.form_submit_button("💾 บันทึกการปรับปรุงข้อมูล", use_container_width=True)
            
            if btn_update:
                st.session_state.maintenance_data.at[curr_idx, "status"] = new_status
                st.session_state.maintenance_data.at[curr_idx, "technician"] = tech_name
                st.session_state.maintenance_data.at[curr_idx, "cause"] = cause
                st.session_state.maintenance_data.at[curr_idx, "solution"] = solution
                st.session_state.maintenance_data.at[curr_idx, "parts_used"] = parts_used
                st.session_state.maintenance_data.at[curr_idx, "parts_qty"] = parts_qty
                
                if new_status == "เสร็จสิ้นแล้ว":
                    st.session_state.maintenance_data.at[curr_idx, "completed_date"] = comp_date.strftime("%Y-%m-%d")
                    st.session_state.maintenance_data.at[curr_idx, "completed_time"] = comp_time.strftime("%H:%M:%S")
                    st.session_state.maintenance_data.at[curr_idx, "completed_at"] = f"{comp_date.strftime('%Y-%m-%d')}T{comp_time.strftime('%H:%M:%S')}"
                
                if after_image_file is not None:
                    st.session_state.maintenance_data.at[curr_idx, "image_after"] = image_to_base64(after_image_file)
                    
                st.success(f"✅ ปรับปรุงสถานะ Ticket **{selected_ticket}** เป็น '{new_status}' เรียบร้อยแล้ว!")
                st.rerun()

# =============================================================================
# TAB 3: รายงาน & สถิติ (Reports & Analytics)
# =============================================================================
with tab3:
    st.header("📊 รายงานสรุปและสถิติการซ่อมบำรุง")
    
    if df.empty:
        st.info("ยังไม่มีข้อมูลแจ้งซ่อมในระบบ")
    else:
        # 1. ช่วงเวลาที่ต้องการสรุปข้อมูล (Period Filter)
        col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
        with col_p1:
            period_choice = st.selectbox(
                "🗓️ เลือกช่วงเวลาสรุปรายงาน:",
                ["ทั้งหมด", "7 วันล่าสุด", "30 วันล่าสุด", "ปีปัจจุบัน", "กำหนดเอง (Custom Range)"],
                key="tab3_period_choice"
            )
        
        df_filtered = df.copy()
        
        # การแปลงวันที่สำหรับกรองช่วงเวลา
        if period_choice != "ทั้งหมด":
            df_filtered['dt_parsed'] = pd.to_datetime(df_filtered['report_date'], errors='coerce')
            today = pd.Timestamp.now().normalize()
            
            if period_choice == "7 วันล่าสุด":
                start_dt = today - pd.Timedelta(days=7)
                df_filtered = df_filtered[df_filtered['dt_parsed'] >= start_dt]
            elif period_choice == "30 วันล่าสุด":
                start_dt = today - pd.Timedelta(days=30)
                df_filtered = df_filtered[df_filtered['dt_parsed'] >= start_dt]
            elif period_choice == "ปีปัจจุบัน":
                start_dt = pd.Timestamp(year=today.year, month=1, day=1)
                df_filtered = df_filtered[df_filtered['dt_parsed'] >= start_dt]
            elif period_choice == "กำหนดเอง (Custom Range)":
                with col_p2:
                    d_start = st.date_input("วันที่เริ่มต้น", today - pd.Timedelta(days=30))
                with col_p3:
                    d_end = st.date_input("วันที่สิ้นสุด", today)
                df_filtered = df_filtered[
                    (df_filtered['dt_parsed'] >= pd.Timestamp(d_start)) & 
                    (df_filtered['dt_parsed'] <= pd.Timestamp(d_end))
                ]

        st.markdown("---")
        
        # 2. Key Metrics Cards
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        total_jobs = len(df_filtered)
        completed_jobs = len(df_filtered[df_filtered["status"] == "เสร็จสิ้นแล้ว"])
        pending_jobs = len(df_filtered[df_filtered["status"] == "รอดำเนินการ"])
        in_progress_jobs = len(df_filtered[df_filtered["status"] == "กำลังดำเนินการ"])
        cancelled_jobs = len(df_filtered[df_filtered["status"] == "ยกเลิก"])
        
        m1.metric("📋 งานทั้งหมด", f"{total_jobs} งาน")
        m2.metric("✅ เสร็จสิ้นแล้ว", f"{completed_jobs} งาน", delta=f"{(completed_jobs/total_jobs*100):.1f}%" if total_jobs > 0 else "0%")
        m3.metric("⏳ รอดำเนินการ", f"{pending_jobs} งาน")
        m4.metric("⚙️ กำลังซ่อม", f"{in_progress_jobs} งาน")
        m5.metric("❌ ยกเลิก", f"{cancelled_jobs} งาน")
        
        # คำนวณเวลาซ่อมเฉลี่ย (MTTR)
        mttr_hours = "-"
        completed_df = df_filtered[df_filtered["status"] == "เสร็จสิ้นแล้ว"].copy()
        if not completed_df.empty:
            durations = []
            for _, row in completed_df.iterrows():
                try:
                    t_start = pd.to_datetime(f"{row['report_date']} {row['report_time']}")
                    t_end = pd.to_datetime(f"{row['completed_date']} {row['completed_time']}")
                    diff = (t_end - t_start).total_seconds() / 3600.0
                    if diff >= 0:
                        durations.append(diff)
                except Exception:
                    pass
            if durations:
                mttr_hours = f"{sum(durations)/len(durations):.1f} ชม."
        m6.metric("⏱️ MTTR เฉลี่ย", mttr_hours)
        
        st.markdown("---")
        
        # 3. สถิติกราฟวิเคราะห์ (Charts & Graphs)
        c_g1, c_g2 = st.columns(2)
        
        with c_g1:
            st.markdown("#### 🍩 สัดส่วนสถานะงานซ่อม (Status Breakdown)")
            status_counts = df_filtered["status"].value_counts().reset_index()
            status_counts.columns = ["สถานะ", "จำนวน"]
            fig_status = px.pie(
                status_counts, 
                values="จำนวน", 
                names="สถานะ", 
                hole=0.4,
                color="สถานะ",
                color_discrete_map={
                    "รอดำเนินการ": "#ff9999",
                    "กำลังดำเนินการ": "#ffcc99",
                    "เสร็จสิ้นแล้ว": "#99ff99",
                    "ยกเลิก": "#d3d3d3"
                }
            )
            st.plotly_chart(fig_status, use_container_width=True)
            
        with c_g2:
            st.markdown("#### 🚨 จำนวนงานจำแนกตามความเร่งด่วน (Priority Breakdown)")
            prio_counts = df_filtered["priority"].value_counts().reset_index()
            prio_counts.columns = ["ความเร่งด่วน", "จำนวน"]
            fig_prio = px.bar(
                prio_counts, 
                x="ความเร่งด่วน", 
                y="จำนวน", 
                color="ความเร่งด่วน",
                color_discrete_map={
                    "ด่วนที่สุด": "#ff4d4d",
                    "ด่วน": "#ffa64d",
                    "ปกติ": "#4da6ff"
                }
            )
            st.plotly_chart(fig_prio, use_container_width=True)

        c_g3, c_g4 = st.columns(2)
        with c_g3:
            st.markdown("#### 🏢 จำนวนงานจำแนกตามแผนก (Department Breakdown)")
            dept_counts = df_filtered["department"].value_counts().reset_index()
            dept_counts.columns = ["แผนก", "จำนวน"]
            fig_dept = px.bar(dept_counts, x="แผนก", y="จำนวน", color="แผนก")
            st.plotly_chart(fig_dept, use_container_width=True)
            
        with c_g4:
            st.markdown("#### 👨‍🔧 จำนวนงานจำแนกตามช่างผู้รับผิดชอบ (Technician Workload)")
            tech_counts = df_filtered["technician"].replace("", "ยังไม่ได้มอบหมาย").fillna("ยังไม่ได้มอบหมาย").value_counts().reset_index()
            tech_counts.columns = ["ช่างผู้รับผิดชอบ", "จำนวน"]
            fig_tech = px.bar(tech_counts, x="ช่างผู้รับผิดชอบ", y="จำนวน", color="ช่างผู้รับผิดชอบ")
            st.plotly_chart(fig_tech, use_container_width=True)
            
        st.markdown("---")
        
        # 4. ดาวน์โหลดรายงานสรุปเป็น CSV
        st.markdown("#### 📥 ดาวน์โหลดรายงานฉบับเต็ม")
        csv_export = df_filtered.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 ดาวน์โหลดไฟล์ CSV รายงานแจ้งซ่อม",
            data=csv_export,
            file_name=f"maintenance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

        # 5. 🔍 ตารางรายการงานล่าสุด/งานค้าง (Work Order List Table & Drill-down)
        st.markdown("---")
        st.markdown("### 🔍 ตารางรายการงานล่าสุด / งานค้าง (Work Order List Table)")
        st.caption("แสดงรายการงานซ่อมล่าสุดเพื่อกด Drill-down ตรวจสอบรายละเอียดงานได้ทันที")
        
        col_w1, col_w2 = st.columns([2, 1])
        with col_w1:
            wo_filter_type = st.radio(
                "📌 เลือกมุมมองรายการ:",
                ["⏳ งานค้างดำเนินการ (Pending / In-Progress)", "🕒 งานซ่อมล่าสุด (5-10 รายการล่าสุด)"],
                horizontal=True,
                key="wo_filter_radio"
            )
        with col_w2:
            num_show = st.slider("🔢 จำนวนรายการที่แสดง:", min_value=5, max_value=20, value=10, step=1, key="wo_num_slider")
            
        if "งานค้างดำเนินการ" in wo_filter_type:
            df_wo = df[df["status"].isin(["รอดำเนินการ", "กำลังดำเนินการ"])].copy()
            df_wo = df_wo.iloc[::-1].head(num_show)
        else:
            df_wo = df.iloc[::-1].head(num_show)
            
        if df_wo.empty:
            st.info("ℹ️ ไม่พบรายการงานตามเงื่อนไขที่เลือก")
        else:
            wo_display_cols = ["ticket_no", "reporter", "equipment", "department", "status", "technician", "priority", "report_date"]
            df_wo_show = df_wo[wo_display_cols].copy()
            df_wo_show.columns = ["เลข Ticket", "ผู้แจ้ง", "อุปกรณ์", "แผนก", "สถานะ", "ช่างผู้รับผิดชอบ", "ความเร่งด่วน", "วันที่แจ้ง"]
            
            st.dataframe(apply_status_style(df_wo_show), use_container_width=True, hide_index=True)
            
            # 🔍 ส่วน Drill-down เจาะลึกรายละเอียด
            st.markdown("##### 🔍 Drill-down: เลือกใบแจ้งซ่อมเพื่อดูรายละเอียดเชิงลึก")
            
            selected_ticket_wo = st.selectbox(
                "เลือกเลขที่ Ticket ที่ต้องการเจาะลึก:",
                options=df_wo["ticket_no"].tolist(),
                key="drill_down_ticket_select"
            )
            
            wo_detail = df[df["ticket_no"] == selected_ticket_wo].iloc[0]
            
            with st.container(border=True):
                st.markdown(f"#### 📄 รายละเอียดใบแจ้งซ่อม: **{wo_detail['ticket_no']}**")
                
                # แถวที่ 1: ข้อมูลทั่วไป
                c_d1, c_d2, c_d3, c_d4 = st.columns(4)
                c_d1.markdown(f"**👤 ผู้แจ้ง:**\n{wo_detail.get('reporter', '-')}")
                c_d2.markdown(f"**🏢 แผนก:**\n{wo_detail.get('department', '-')}")
                c_d3.markdown(f"**⚙️ อุปกรณ์/เครื่องจักร:**\n{wo_detail.get('equipment', '-')}")
                c_d4.markdown(f"**📌 สถานะ:**\n`{wo_detail.get('status', '-')}`")
                
                # แถวที่ 2: สถานะและช่าง
                c_d5, c_d6, c_d7, c_d8 = st.columns(4)
                c_d5.markdown(f"**🚨 ความเร่งด่วน:**\n{wo_detail.get('priority', '-')}")
                c_d6.markdown(f"**🏷️ ประเภทงาน:**\n{wo_detail.get('job_type', '-')}")
                c_d7.markdown(f"**📅 วัน-เวลาที่แจ้ง:**\n{wo_detail.get('report_date', '-')} {wo_detail.get('report_time', '')}")
                c_d8.markdown(f"**👨‍🔧 ช่างผู้รับผิดชอบ:**\n{wo_detail.get('technician', '-') or '-'}")
                
                st.divider()
                
                # แถวที่ 3: อาการเสีย/รายละเอียด
                st.markdown("**📝 รายละเอียดอาการเสีย / ปัญหาที่พบ:**")
                st.info(wo_detail.get('description', '-') or 'ไม่มีรายละเอียด')
                
                # แถวที่ 4: ผลการซ่อมและการแก้ไข
                c_r1, c_r2 = st.columns(2)
                with c_r1:
                    st.markdown(f"**🛠️ สาเหตุของปัญหา:**\n{wo_detail.get('cause', '-') or '-'}")
                    st.markdown(f"**🔧 การแก้ไข/การปฏิบัติงาน:**\n{wo_detail.get('solution', '-') or '-'}")
                with c_r2:
                    st.markdown(f"**🔩 อะไหล่ที่ใช้:**\n{wo_detail.get('parts_used', '-') or '-'} (จำนวน: {wo_detail.get('parts_qty', '-') or '-'})")
                    comp_time_str = f"{wo_detail.get('completed_date', '')} {wo_detail.get('completed_time', '')}".strip()
                    st.markdown(f"**🏁 วัน-เวลาที่ซ่อมเสร็จ:**\n{comp_time_str if comp_time_str else '-'}")
                
                # แถวที่ 5: รูปถ่ายก่อน-หลังซ่อม
                st.markdown("---")
                col_img_b, col_img_a = st.columns(2)
                with col_img_b:
                    display_image_gallery(wo_detail.get("image_before", ""), title="📸 รูปถ่ายก่อนซ่อม (Before)")
                with col_img_a:
                    display_image_gallery(wo_detail.get("image_after", ""), title="📸 รูปถ่ายหลังซ่อมเสร็จ (After)")
