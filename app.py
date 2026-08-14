import io
import sqlite3
from datetime import datetime, timedelta, timezone
import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st

# -------------------------------------------------------------
# กำหนดเขตเวลาประเทศไทย (UTC+7 / ICT)
# -------------------------------------------------------------
THAILAND_TZ = timezone(timedelta(hours=7))


def get_thailand_now():
  """ฟังก์ชันดึงเวลาปัจจุบันของประเทศไทย (YYYY-MM-DD HH:MM:SS)"""
  return datetime.now(THAILAND_TZ).strftime("%Y-%m-%d %H:%M:%S")


def get_thailand_now_dt():
  """ฟังก์ชันดึง datetime Object ปัจจุบันของไทย"""
  return datetime.now(THAILAND_TZ)


def format_timedelta(td):
  """ฟังก์ชันแปลง Timedelta ให้แสดงผลเป็น วัน/ชม./นาที"""
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


# --- 1. ตั้งค่าฐานข้อมูล SQLite ---
conn = sqlite3.connect("repair_system_v6.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS repair_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter TEXT NOT NULL,
    department TEXT NOT NULL,
    equipment TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    image BLOB,
    technician TEXT,
    cause TEXT,
    solution TEXT,
    parts_used TEXT,
    parts_qty TEXT,
    completed_at TEXT,
    image_after BLOB
)
""")
conn.commit()

# --- 2. ตั้งค่าหน้าตาแอป Streamlit ---
st.set_page_config(
    page_title="ระบบแจ้งซ่อมและบันทึกผลงาน", page_icon="🛠️", layout="wide"
)

st.title("🛠️ ระบบแจ้งซ่อม บันทึกผลงาน และส่งออกรายงาน Excel")

tab1, tab2, tab3 = st.tabs([
    "📝 ส่งใบแจ้งซ่อม",
    "⚙️ บันทึกงานซ่อม (สำหรับช่าง)",
    "📊 รายงาน & กราฟสรุปประจำเดือน",
])

# ==========================================
# --- Tab 1: ฟอร์มแจ้งซ่อม (ฝั่งผู้ใช้งาน) ---
# ==========================================
with tab1:
  st.subheader("กรอกข้อมูลการแจ้งซ่อม")
  with st.form(key="repair_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
      reporter = st.text_input("ชื่อผู้แจ้ง *")
    with col2:
      department = st.selectbox(
          "เลือกแผนก / โซน *", ["สีฝุ่น", "สีน้ำมัน", "โซน 2"]
      )
    with col3:
      priority = st.selectbox(
          "ระดับความเร่งด่วน", ["ปกติ", "ด่วน", "ด่วนที่สุด"]
      )

    equipment = st.text_input("อุปกรณ์ / สถานที่ ที่ต้องการแจ้งซ่อม *")
    description = st.text_area("รายละเอียดปัญหาอาการเสีย *")
    uploaded_file = st.file_uploader(
        "📷 แนบรูปภาพอุปกรณ์เสียก่อนซ่อม (ถ้ามี)", type=["jpg", "png", "jpeg"]
    )

    submit_button = st.form_submit_button(label="ส่งข้อมูลแจ้งซ่อม")

    if submit_button:
      if reporter and department and equipment and description:
        image_bytes = None
        if uploaded_file is not None:
          image_bytes = uploaded_file.read()

        now_str = get_thailand_now()  # เวลาประเทศไทย (UTC+7)
        c.execute(
            """
                    INSERT INTO repair_tickets (reporter, department, equipment, description, priority, status, created_at, image)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
            (
                reporter,
                department,
                equipment,
                description,
                priority,
                "รอดำเนินการ",
                now_str,
                image_bytes,
            ),
        )
        conn.commit()
        st.success("✅ ส่งข้อมูลแจ้งซ่อมเรียบร้อยแล้ว!")
      else:
        st.warning("⚠️ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")

