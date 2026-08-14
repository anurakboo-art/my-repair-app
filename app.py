import base64
import io
from datetime import datetime, timedelta, timezone
import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st
from supabase import create_client

# -------------------------------------------------------------
# 1. กำหนดเขตเวลาประเทศไทย (UTC+7) และฟังก์ชันจัดการเวลา
# -------------------------------------------------------------
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
    return datetime.strptime(str(val)[:8], "%H:%M:%S").time()
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


def compress_and_to_base64(image_bytes, max_size=(400, 400), quality=60):
  if not image_bytes:
    return ""
  try:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P"):
      img = img.convert("RGB")
    img.thumbnail(max_size)
    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=quality)
    return base64.b64encode(out_buf.getvalue()).decode("utf-8")
  except Exception:
    return ""


def base64_to_image(b64_str):
  if not b64_str or pd.isna(b64_str) or str(b64_str).strip() == "":
    return None
  try:
    img_bytes = base64.b64decode(str(b64_str))
    return Image.open(io.BytesIO(img_bytes))
  except Exception:
    return None


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


# -------------------------------------------------------------
# 2. เชื่อมต่อ Supabase และกำหนดชื่อหน้าเว็บ
# -------------------------------------------------------------
st.set_page_config(
    page_title="ใบแจ้งซ่อม-บันทึกการซ่อม", page_icon="🛠️", layout="wide"
)

# หัวกระดาษหลักของแอป
st.title("🛠️ ใบแจ้งซ่อม-บันทึกการซ่อม")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

COLUMN_NAMES = [
    "id",
    "reporter",
    "department",
    "equipment",
    "description",
    "priority",
    "status",
    "report_date",
    "report_time",
    "created_at",
    "image_before",
    "technician",
    "cause",
    "solution",
    "parts_used",
    "parts_qty",
    "completed_date",
    "completed_time",
    "completed_at",
    "image_after",
]


def load_data():
  try:
    response = (
        supabase.table("repair_requests")
        .select("*")
        .order("id", desc=False)
        .execute()
    )
    data = response.data
    if not data:
      return pd.DataFrame(columns=COLUMN_NAMES)
    df = pd.DataFrame(data)
    for col in COLUMN_NAMES:
      if col not in df.columns:
        df[col] = ""
    return df
  except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
    return pd.DataFrame(columns=COLUMN_NAMES)


df_data = load_data()

# ดึงรายการแผนกทั้งหมดที่มีอยู่ในฐานข้อมูลมารวมกับแผนกเริ่มต้น
default_depts = ["สีฝุ่น", "สีน้ำมัน", "โซน 2"]
if not df_data.empty and "department" in df_data.columns:
  db_depts = [
      str(d).strip()
      for d in df_data["department"].dropna().unique()
      if str(d).strip() != ""
  ]
  all_departments = sorted(list(set(default_depts + db_depts)))
else:
  all_departments = default_depts

tab1, tab2, tab3 = st.tabs([
    "📝 ส่งใบแจ้งซ่อม",
    "⚙️ จัดการ/แก้ไขงานซ่อม (สำหรับช่าง)",
    "📊 รายงาน & กราฟสรุปผล",
])

