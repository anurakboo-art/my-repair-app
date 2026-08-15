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

st.title("🛠️ ใบแจ้งซ่อม & บันทึกงาน PM")

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

COLUMN_NAMES = [
    "id",
    "ticket_no",
    "received_no",
    "reporter",
    "job_type",
    "department",
    "equipment",
    "description",
    "priority",
    "status",
    "report_date",
    "report_time",
    "received_date",
    "received_time",
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
    # ดึงข้อมูลทั้งหมดจาก Supabase
    response = (
        supabase.table("repair_requests")
        .select("*")
        .order("report_date", desc=False)
        .order("report_time", desc=False)
        .execute()
    )
    data = response.data
    if not data:
      df = pd.DataFrame(columns=COLUMN_NAMES)
      return df

    df = pd.DataFrame(data)
    for col in COLUMN_NAMES:
      if col not in df.columns:
        df[col] = ""

    df["job_type"] = df["job_type"].replace("", "แจ้งซ่อม").fillna("แจ้งซ่อม")

    # รวมวันที่และเวลาเพื่อจัดเรียงลำดับจากเก่าไปใหม่ (วันที่มาก่อน อยู่ก่อนหน้า)
    df["temp_dt"] = pd.to_datetime(
        df["report_date"].astype(str) + " " + df["report_time"].astype(str),
        errors="coerce",
    )
    df = df.sort_values(
        by=["temp_dt", "created_at", "id"], ascending=[True, True, True]
    ).reset_index(drop=True)
    df = df.drop(columns=["temp_dt"])

    # หากไม่มีเลขที่ใบแจ้งซ่อม ให้แสดงค่าสำรองอ้างอิงลำดับ
    def fill_ticket_no(row):
      t_no = str(row.get("ticket_no", "") or "").strip()
      if t_no:
        return t_no
      try:
        val = int(row["id"])
        return f"REP-{val:04d}"
      except Exception:
        return f"REP-{row['id']}"

    df["ticket_no"] = df.apply(fill_ticket_no, axis=1)

    return df
  except Exception as e:
    st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูล: {e}")
    df = pd.DataFrame(columns=COLUMN_NAMES)
    return df


df_data = load_data()

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
    "📝 บันทึกงานแจ้งซ่อม / PM",
    "⚙️ จัดการ/แก้ไขงาน (สำหรับช่าง)",
    "📊 รายงาน & กราฟสรุปผล",
])