# ==========================================================
# --- Tab 2: บันทึกงานซ่อม & แนบรูปหลังซ่อม (ฝั่งช่าง) ---
# ==========================================================
with tab2:
  st.subheader("จัดการ อัปเดตงานซ่อม สาเหตุ วิธีแก้ไข และวัน-เวลาที่ซ่อมเสร็จ")

  c.execute("SELECT id FROM repair_tickets ORDER BY id DESC")
  ticket_ids = [row[0] for row in c.fetchall()]

  if ticket_ids:
    df_all = pd.read_sql_query(
        """
            SELECT 
                id AS 'ID', reporter AS 'ผู้แจ้ง', department AS 'แผนก', equipment AS 'อุปกรณ์', 
                priority AS 'ความเร่งด่วน', status AS 'สถานะ', 
                technician AS 'ผู้ซ่อม', cause AS 'สาเหตุ', solution AS 'วิธีแก้ไข',
                parts_used AS 'อะไหล่ที่ใช้', parts_qty AS 'จำนวน', 
                created_at AS 'เวลาแจ้ง (ไทย)', completed_at AS 'เวลาซ่อมเสร็จ (ไทย)'
            FROM repair_tickets ORDER BY id DESC
        """,
        conn,
    )
    st.dataframe(df_all, use_container_width=True)

    st.markdown("---")

    selected_id = st.selectbox("เลือก ID ที่ต้องการอัปเดตงานซ่อม", ticket_ids)

    c.execute("SELECT * FROM repair_tickets WHERE id=?", (selected_id,))
    ticket = c.fetchone()

    if ticket:
      col_info, col_form = st.columns([1, 1])

      with col_info:
        st.markdown(f"### 🔍 รายละเอียดใบแจ้งซ่อม ID: **{ticket[0]}**")
        st.write(f"**ผู้แจ้ง:** {ticket[1]}")
        st.write(f"**แผนก:** {ticket[2]}")
        st.write(f"**อุปกรณ์:** {ticket[3]}")
        st.write(f"**ความเร่งด่วน:** {ticket[5]}")
        st.write(f"**เวลาแจ้ง (ไทย):** {ticket[7]}")
        st.write(f"**เวลาซ่อมเสร็จล่าสุด:** {ticket[14] or 'ยังไม่เสร็จสิ้น'}")
        st.info(f"**อาการเสีย:** {ticket[4]}")

        st.markdown("#### 🖼️ เปรียบเทียบรูปภาพก่อน-หลังซ่อม")
        img_col1, img_col2 = st.columns(2)

        with img_col1:
          st.caption("📷 **ก่อนซ่อม**")
          if ticket[8]:
            img_before = Image.open(io.BytesIO(ticket[8]))
            st.image(img_before, use_container_width=True)
          else:
            st.text("ไม่มีรูปก่อนซ่อม")

        with img_col2:
          st.caption("✅ **หลังซ่อมเสร็จ**")
          if ticket[15]:
            img_after = Image.open(io.BytesIO(ticket[15]))
            st.image(img_after, use_container_width=True)
          else:
            st.text("ยังไม่ได้แนบรูปหลังซ่อม")

      with col_form:
        st.markdown("### 🛠️ บันทึกการซ่อมของช่าง")
        with st.form(key="tech_form"):
          status_list = [
              "รอดำเนินการ",
              "กำลังดำเนินการ",
              "เสร็จสิ้น",
              "ยกเลิก",
          ]
          curr_status_idx = (
              status_list.index(ticket[6]) if ticket[6] in status_list else 0
          )

          new_status = st.selectbox(
              "สถานะการซ่อม", status_list, index=curr_status_idx
          )
          technician_name = st.text_input(
              "ชื่อผู้ซ่อม / ช่างผู้รับผิดชอบ", value=ticket[9] or ""
          )

          cause_input = st.text_area(
              "สาเหตุของอาการเสีย / จุดที่ชำรุด", value=ticket[10] or ""
          )
          solution_input = st.text_area(
              "วิธีแก้ไข / ดำเนินการซ่อม", value=ticket[11] or ""
          )

          parts_used = st.text_input(
              "อะไหล่ที่ใช้ (เช่น น็อต M6, สายไฟ)", value=ticket[12] or ""
          )
          parts_qty = st.text_input(
              "จำนวนอะไหล่ (เช่น 2 ตัว, 1 เมตร)", value=ticket[13] or ""
          )

          st.markdown("---")
          st.markdown("🕒 **ระบุวันและเวลาที่ซ่อมเสร็จ**")

          default_dt = get_thailand_now_dt()
          if ticket[14]:
            try:
              default_dt = datetime.strptime(ticket[14], "%Y-%m-%d %H:%M:%S")
            except Exception:
              pass

          col_d, col_t = st.columns(2)
          with col_d:
            completed_date = st.date_input(
                "📅 วันที่ซ่อมเสร็จ", value=default_dt.date()
            )
          with col_t:
            completed_time = st.time_input(
                "⏰ เวลาที่ซ่อมเสร็จ",
                value=default_dt.time().replace(microsecond=0),
            )

          uploaded_after = st.file_uploader(
              "📷 แนบรูปถ่ายหลังซ่อมเสร็จ", type=["jpg", "png", "jpeg"]
          )

          save_btn = st.form_submit_button("💾 บันทึกข้อมูลงานซ่อม")

          if save_btn:
            image_after_bytes = ticket[15]
            if uploaded_after is not None:
              image_after_bytes = uploaded_after.read()

            completed_time_str = None
            if new_status == "เสร็จสิ้น":
              completed_time_str = f"{completed_date} {completed_time.strftime('%H:%M:%S')}"
            else:
              completed_time_str = ticket[14]

            c.execute(
                """
                            UPDATE repair_tickets 
                            SET status=?, technician=?, cause=?, solution=?, parts_used=?, parts_qty=?, completed_at=?, image_after=?
                            WHERE id=?
                        """,
                (
                    new_status,
                    technician_name,
                    cause_input,
                    solution_input,
                    parts_used,
                    parts_qty,
                    completed_time_str,
                    image_after_bytes,
                    selected_id,
                ),
            )
            conn.commit()
            st.success(
                f"✅ บันทึกข้อมูลงานซ่อม ID {selected_id} เรียบร้อยแล้ว!"
            )
            st.rerun()
  else:
    st.info("ยังไม่มีข้อมูลการแจ้งซ่อมในระบบ")