# ==========================================
# --- Tab 1: ฟอร์มแจ้งซ่อม ---
# ==========================================
with tab1:
  st.subheader("กรอกข้อมูลการแจ้งซ่อมใหม่")
  with st.form(key="repair_form", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)

    with col1:
      reporter = st.text_input("ชื่อผู้แจ้ง *")

    with col2:
      dept_options = all_departments + ["➕ พิมพ์ระบุแผนกใหม่..."]
      dept_choice = st.selectbox("เลือกแผนก / โซน *", dept_options)
      if dept_choice == "➕ พิมพ์ระบุแผนกใหม่...":
        department = st.text_input("พิมพ์ชื่อแผนก / โซน ใหม่ *")
      else:
        department = dept_choice

    with col3:
      priority = st.selectbox(
          "ระดับความเร่งด่วน", ["ปกติ", "ด่วน", "ด่วนที่สุด"]
      )

    equipment = st.text_input("อุปกรณ์ / สถานที่ ที่ต้องการแจ้งซ่อม *")
    description = st.text_area("รายละเอียดปัญหาอาการเสีย *")

    st.markdown("🕒 **วันและเวลาที่เกิดเหตุ / แจ้งซ่อม**")
    now_dt = get_thailand_now_dt()
    col_d, col_t = st.columns(2)
    with col_d:
      report_date = st.date_input("📅 วันที่แจ้งซ่อม", value=now_dt.date())
    with col_t:
      report_time = st.time_input(
          "⏰ เวลาที่แจ้งซ่อม", value=now_dt.time().replace(microsecond=0)
      )

    uploaded_file = st.file_uploader(
        "📷 แนบรูปภาพอุปกรณ์เสียก่อนซ่อม (ถ้ามี)", type=["jpg", "png", "jpeg"]
    )

    submit_button = st.form_submit_button(label="ส่งข้อมูลแจ้งซ่อม")

    if submit_button:
      if reporter and department and equipment and description:
        image_b64 = ""
        if uploaded_file is not None:
          image_b64 = compress_and_to_base64(uploaded_file.read())

        created_at_str = (
            f"{report_date} {report_time.strftime('%H:%M:%S')}+07:00"
        )

        new_data = {
            "reporter": reporter,
            "department": department.strip(),
            "equipment": equipment,
            "description": description,
            "priority": priority,
            "status": "รอดำเนินการ",
            "report_date": str(report_date),
            "report_time": report_time.strftime("%H:%M:%S"),
            "created_at": created_at_str,
            "image_before": image_b64,
            "technician": "",
            "cause": "",
            "solution": "",
            "parts_used": "",
            "parts_qty": "",
            "completed_date": None,
            "completed_time": None,
            "completed_at": None,
            "image_after": "",
        }

        res = supabase.table("repair_requests").insert(new_data).execute()
        st.success("✅ ส่งข้อมูลแจ้งซ่อมเรียบร้อยแล้ว!")
        st.rerun()
      else:
        st.warning("⚠️ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")