# ==========================================
# --- Tab 1: ฟอร์มแจ้งซ่อม / PM ---
# ==========================================
with tab1:
  st.subheader("กรอกข้อมูลการแจ้งซ่อม / งาน PM ใหม่")

  if "success_msg" in st.session_state:
    st.success(st.session_state.pop("success_msg"))

  # สร้างเลขที่ใบแจ้งซ่อมตั้งต้นอัตโนมัติตามลำดับจำนวนงาน
  default_ticket_no = f"REP-{(len(df_data) + 1):04d}"

  with st.form(key="repair_form", clear_on_submit=True):
    col1, col2, col3, col4 = st.columns(4)

    with col1:
      ticket_no = st.text_input(
          "เลขที่ใบแจ้งซ่อม *",
          value=default_ticket_no,
          placeholder="เช่น REP-0001",
      )

    with col2:
      received_no = st.text_input(
          "เลขที่รับแจ้ง", placeholder="เช่น REC-0001 (ถ้ามี)"
      )

    with col3:
      reporter = st.text_input("ชื่อผู้แจ้ง *")

    with col4:
      job_type = st.selectbox("ประเภทงาน *", ["แจ้งซ่อม", "PM"])

    col5, col6, col7 = st.columns(3)
    with col5:
      dept_options = all_departments + ["➕ พิมพ์ระบุแผนกใหม่..."]
      dept_choice = st.selectbox("เลือกแผนก / โซน *", dept_options)
      if dept_choice == "➕ พิมพ์ระบุแผนกใหม่...":
        department = st.text_input("พิมพ์ชื่อแผนก / โซน ใหม่ *")
      else:
        department = dept_choice

    with col6:
      priority = st.selectbox(
          "ระดับความเร่งด่วน", ["ปกติ", "ด่วน", "ด่วนที่สุด"]
      )

    with col7:
      equipment = st.text_input("อุปกรณ์ / เครื่องจักร / สถานที่ *")

    description = st.text_area("รายละเอียดปัญหาอาการเสีย / รายการ PM *")

    st.markdown("🕒 **วันและเวลาที่แจ้ง / วันและเวลาที่รับแจ้ง**")
    now_dt = get_thailand_now_dt()
    col_d1, col_t1, col_d2, col_t2 = st.columns(4)
    with col_d1:
      report_date = st.date_input("📅 วันที่แจ้ง", value=now_dt.date())
    with col_t1:
      report_time = st.time_input(
          "⏰ เวลาที่แจ้ง", value=now_dt.time().replace(microsecond=0)
      )
    with col_d2:
      received_date = st.date_input("📅 วันที่รับแจ้ง", value=now_dt.date())
    with col_t2:
      received_time = st.time_input(
          "⏰ เวลาที่รับแจ้ง", value=now_dt.time().replace(microsecond=0)
      )

    uploaded_file = st.file_uploader(
        "📷 แนบรูปภาพอุปกรณ์ก่อนซ่อม/ทำ PM (ถ้ามี)",
        type=["jpg", "png", "jpeg"],
    )

    submit_button = st.form_submit_button(label="ส่งข้อมูลบันทึกงาน")

    if submit_button:
      if ticket_no and reporter and department and equipment and description:
        image_b64 = ""
        if uploaded_file is not None:
          image_b64 = compress_and_to_base64(uploaded_file.read())

        created_at_str = (
            f"{report_date} {report_time.strftime('%H:%M:%S')}+07:00"
        )

        new_data = {
            "ticket_no": ticket_no.strip(),
            "received_no": received_no.strip(),
            "reporter": reporter,
            "job_type": job_type,
            "department": department.strip(),
            "equipment": equipment,
            "description": description,
            "priority": priority,
            "status": "รอดำเนินการ",
            "report_date": str(report_date),
            "report_time": report_time.strftime("%H:%M:%S"),
            "received_date": str(received_date),
            "received_time": received_time.strftime("%H:%M:%S"),
            "created_at": created_at_str,
            "image_before": image_b64,
            "technician": "",
            "cause": "",
            "solution": "",
            "parts_used": "",
            "parts_qty": "",
            "image_after": "",
        }

        try:
          supabase.table("repair_requests").insert(new_data).execute()
          st.session_state["success_msg"] = (
              f"✅ บันทึกข้อมูลเรียบร้อยแล้ว! เลขที่ใบแจ้งซ่อม:"
              f" **{ticket_no.strip()}**"
          )
          st.rerun()
        except Exception as e:
          st.error(
              "❌ ไม่สามารถบันทึกข้อมูลได้"
              " กรุณาตรวจสอบว่ามีคอลัมน์ใน Supabase หรือยัง (ข้อความแจ้งเตือน:"
              f" {e})"
          )
      else:
        st.warning("⚠️ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")

