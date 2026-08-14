import io
import sqlite3
from datetime import datetime
import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st

# --- 1. ตั้งค่าฐานข้อมูล SQLite (เพิ่มคอลัมน์ image_after) ---
conn = sqlite3.connect("repair_system_v4.db", check_same_thread=False)
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
    created_at TEXT NOT NULL,
    image BLOB,
    technician TEXT,
    parts_used TEXT,
    parts_qty TEXT,
    completed_at TEXT,
    image_after BLOB -- เพิ่มคอลัมน์เก็บรูปหลังซ่อม
)
"""
)
conn.commit()

# --- 2. ตั้งค่าหน้าตาแอป Streamlit ---
st.set_page_config(
    page_title="ระบบแจ้งซ่อมและบันทึกผลงาน", page_icon="🛠️", layout="wide"
)

st.title("🛠️ ระบบแจ้งซ่อม บันทึกผลงาน (ก่อน/หลังซ่อม) และรายงาน")

tab1, tab2, tab3 = st.tabs(
    [
        "📝 ส่งใบแจ้งซ่อม",
        "⚙️ บันทึกงานซ่อม (สำหรับช่าง)",
        "📊 รายงาน & กราฟสรุปประจำเดือน",
    ]
)

# ==========================================
# --- Tab 1: ฟอร์มแจ้งซ่อม (ฝั่งผู้ใช้งาน) ---
# ==========================================
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
        uploaded_file = st.file_uploader(
            "📷 แนบรูปภาพอุปกรณ์เสียก่อนซ่อม (ถ้ามี)",
            type=["jpg", "png", "jpeg"],
        )

        submit_button = st.form_submit_button(label="ส่งข้อมูลแจ้งซ่อม")

        if submit_button:
            if reporter and equipment and description:
                image_bytes = None
                if uploaded_file is not None:
                    image_bytes = uploaded_file.read()

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute(
                    """
                    INSERT INTO repair_tickets (reporter, equipment, description, priority, status, created_at, image)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        reporter,
                        equipment,
                        description,
                        priority,
                        "รอดำเนินการ",
                        now,
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
    st.subheader("จัดการ อัปเดตงานซ่อม และแนบรูปหลังซ่อม")

    c.execute("SELECT id FROM repair_tickets ORDER BY id DESC")
    ticket_ids = [row[0] for row in c.fetchall()]

    if ticket_ids:
        # แสดงตารางรายการทั้งหมด
        df_all = pd.read_sql_query(
            """
            SELECT 
                id AS 'ID', reporter AS 'ผู้แจ้ง', equipment AS 'อุปกรณ์', 
                priority AS 'ความเร่งด่วน', status AS 'สถานะ', 
                technician AS 'ผู้ซ่อม', parts_used AS 'อะไหล่ที่ใช้', 
                parts_qty AS 'จำนวน', created_at AS 'เวลาแจ้ง', completed_at AS 'เวลาซ่อมเสร็จ'
            FROM repair_tickets ORDER BY id DESC
        """,
            conn,
        )
        st.dataframe(df_all, use_container_width=True)

        st.markdown("---")

        selected_id = st.selectbox(
            "เลือก ID ที่ต้องการอัปเดตงานซ่อม", ticket_ids
        )

        # ดึงข้อมูลของ ID ที่เลือก
        c.execute("SELECT * FROM repair_tickets WHERE id=?", (selected_id,))
        ticket = c.fetchone()

        if ticket:
            # โครงสร้างตาราง:
            # (0:id, 1:reporter, 2:equipment, 3:description, 4:priority, 5:status, 6:created_at, 7:image, 8:technician, 9:parts_used, 10:parts_qty, 11:completed_at, 12:image_after)

            col_info, col_form = st.columns([1, 1])

            with col_info:
                st.markdown(
                    f"### 🔍 รายละเอียดใบแจ้งซ่อม ID: **{ticket[0]}**"
                )
                st.write(f"**ผู้แจ้ง:** {ticket[1]}")
                st.write(f"**อุปกรณ์:** {ticket[2]}")
                st.write(f"**ความเร่งด่วน:** {ticket[4]}")
                st.write(f"**เวลาแจ้ง:** {ticket[6]}")
                st.info(f"**อาการเสีย:** {ticket[3]}")

                # แสดงเปรียบเทียบรูปก่อนซ่อมและหลังซ่อม
                st.markdown("#### 🖼️ เปรียบเทียบรูปภาพก่อน-หลังซ่อม")
                img_col1, img_col2 = st.columns(2)

                with img_col1:
                    st.caption("📷 **ก่อนซ่อม**")
                    if ticket[7]:
                        img_before = Image.open(io.BytesIO(ticket[7]))
                        st.image(img_before, use_container_width=True)
                    else:
                        st.text("ไม่มีรูปก่อนซ่อม")

                with img_col2:
                    st.caption("✅ **หลังซ่อมเสร็จ**")
                    if ticket[12]:
                        img_after = Image.open(io.BytesIO(ticket[12]))
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
                        status_list.index(ticket[5])
                        if ticket[5] in status_list
                        else 0
                    )

                    new_status = st.selectbox(
                        "สถานะการซ่อม", status_list, index=curr_status_idx
                    )
                    technician_name = st.text_input(
                        "ชื่อผู้ซ่อม / ช่างผู้รับผิดชอบ", value=ticket[8] or ""
                    )
                    parts_used = st.text_input(
                        "อะไหล่ที่ใช้ (เช่น น็อต M6, สายไฟ)",
                        value=ticket[9] or "",
                    )
                    parts_qty = st.text_input(
                        "จำนวนอะไหล่ (เช่น 2 ตัว, 1 เมตร)",
                        value=ticket[10] or "",
                    )

                    # อัปโหลดรูปหลังซ่อม
                    uploaded_after = st.file_uploader(
                        "📷 แนบรูปถ่ายหลังซ่อมเสร็จ",
                        type=["jpg", "png", "jpeg"],
                    )

                    save_btn = st.form_submit_button("💾 บันทึกข้อมูลงานซ่อม")

                    if save_btn:
                        # จัดการรูปหลังซ่อม
                        image_after_bytes = ticket[12]  # ใช้รูปเดิมถ้าไม่มีการอัปโหลดใหม่
                        if uploaded_after is not None:
                            image_after_bytes = uploaded_after.read()

                        # บันทึกเวลาซ่อมเสร็จอัตโนมัติเมื่อเลือกสถานะ 'เสร็จสิ้น'
                        completed_time = ticket[11]
                        if new_status == "เสร็จสิ้น" and not completed_time:
                            completed_time = datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )

                        c.execute(
                            """
                            UPDATE repair_tickets 
                            SET status=?, technician=?, parts_used=?, parts_qty=?, completed_at=?, image_after=?
                            WHERE id=?
                        """,
                            (
                                new_status,
                                technician_name,
                                parts_used,
                                parts_qty,
                                completed_time,
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
# --- Tab 3: สรุปรายงาน & กราฟประจำเดือน (Dashboard) ---
# ===================================================
with tab3:
    st.subheader("📈 สรุปภาพรวมและสถิติการแจ้งซ่อม")

    df_stats = pd.read_sql_query("SELECT * FROM repair_tickets", conn)

    if not df_stats.empty:
        df_stats["created_at_dt"] = pd.to_datetime(df_stats["created_at"])
        df_stats["YearMonth"] = df_stats["created_at_dt"].dt.strftime("%Y-%m")

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("จำนวนแจ้งซ่อมทั้งหมด", len(df_stats))
        col_m2.metric(
            "ซ่อมเสร็จสิ้นแล้ว", len(df_stats[df_stats["status"] == "เสร็จสิ้น"])
        )
        col_m3.metric(
            "กำลังดำเนินการ",
            len(df_stats[df_stats["status"] == "กำลังดำเนินการ"]),
        )
        col_m4.metric(
            "รอดำเนินการ", len(df_stats[df_stats["status"] == "รอดำเนินการ"])
        )

        st.markdown("---")

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.markdown("### 🗓️ สถิติการแจ้งซ่อมรายเดือน")
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
                title="จำนวนใบแจ้งซ่อมในแต่ละเดือน (แยกตามสถานะ)",
                labels={"YearMonth": "เดือน (ปี-เดือน)", "จำนวนงาน": "จำนวนรายการ"},
                barmode="stack",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_g2:
            st.markdown("### 🚨 สัดส่วนความเร่งด่วนของงานซ่อม")
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
        st.markdown("### 🛠️ รายงานการซ่อมและอะไหล่ที่ใช้")

        completed_df = df_stats[df_stats["technician"].notna()][
            [
                "id",
                "equipment",
                "technician",
                "parts_used",
                "parts_qty",
                "created_at",
                "completed_at",
            ]
        ].copy()

        # เช็กว่ารายการไหนมีรูปหลังซ่อมบ้าง
        completed_df["รูปหลังซ่อม"] = df_stats["image_after"].apply(
            lambda x: "✅ มีรูป" if x is not None else "❌ ไม่มี"
        )

        completed_df.columns = [
            "ID",
            "อุปกรณ์",
            "ช่างผู้ซ่อม",
            "อะไหล่ที่ใช้",
            "จำนวน",
            "เวลาแจ้งซ่อม",
            "เวลาซ่อมเสร็จ",
            "สถานะรูปหลังซ่อม",
        ]
        st.dataframe(completed_df, use_container_width=True)

    else:
        st.info("ยังไม่มีข้อมูลสำหรับสร้างกราฟสรุปผล")

conn.close()