# ==========================================
# --- Tab 2: จัดการ / แก้ไขงานซ่อม ---
# ==========================================
with tab2:
  st.subheader("🛠️ แก้ไขและอัปเดตข้อมูลงานซ่อม (สามารถปรับแก้ได้ทุกช่อง)")

  if not df_data.empty:
    df_display = df_data.copy()

    display_cols = [
        "id",
        "reporter",
        "department",
        "equipment",
        "priority",
        "status",
        "report_date",
        "report_time",
        "technician",
        "cause",
        "solution",
        "completed_date",
        "completed_time",
    ]

    df_show = df_display[display_cols].copy()
    df_show.columns = [
        "ID",
        "ผู้แจ้ง",
        "แผนก",
        "อุปกรณ์",
        "ความเร่งด่วน",
        "สถานะ",
        "วันที่แจ้ง",
        "เวลาแจ้ง",
        "ผู้ซ่อม",
        "สาเหตุ",
        "วิธีแก้ไข",
        "วันที่เสร็จ",
        "เวลาเสร็จ",
    ]

    try:
      styled_df = df_show.style.map(style_status, subset=["สถานะ"])
    except AttributeError:
      styled_df = df_show.style.applymap(style_status, subset=["สถานะ"])

    st.dataframe(styled_df, use_container_width=True)
    st.markdown("---")

    ticket_ids = df_data["id"].tolist()
    selected_id = st.selectbox(
        "🔍 เลือก ID ที่ต้องการแก้ไข / อัปเดตข้อมูล", ticket_ids
    )

    row_idx = df_data[df_data["id"] == selected_id].index[0]
    ticket = df_data.loc[row_idx]

    now_dt = get_thailand_now_dt()

    # --- ปุ่มลบใบแจ้งซ่อม ---
    with st.expander("⚠️ ต้องการลบใบแจ้งซ่อมนี้?"):
      st.write(
          f"หากต้องการลบใบแจ้งซ่อม ID **{selected_id}** ออกจากฐานข้อมูล ให้กดปุ่มด้านล่าง"
      )
      if st.button(
          f"🗑️ ยืนยันลบ ID {selected_id}", type="primary", key="del_btn"
      ):
        supabase.table("repair_requests").delete().eq(
            "id", selected_id
        ).execute()
        st.success(f"🗑️ ลบใบแจ้งซ่อม ID {selected_id} เรียบร้อยแล้ว!")
        st.rerun()

    # --- ฟอร์มแก้ไขข้อมูลทั้งหมด ---
    with st.form(key="edit_full_form"):
      st.markdown(f"### ✏️ แก้ไขข้อมูลใบแจ้งซ่อม ID: **{ticket['id']}**")

      # --- ส่วนที่ 1: ข้อมูลผู้แจ้งซ่อม ---
      st.markdown("#### 1️⃣ ข้อมูลการแจ้งซ่อม (ฝั่งผู้แจ้ง)")
      col_e1, col_e2, col_e3 = st.columns(3)

      curr_ticket_dept = str(ticket["department"] or "").strip()
      edit_dept_base = sorted(list(set(all_departments + [curr_ticket_dept])))
      if "" in edit_dept_base:
        edit_dept_base.remove("")
      edit_dept_options = edit_dept_base + ["➕ พิมพ์ระบุแผนกใหม่..."]

      curr_dept_idx = (
          edit_dept_options.index(curr_ticket_dept)
          if curr_ticket_dept in edit_dept_options
          else 0
      )

      prio_options = ["ปกติ", "ด่วน", "ด่วนที่สุด"]
      curr_prio = (
          ticket["priority"]
          if ticket["priority"] in prio_options
          else prio_options[0]
      )

      with col_e1:
        reporter_edit = st.text_input(
            "ผู้แจ้งซ่อม", value=str(ticket["reporter"] or "")
        )

      with col_e2:
        dept_choice_edit = st.selectbox(
            "แผนก / โซน", edit_dept_options, index=curr_dept_idx
        )
        if dept_choice_edit == "➕ พิมพ์ระบุแผนกใหม่...":
          department_edit = st.text_input(
              "พิมพ์ชื่อแผนก / โซน ใหม่", value=curr_ticket_dept
          )
        else:
          department_edit = dept_choice_edit

      with col_e3:
        priority_edit = st.selectbox(
            "ระดับความเร่งด่วน",
            prio_options,
            index=prio_options.index(curr_prio),
        )

      equipment_edit = st.text_input(
          "อุปกรณ์ / สถานที่", value=str(ticket["equipment"] or "")
      )
      description_edit = st.text_area(
          "อาการเสีย / รายละเอียดปัญหา",
          value=str(ticket["description"] or ""),
      )

      st.markdown("🕒 **วันและเวลาที่แจ้งซ่อม (แก้ไขได้)**")
      col_rd, col_rt = st.columns(2)

      init_rep_date = parse_date(ticket["report_date"], now_dt.date())
      init_rep_time = parse_time(
          ticket["report_time"], now_dt.time().replace(microsecond=0)
      )

      with col_rd:
        report_date_edit = st.date_input(
            "📅 วันที่แจ้งซ่อม", value=init_rep_date
        )
      with col_rt:
        report_time_edit = st.time_input(
            "⏰ เวลาที่แจ้งซ่อม", value=init_rep_time
        )

      col_img1, col_img2 = st.columns(2)
      with col_img1:
        st.caption("📷 รูปถ่ายก่อนซ่อมปัจจุบัน")
        img_b = base64_to_image(ticket["image_before"])
        if img_b:
          st.image(img_b, width=200)
        else:
          st.text("ไม่มีรูปก่อนซ่อม")
        uploaded_before_edit = st.file_uploader(
            "เปลี่ยนรูปถ่ายก่อนซ่อม",
            type=["jpg", "png", "jpeg"],
            key="up_before",
        )

      st.markdown("---")

      # --- ส่วนที่ 2: ข้อมูลงานซ่อมของช่าง ---
      st.markdown("#### 2️⃣ การดำเนินงานของช่าง (ฝั่งผู้ซ่อม)")

      status_list = ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"]
      curr_status = (
          ticket["status"] if ticket["status"] in status_list else "รอดำเนินการ"
      )

      col_t1, col_t2 = st.columns(2)
      with col_t1:
        new_status = st.selectbox(
            "สถานะการซ่อม",
            status_list,
            index=status_list.index(curr_status),
        )
      with col_t2:
        technician_name = st.text_input(
            "ช่างผู้รับผิดชอบ", value=str(ticket["technician"] or "")
        )

      cause_input = st.text_area(
          "สาเหตุการชำรุด", value=str(ticket["cause"] or "")
      )
      solution_input = st.text_area(
          "วิธีแก้ไข", value=str(ticket["solution"] or "")
      )

      col_p1, col_p2 = st.columns(2)
      with col_p1:
        parts_used = st.text_input(
            "อะไหล่ที่ใช้", value=str(ticket["parts_used"] or "")
        )
      with col_p2:
        parts_qty = st.text_input(
            "จำนวนอะไหล่", value=str(ticket["parts_qty"] or "")
        )

      st.markdown("🕒 **วันและเวลาที่ซ่อมเสร็จ (แก้ไขได้)**")

      init_comp_date = parse_date(ticket["completed_date"], now_dt.date())
      init_comp_time = parse_time(
          ticket["completed_time"], now_dt.time().replace(microsecond=0)
      )

      col_cd, col_ct = st.columns(2)
      with col_cd:
        completed_date_edit = st.date_input(
            "📅 วันที่ซ่อมเสร็จ", value=init_comp_date
        )
      with col_ct:
        completed_time_edit = st.time_input(
            "⏰ เวลาที่ซ่อมเสร็จ", value=init_comp_time
        )

      with col_img2:
        st.caption("✅ รูปถ่ายหลังซ่อมปัจจุบัน")
        img_a = base64_to_image(ticket["image_after"])
        if img_a:
          st.image(img_a, width=200)
        else:
          st.text("ไม่มีรูปหลังซ่อม")
        uploaded_after_edit = st.file_uploader(
            "เปลี่ยนรูปถ่ายหลังซ่อม",
            type=["jpg", "png", "jpeg"],
            key="up_after",
        )

      save_btn = st.form_submit_button(
          "💾 บันทึกการแก้ไขข้อมูลทั้งหมด", type="primary"
      )

      if save_btn:
        # การจัดการรูปภาพก่อนซ่อม
        img_before_b64 = ticket["image_before"]
        if uploaded_before_edit is not None:
          img_before_b64 = compress_and_to_base64(uploaded_before_edit.read())

        # การจัดการรูปภาพหลังซ่อม
        img_after_b64 = ticket["image_after"]
        if uploaded_after_edit is not None:
          img_after_b64 = compress_and_to_base64(uploaded_after_edit.read())

        # คำนวณ ISO Timestamp วันที่แจ้ง
        created_at_str = f"{report_date_edit} {report_time_edit.strftime('%H:%M:%S')}+07:00"

        # คำนวณ ISO Timestamp วันที่เสร็จ
        comp_date_str = None
        comp_time_str = None
        comp_at_str = None

        if new_status == "เสร็จสิ้น":
          comp_date_str = str(completed_date_edit)
          comp_time_str = completed_time_edit.strftime("%H:%M:%S")
          comp_at_str = f"{comp_date_str} {comp_time_str}+07:00"

        update_data = {
            "reporter": reporter_edit,
            "department": department_edit.strip(),
            "equipment": equipment_edit,
            "description": description_edit,
            "priority": priority_edit,
            "report_date": str(report_date_edit),
            "report_time": report_time_edit.strftime("%H:%M:%S"),
            "created_at": created_at_str,
            "image_before": img_before_b64,
            "status": new_status,
            "technician": technician_name,
            "cause": cause_input,
            "solution": solution_input,
            "parts_used": parts_used,
            "parts_qty": parts_qty,
            "completed_date": comp_date_str,
            "completed_time": comp_time_str,
            "completed_at": comp_at_str,
            "image_after": img_after_b64,
        }

        supabase.table("repair_requests").update(update_data).eq(
            "id", selected_id
        ).execute()
        st.success(
            f"✅ แก้ไขข้อมูลใบแจ้งซ่อม ID {selected_id} และอัปเดตลง Supabase เรียบร้อยแล้ว!"
        )
        st.rerun()

  else:
    st.info("ยังไม่มีข้อมูลการแจ้งซ่อมในระบบ")