# ==========================================
# --- Tab 2: จัดการ / แก้ไขงาน ---
# ==========================================
with tab2:
  st.subheader("🛠️ แก้ไขและอัปเดตข้อมูลงานซ่อม / PM (สำหรับช่าง)")

  if not df_data.empty:
    df_display = df_data.copy()

    display_cols = [
        "ticket_no",
        "received_no",
        "reporter",
        "job_type",
        "department",
        "equipment",
        "description",
        "priority",
        "status",
        "report_date",
        "report_time",
        "received_date",
        "received_time",
        "technician",
        "cause",
        "solution",
        "completed_date",
        "completed_time",
    ]

    df_show = df_display[display_cols].copy()
    df_show.columns = [
        "เลขที่ใบแจ้งซ่อม",
        "เลขที่รับแจ้ง",
        "ผู้แจ้ง",
        "ประเภทงาน",
        "แผนก",
        "อุปกรณ์",
        "อาการเสีย/รายละเอียด",
        "ความเร่งด่วน",
        "สถานะ",
        "วันที่แจ้ง",
        "เวลาแจ้ง",
        "วันที่รับแจ้ง",
        "เวลาที่รับแจ้ง",
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

    # ตัวเลือกรายการเรียงตามวันที่เก่าไปใหม่
    ticket_options = {
        row["id"]: (
            f"{row['ticket_no']} | วันที่: {row['report_date']} |"
            f" {row['job_type']} - แผนก {row['department']} | อุปกรณ์:"
            f" {row['equipment']} ({row['status']})"
        )
        for _, row in df_data.iterrows()
    }

    selected_id = st.selectbox(
        "🔍 เลือกใบแจ้งซ่อมที่ต้องการแก้ไข / อัปเดตข้อมูล (เรียงจากเก่าไปใหม่)",
        options=list(ticket_options.keys()),
        format_func=lambda x: ticket_options[x],
    )

    row_idx = df_data[df_data["id"] == selected_id].index[0]
    ticket = df_data.loc[row_idx]

    now_dt = get_thailand_now_dt()

    with st.expander("⚠️ ต้องการลบใบแจ้งซ่อมนี้?"):
      st.write(
          f"หากต้องการลบใบแจ้งซ่อม **{ticket['ticket_no']}** ออกจากฐานข้อมูล"
          " ให้กดปุ่มด้านล่าง"
      )
      if st.button(
          f"🗑️ ยืนยันลบ {ticket['ticket_no']}", type="primary", key="del_btn"
      ):
        try:
          supabase.table("repair_requests").delete().eq(
              "id", selected_id
          ).execute()
          st.success(f"🗑️ ลบรายการ {ticket['ticket_no']} เรียบร้อยแล้ว!")
          st.rerun()
        except Exception as e:
          st.error(f"❌ เกิดข้อผิดพลาดในการลบ: {e}")

    with st.form(key="edit_full_form"):
      st.markdown(
          f"### ✏️ แก้ไขข้อมูลใบแจ้งซ่อม เลขที่: **{ticket['ticket_no']}**"
      )

      st.markdown("#### 1️⃣ ข้อมูลการแจ้งและการรับแจ้ง (ฝั่งผู้แจ้ง / รับแจ้ง)")
      col_e0, col_e01, col_e1, col_e2, col_e3, col_e4 = st.columns(6)

      job_type_list = ["แจ้งซ่อม", "PM"]
      curr_job_type = (
          ticket["job_type"]
          if ticket["job_type"] in job_type_list
          else "แจ้งซ่อม"
      )

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

      with col_e0:
        ticket_no_edit = st.text_input(
            "เลขที่ใบแจ้งซ่อม", value=str(ticket["ticket_no"] or "")
        )

      with col_e01:
        received_no_edit = st.text_input(
            "เลขที่รับแจ้ง", value=str(ticket["received_no"] or "")
        )

      with col_e1:
        reporter_edit = st.text_input(
            "ผู้แจ้งซ่อม", value=str(ticket["reporter"] or "")
        )

      with col_e2:
        job_type_edit = st.selectbox(
            "ประเภทงาน", job_type_list, index=job_type_list.index(curr_job_type)
        )

      with col_e3:
        dept_choice_edit = st.selectbox(
            "แผนก / โซน", edit_dept_options, index=curr_dept_idx
        )
        if dept_choice_edit == "➕ พิมพ์ระบุแผนกใหม่...":
          department_edit = st.text_input(
              "พิมพ์ชื่อแผนก / โซน ใหม่", value=curr_ticket_dept
          )
        else:
          department_edit = dept_choice_edit

      with col_e4:
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

      st.markdown("🕒 **วันเวลาที่แจ้ง & วันเวลาที่รับแจ้ง (แก้ไขได้)**")
      col_rd, col_rt, col_rcd, col_rct = st.columns(4)

      init_rep_date = parse_date(ticket["report_date"], now_dt.date())
      init_rep_time = parse_time(
          ticket["report_time"], now_dt.time().replace(microsecond=0)
      )
      init_rec_date = parse_date(ticket["received_date"], now_dt.date())
      init_rec_time = parse_time(
          ticket["received_time"], now_dt.time().replace(microsecond=0)
      )

      with col_rd:
        report_date_edit = st.date_input("📅 วันที่แจ้ง", value=init_rep_date)
      with col_rt:
        report_time_edit = st.time_input("⏰ เวลาที่แจ้ง", value=init_rep_time)
      with col_rcd:
        received_date_edit = st.date_input(
            "📅 วันที่รับแจ้ง", value=init_rec_date
        )
      with col_rct:
        received_time_edit = st.time_input(
            "⏰ เวลาที่รับแจ้ง", value=init_rec_time
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

      st.markdown("#### 2️⃣ การดำเนินงานของช่าง (ฝั่งผู้ซ่อม)")

      status_list = ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"]
      curr_status = (
          ticket["status"] if ticket["status"] in status_list else "รอดำเนินการ"
      )

      col_t1, col_t2 = st.columns(2)
      with col_t1:
        new_status = st.selectbox(
            "สถานะการทำงาน",
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
          "วิธีแก้ไข / รายการทำ PM", value=str(ticket["solution"] or "")
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

      st.markdown("🕒 **วันและเวลาที่เสร็จสิ้น (แก้ไขได้)**")

      init_comp_date = parse_date(ticket["completed_date"], now_dt.date())
      init_comp_time = parse_time(
          ticket["completed_time"], now_dt.time().replace(microsecond=0)
      )

      col_cd, col_ct = st.columns(2)
      with col_cd:
        completed_date_edit = st.date_input(
            "📅 วันที่เสร็จสิ้น", value=init_comp_date
        )
      with col_ct:
        completed_time_edit = st.time_input(
            "⏰ เวลาที่เสร็จสิ้น", value=init_comp_time
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
        img_before_b64 = ticket["image_before"]
        if uploaded_before_edit is not None:
          img_before_b64 = compress_and_to_base64(uploaded_before_edit.read())

        img_after_b64 = ticket["image_after"]
        if uploaded_after_edit is not None:
          img_after_b64 = compress_and_to_base64(uploaded_after_edit.read())

        created_at_str = f"{report_date_edit} {report_time_edit.strftime('%H:%M:%S')}+07:00"

        update_data = {
            "ticket_no": ticket_no_edit.strip(),
            "received_no": received_no_edit.strip(),
            "reporter": reporter_edit,
            "job_type": job_type_edit,
            "department": department_edit.strip(),
            "equipment": equipment_edit,
            "description": description_edit,
            "priority": priority_edit,
            "report_date": str(report_date_edit),
            "report_time": report_time_edit.strftime("%H:%M:%S"),
            "received_date": str(received_date_edit),
            "received_time": received_time_edit.strftime("%H:%M:%S"),
            "created_at": created_at_str,
            "image_before": img_before_b64,
            "status": new_status,
            "technician": technician_name,
            "cause": cause_input,
            "solution": solution_input,
            "parts_used": parts_used,
            "parts_qty": parts_qty,
            "image_after": img_after_b64,
        }

        if new_status == "เสร็จสิ้น":
          comp_date_str = str(completed_date_edit)
          comp_time_str = completed_time_edit.strftime("%H:%M:%S")
          update_data["completed_date"] = comp_date_str
          update_data["completed_time"] = comp_time_str
          update_data["completed_at"] = f"{comp_date_str} {comp_time_str}+07:00"

        try:
          supabase.table("repair_requests").update(update_data).eq(
              "id", selected_id
          ).execute()
          st.success(
              f"✅ แก้ไขข้อมูลใบแจ้งซ่อม {ticket_no_edit} เรียบร้อยแล้ว!"
          )
          st.rerun()
        except Exception as e:
          st.error(f"❌ เกิดข้อผิดพลาดในการอัปเดตข้อมูล: {e}")

  else:
    st.info("ยังไม่มีข้อมูลการแจ้งซ่อมในระบบ")

# ==========================================
# --- Tab 3: รายงาน & กราฟ ---
# ==========================================
with tab3:
  st.subheader("📈 สรุปภาพรวม สถิติ และส่งออกข้อมูล")

  if not df_data.empty:
    df_stats = df_data.copy()

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

    count_repair = len(df_stats[df_stats["job_type"] == "แจ้งซ่อม"])
    count_pm = len(df_stats[df_stats["job_type"] == "PM"])

    col_m1, col_m2, col_m3, col_m4, col_m5, col_m6 = st.columns(6)
    col_m1.metric("งานทั้งหมด", len(df_stats))
    col_m2.metric("🛠️ งานแจ้งซ่อม", count_repair)
    col_m3.metric("⚙️ งาน PM", count_pm)
    col_m4.metric(
        "เสร็จสิ้นแล้ว", len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
    )
    col_m5.metric("⏱️ เวลาซ่อมรวมทั้งหมด", format_timedelta(total_time_td))
    col_m6.metric("⌛ เวลาซ่อมเฉลี่ย/งาน", format_timedelta(avg_time_td))

    st.markdown("---")

    col_g1, col_g2, col_g3 = st.columns(3)

    with col_g1:
      period_type = st.selectbox(
          "🗓️ ช่วงเวลาของกราฟแท่ง",
          ["รายวัน", "รายสัปดาห์", "รายเดือน", "รายปี"],
          index=2,
      )

      chart_color_by = st.radio(
          "🎨 แสดงสีแท่งกราฟแยกตาม",
          ["แผนก", "สถานะ", "ประเภทงาน"],
          horizontal=True,
      )

      color_col = (
          "department"
          if chart_color_by == "แผนก"
          else ("status" if chart_color_by == "สถานะ" else "job_type")
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
          df_stats.groupby(["Period", color_col])
          .size()
          .reset_index(name="จำนวนงาน")
      )

      color_map = None
      if color_col == "status":
        color_map = {
            "เสร็จสิ้น": "#28a745",
            "รอดำเนินการ": "#ffc107",
            "ยกเลิก": "#dc3545",
            "กำลังดำเนินการ": "#17a2b8",
        }
      elif color_col == "job_type":
        color_map = {"แจ้งซ่อม": "#007bff", "PM": "#6f42c1"}

      fig_bar = px.bar(
          summary_by_period,
          x="Period",
          y="จำนวนงาน",
          color=color_col,
          title=f"สถิติจำนวนงาน ({period_type}) - แยกตาม{chart_color_by}",
          labels={
              "Period": f"ช่วงเวลา ({period_type})",
              "จำนวนงาน": "รายการ",
              color_col: chart_color_by,
          },
          color_discrete_map=color_map,
          barmode="stack",
          text_auto=True,
      )
      st.plotly_chart(fig_bar, use_container_width=True)

    with col_g2:
      st.markdown("### 📊 สัดส่วนประเภทงาน (แจ้งซ่อม vs PM)")
      job_type_summary = (
          df_stats.groupby("job_type").size().reset_index(name="จำนวนงาน")
      )

      fig_job_pie = px.pie(
          job_type_summary,
          values="จำนวนงาน",
          names="job_type",
          title="สัดส่วนประเภทงาน",
          color="job_type",
          color_discrete_map={"แจ้งซ่อม": "#007bff", "PM": "#6f42c1"},
      )
      st.plotly_chart(fig_job_pie, use_container_width=True)

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
    st.markdown("### 🛠️ ตารางรายงานการทำงาน (เรียงตามวันที่เก่าไปใหม่)")

    df_stats["ระยะเวลาซ่อมรวม"] = df_stats["duration"].apply(format_timedelta)
    df_stats["สถานะรูปหลังซ่อม"] = df_stats["image_after"].apply(
        lambda x: "✅ มีรูป" if str(x).strip() != "" else "❌ ไม่มี"
    )

    report_cols = [
        "ticket_no",
        "received_no",
        "reporter",
        "job_type",
        "department",
        "equipment",
        "description",
        "status",
        "report_date",
        "report_time",
        "received_date",
        "received_time",
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
        "เลขที่ใบแจ้งซ่อม",
        "เลขที่รับแจ้ง",
        "ผู้แจ้ง",
        "ประเภทงาน",
        "แผนก",
        "อุปกรณ์",
        "อาการเสีย / รายละเอียด",
        "สถานะ",
        "วันที่แจ้ง",
        "เวลาแจ้ง",
        "วันที่รับแจ้ง",
        "เวลาที่รับแจ้ง",
        "ช่างผู้ซ่อม",
        "สาเหตุ",
        "วิธีแก้ไข",
        "อะไหล่ที่ใช้",
        "จำนวน",
        "วันที่เสร็จ",
        "เวลาเสร็จ",
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
            writer, index=False, sheet_name="รายงานการซ่อม_PM"
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
