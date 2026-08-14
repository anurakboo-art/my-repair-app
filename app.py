import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st

# 1. ตั้งค่าฐานข้อมูล SQLite สำหรับเก็บข้อมูล
conn = sqlite3.connect("repair_requests.db", check_same_thread=False)
c = conn.cursor()

c.execute(
    """
CREATE TABLE IF NOT EXISTS repair_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reporter TEXT NOT NULL,
    equipment TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""
)
conn.commit()

# 2. ตั้งค่าหน้าตาแอป Streamlit
st.set_page_config(
    page_title="ระบบแจ้งซ่อม (Repair Request)", page_icon="🛠️", layout="wide"
)

st.title("🛠️ ระบบแจ้งซ่อมและติดตามสถานะ")

tab1, tab2 = st.tabs(["📝 ส่งใบแจ้งซ่อม", "📊 รายการแจ้งซ่อมทั้งหมด"])

# --- Tab 1: ฟอร์มแจ้งซ่อม ---
with tab1:
    st.subheader("กรอกข้อมูลการแจ้งซ่อม")
    with st.form(key="repair_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            reporter = st.text_input("ชื่อผู้แจ้ง *")
            equipment = st.text_input("อุปกรณ์ / สถานที่ ที่ต้องการแจ้งซ่อม *")
        with col2:
            priority = st.selectbox(
                "ระดับความเร่งด่วน", ["ปกติ", "ด่วน", "ด่วนที่สุด"]
            )

        description = st.text_area("รายละเอียดปัญหาอาการเสีย *")

        submit_button = st.form_submit_button(label="ส่งข้อมูลแจ้งซ่อม")

        if submit_button:
            if reporter and equipment and description:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute(
                    """
                    INSERT INTO repair_tickets (reporter, equipment, description, priority, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        reporter,
                        equipment,
                        description,
                        priority,
                        "รอดำเนินการ",
                        now,
                    ),
                )
                conn.commit()
                st.success("✅ ส่งข้อมูลแจ้งซ่อมเรียบร้อยแล้ว!")
            else:
                st.warning("⚠️ กรุณากรอกข้อมูลที่มีเครื่องหมาย * ให้ครบถ้วน")

# --- Tab 2: ตารางดูรายการ & อัปเดตสถานะ ---
with tab2:
    st.subheader("รายการแจ้งซ่อมทั้งหมด")

    # ดึงข้อมูลจากฐานข้อมูล
    df = pd.read_sql_query(
        "SELECT id AS 'ID', reporter AS 'ผู้แจ้ง', equipment AS 'อุปกรณ์', description AS 'อาการเสีย', priority AS 'ความเร่งด่วน', status AS 'สถานะ', created_at AS 'เวลาแจ้ง' FROM repair_tickets ORDER BY id DESC",
        conn,
    )

    if not df.empty:
        st.dataframe(df, use_container_width=True)

        st.markdown("---")
        st.subheader("⚙️ อัปเดตสถานะการซ่อม (สำหรับช่าง / แอดมิน)")

        col_id, col_status, col_btn = st.columns([1, 2, 1])
        with col_id:
            ticket_id = st.selectbox(
                "เลือก ID ที่ต้องการอัปเดต", df["ID"].tolist()
            )
        with col_status:
            new_status = st.selectbox(
                "เปลี่ยนสถานะเป็น",
                ["รอดำเนินการ", "กำลังดำเนินการ", "เสร็จสิ้น", "ยกเลิก"],
            )
        with col_btn:
            st.write(" ")  # จัดระยะ
            st.write(" ")
            if st.button("อัปเดตสถานะ"):
                c.execute(
                    "UPDATE repair_tickets SET status = ? WHERE id = ?",
                    (new_status, ticket_id),
                )
                conn.commit()
                st.success(
                    f"อัปเดต ID {ticket_id} เป็น '{new_status}' เรียบร้อย!"
                )
                st.rerun()
    else:
        st.info("ยังไม่มีข้อมูลการแจ้งซ่อมในระบบ")