# ==========================================
# --- Tab 3: รายงาน & กราฟ ---
# ==========================================
with tab3:
  st.subheader("📈 สรุปภาพรวม สถิติ และส่งออกข้อมูล")

  if not df_data.empty:
    df_stats = df_data.copy()

    # แก้ไขการจัดการ Timezone ให้เปรียบเทียบและลบกันได้โดยไม่มีปัญหา TypeError
    df_stats["created_at_dt"] = pd.to_datetime(
        df_stats["created_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Bangkok")
    df_stats["completed_at_dt"] = pd.to_datetime(
        df_stats["completed_at"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Bangkok")

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
    col_m5.metric("⏱️ เวลาซ่อมรวมทั้งหมด", format_timedelta(total_time_td))
    col_m6.metric("⌛ เวลาซ่อมเฉลี่ย/งาน", format_timedelta(avg_time_td))

    st.markdown("---")

    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
      period_type = st.selectbox(
          "🗓️ เลือกมุมมองช่วงเวลาของกราฟ",
          ["รายวัน", "รายสัปดาห์", "รายเดือน", "รายปี"],
          index=2,
      )

      if period_type == "รายวัน":
        df_stats["Period"] = df_stats["created_at_dt"].dt.strftime("%Y-%m-%d")
      elif period_type == "รายสัปดาห์":
        df_stats["Period"] = df_stats["created_at_dt"].dt.strftime("%Y-W%U")
      elif period_type == "รายเดือน":
        df_stats["Period"] = df_stats["created_at_dt"].dt.strftime("%Y-%m")
      else:
        df_stats["Period"] = df_stats["created_at_dt"].dt.strftime("%Y")

      summary_by_period = (
          df_stats.groupby(["Period", "status"])
          .size()
          .reset_index(name="จำนวนงาน")
      )

      fig_bar = px.bar(
          summary_by_period,
          x="Period",
          y="จำนวนงาน",
          color="status",
          title=f"สถิติใบแจ้งซ่อม ({period_type})",
          labels={"Period": f"ช่วงเวลา ({period_type})", "จำนวนงาน": "รายการ"},
          color_discrete_map={
              "เสร็จสิ้น": "#28a745",
              "รอดำเนินการ": "#ffc107",
              "ยกเลิก": "#dc3545",
              "กำลังดำเนินการ": "#17a2b8",
          },
          barmode="stack",
          text_auto=True,
      )
      st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
      st.markdown("### ⏱️ เวลาซ่อมรวมแยกตามแผนก")
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
    st.markdown("### 🛠️ ตารางรายงานการซ่อม (สำหรับส่งออกข้อมูล)")

    df_stats["ระยะเวลาซ่อมรวม"] = df_stats["duration"].apply(format_timedelta)
    df_stats["สถานะรูปหลังซ่อม"] = df_stats["image_after"].apply(
        lambda x: "✅ มีรูป" if str(x).strip() != "" else "❌ ไม่มี"
    )

    report_cols = [
        "id",
        "reporter",
        "department",
        "equipment",
        "status",
        "report_date",
        "report_time",
        "technician",
        "cause",
        "solution",
        "parts_used",
        "parts_qty",
        "completed_date",
        "completed_time",
        "ระยะเวลาซ่อมรวม",
        "สถานะรูปหลังซ่อม",
    ]

    completed_df_display = df_stats[report_cols].copy()
    completed_df_display.columns = [
        "ID",
        "ผู้แจ้ง",
        "แผนก",
        "อุปกรณ์",
        "สถานะ",
        "วันที่แจ้งซ่อม",
        "เวลาแจ้งซ่อม",
        "ช่างผู้ซ่อม",
        "สาเหตุ",
        "วิธีแก้ไข",
        "อะไหล่ที่ใช้",
        "จำนวน",
        "วันที่ซ่อมเสร็จ",
        "เวลาซ่อมเสร็จ",
        "ระยะเวลาซ่อมรวม",
        "สถานะรูปหลังซ่อม",
    ]

    try:
      styled_report_df = completed_df_display.style.map(
          style_status, subset=["สถานะ"]
      )
    except AttributeError:
      styled_report_df = completed_df_display.style.applymap(
          style_status, subset=["สถานะ"]
      )

    st.dataframe(styled_report_df, use_container_width=True)

    st.markdown("#### 📥 ดาวน์โหลดรายงาน")
    col_dl1, col_dl2 = st.columns(2)

    file_timestamp = get_thailand_now_dt().strftime("%Y%m%d_%H%M")

    csv_bytes = completed_df_display.to_csv(index=False).encode("utf-8-sig")
    with col_dl1:
      st.download_button(
          label="📄 ดาวน์โหลดรายงาน (ไฟล์ CSV)",
          data=csv_bytes,
          file_name=f"Repair_Report_{file_timestamp}.csv",
          mime="text/csv",
          use_container_width=True,
      )

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