# ===================================================
# --- Tab 3: สรุปรายงาน & กราฟ + ปุ่มโหลด Excel ---
# ===================================================
with tab3:
  st.subheader("📈 สรุปภาพรวม สถิติ และส่งออกข้อมูลเป็น Excel")

  df_stats = pd.read_sql_query("SELECT * FROM repair_tickets", conn)

  if not df_stats.empty:
    df_stats["created_at_dt"] = pd.to_datetime(
        df_stats["created_at"], errors="coerce"
    )
    df_stats["completed_at_dt"] = pd.to_datetime(
        df_stats["completed_at"], errors="coerce"
    )
    df_stats["YearMonth"] = df_stats["created_at_dt"].dt.strftime("%Y-%m")

    df_stats["duration"] = (
        df_stats["completed_at_dt"] - df_stats["created_at_dt"]
    )
    df_stats["duration_hours"] = (
        df_stats["duration"].dt.total_seconds() / 3600
    )

    completed_tickets = df_stats[df_stats["status"] == "เสร็จสิ้น"]
    total_time_td = (
        completed_tickets["duration"].sum()
        if not completed_tickets.empty
        else pd.Timedelta(0)
    )
    avg_time_td = (
        completed_tickets["duration"].mean()
        if not completed_tickets.empty
        else pd.Timedelta(0)
    )

    total_repair_str = format_timedelta(total_time_td)
    avg_repair_str = format_timedelta(avg_time_td)

    # --- Metrics สรุป ---
    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    col_m1.metric("แจ้งซ่อมทั้งหมด", len(df_stats))
    col_m2.metric(
        "เสร็จสิ้นแล้ว", len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
    )
    col_m3.metric(
        "กำลังดำเนินการ",
        len(df_stats[df_stats["status"] == "กำลังดำเนินการ"]),
    )
    col_m4.metric(
        "รอดำเนินการ", len(df_stats[df_stats["status"] == "รอดำเนินการ"])
    )
    col_m5.metric("⏱️ เวลาซ่อมรวมทั้งหมด", total_repair_str)
    col_m6.metric("⌛ เวลาซ่อมเฉลี่ย/งาน", avg_repair_str)

    st.markdown("---")

    # --- กราฟสรุปผล ---
    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
      st.markdown("### 🗓️ รายเดือน (ตามสถานะ)")
      monthly_summary = (
          df_stats.groupby(["YearMonth", "status"])
          .size()
          .reset_index(name="จำนวนงาน")
      )

      fig_bar = px.bar(
          monthly_summary,
          x="YearMonth",
          y="จำนวนงาน",
          color="status",
          title="ใบแจ้งซ่อมในแต่ละเดือน",
          labels={"YearMonth": "เดือน", "จำนวนงาน": "รายการ"},
          barmode="stack",
      )
      st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
      st.markdown("### ⏱️ เวลาซ่อมรวมแยกตามแผนก (ชั่วโมง)")
      dept_time = (
          completed_tickets.groupby("department")["duration_hours"]
          .sum()
          .reset_index()
      )
      dept_time["duration_hours"] = dept_time["duration_hours"].round(2)

      fig_dept_time = px.bar(
          dept_time,
          x="department",
          y="duration_hours",
          color="department",
          title="เวลาซ่อมรวมทั้งหมดแยกตามแผนก (ชม.)",
          labels={"department": "แผนก", "duration_hours": "ชั่วโมงรวม"},
          text_auto=True,
      )
      st.plotly_chart(fig_dept_time, use_container_width=True)

    with col_g3:
      st.markdown("### 🚨 สัดส่วนความเร่งด่วน")
      priority_summary = (
          df_stats.groupby("priority").size().reset_index(name="จำนวนงาน")
      )

      fig_pie = px.pie(
          priority_summary,
          values="จำนวนงาน",
          names="priority",
          title="สัดส่วนระดับความเร่งด่วน",
          color="priority",
          color_discrete_map={
              "ด่วนที่สุด": "red",
              "ด่วน": "orange",
              "ปกติ": "green",
          },
      )
      st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🛠️ ตารางรายงานการซ่อม")

    completed_df = df_stats[df_stats["technician"].notna()][
        [
            "id",
            "reporter",
            "department",
            "equipment",
            "technician",
            "cause",
            "solution",
            "parts_used",
            "parts_qty",
            "created_at",
            "completed_at",
            "duration",
        ]
    ].copy()

    completed_df["ระยะเวลาซ่อม"] = completed_df["duration"].apply(
        format_timedelta
    )
    completed_df["รูปหลังซ่อม"] = df_stats["image_after"].apply(
        lambda x: "✅ มีรูป" if x is not None else "❌ ไม่มี"
    )

    completed_df_display = completed_df[[
        "id",
        "reporter",
        "department",
        "equipment",
        "technician",
        "cause",
        "solution",
        "parts_used",
        "parts_qty",
        "created_at",
        "completed_at",
        "ระยะเวลาซ่อม",
        "รูปหลังซ่อม",
    ]]

    completed_df_display.columns = [
        "ID",
        "ผู้แจ้ง",
        "แผนก",
        "อุปกรณ์",
        "ช่างผู้ซ่อม",
        "สาเหตุ",
        "วิธีแก้ไข",
        "อะไหล่ที่ใช้",
        "จำนวน",
        "วัน-เวลาที่แจ้ง (ไทย)",
        "วัน-เวลาที่ซ่อมเสร็จ (ไทย)",
        "ระยะเวลาซ่อมรวม",
        "สถานะรูปหลังซ่อม",
    ]

    st.dataframe(completed_df_display, use_container_width=True)

    # --- เพิ่มปุ่มสำหรับดาวน์โหลดไฟล์ Excel / CSV ---
    st.markdown("#### 📥 ดาวน์โหลดรายงาน")
    col_dl1, col_dl2 = st.columns(2)

    file_timestamp = get_thailand_now_dt().strftime("%Y%m%d_%H%M")

    # 1. ปุ่มดาวน์โหลดไฟล์ CSV (เปิดใน Excel ภาษาไทยไม่ต่างดาว)
    csv_bytes = completed_df_display.to_csv(index=False).encode("utf-8-sig")
    with col_dl1:
      st.download_button(
          label="📄 ดาวน์โหลดรายงาน (ไฟล์ CSV สำหรับ Excel)",
          data=csv_bytes,
          file_name=f"Repair_Report_{file_timestamp}.csv",
          mime="text/csv",
          use_container_width=True,
      )

    # 2. ปุ่มดาวน์โหลดไฟล์ Excel .xlsx
    try:
      excel_buffer = io.BytesIO()
      with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        completed_df_display.to_excel(
            writer, index=False, sheet_name="รายงานการซ่อม"
        )
      excel_data = excel_buffer.getvalue()

      with col_dl2:
        st.download_button(
            label="📊 ดาวน์โหลดรายงาน (ไฟล์ Excel .xlsx)",
            data=excel_data,
            file_name=f"Repair_Report_{file_timestamp}.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )
    except Exception:
      pass

  else:
    st.info("ยังไม่มีข้อมูลสำหรับสร้างกราฟสรุปผล")

conn.close()
