import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="CMMS Maintenance Demo", page_icon="🔧", layout="wide")
st.title("🔧 ระบบซ่อมบำรุง CMMS")
st.caption("เวอร์ชันทดลอง • ข้อมูลเก็บเฉพาะใน session ไม่ใช่ฐานข้อมูลถาวร")
if "tickets" not in st.session_state:
    st.session_state.tickets = []
if "pm" not in st.session_state:
    st.session_state.pm = []
menu = st.sidebar.radio("เมนู", ["Dashboard", "ใบแจ้งซ่อม", "แผน PM", "ทะเบียนเครื่องจักร", "คลังอะไหล่", "รายงาน"])
machines = ["AC-001", "Shot Blast", "Air Dryer", "Conveyor Line"]
if menu == "Dashboard":
    a,b,c = st.columns(3)
    a.metric("ใบแจ้งซ่อม",len(st.session_state.tickets))
    b.metric("รอดำเนินการ",sum(t["สถานะ"]=="รอดำเนินการ" for t in st.session_state.tickets))
    c.metric("งาน PM",len(st.session_state.pm))
    if st.session_state.tickets:
        st.bar_chart(pd.DataFrame(st.session_state.tickets)["เครื่องจักร"].value_counts())
elif menu == "ใบแจ้งซ่อม":
    with st.form("repair",clear_on_submit=False):
        machine=st.selectbox("เครื่องจักร",machines)
        kind=st.selectbox("ประเภทงาน",["Breakdown","Corrective","Other"])
        urgency=st.selectbox("ความเร่งด่วน",["Critical","High","Medium","Low"])
        symptom=st.text_area("อาการเสีย",value="ไม่ทำงาน")
        photos=st.file_uploader("แนบรูปภาพ",type=["png","jpg","jpeg"],accept_multiple_files=True)
        videos=st.file_uploader("แนบวิดีโอ",type=["mp4","mov"],accept_multiple_files=True)
        submitted=st.form_submit_button("บันทึกใบแจ้งซ่อมทดลอง")
    if submitted:
        if not symptom.strip():
            st.error("กรุณาระบุอาการเสีย")
        else:
            st.session_state.tickets.append({"เลขที่":f"DEMO-{len(st.session_state.tickets)+1:04d}","วันที่":datetime.now().strftime("%Y-%m-%d %H:%M"),"เครื่องจักร":machine,"ประเภท":kind,"ความเร่งด่วน":urgency,"อาการ":symptom,"สถานะ":"รอดำเนินการ","รูปภาพ":len(photos),"วิดีโอ":len(videos)})
            st.success("เพิ่มรายการทดลองแล้ว (ไฟล์แนบยังไม่จัดเก็บถาวร)")
    st.dataframe(pd.DataFrame(st.session_state.tickets),use_container_width=True)
elif menu == "แผน PM":
    with st.form("pm"):
        machine=st.selectbox("เครื่องจักร",machines)
        task=st.text_input("รายการตรวจ")
        freq=st.selectbox("ความถี่",["Daily","Weekly","Monthly","Yearly"])
        if st.form_submit_button("เพิ่มแผน PM"):
            if task.strip():
                st.session_state.pm.append({"เครื่องจักร":machine,"รายการ":task,"ความถี่":freq,"สถานะ":"รอดำเนินการ"})
                st.success("เพิ่มแผนทดลองแล้ว")
            else: st.error("กรุณาระบุรายการตรวจ")
    st.dataframe(pd.DataFrame(st.session_state.pm),use_container_width=True)
elif menu == "ทะเบียนเครื่องจักร":
    st.dataframe(pd.DataFrame({"รหัส/ชื่อเครื่องจักร":machines}),use_container_width=True)
elif menu == "คลังอะไหล่":
    st.info("โมดูลคลังอะไหล่: เตรียมเชื่อมต่อฐานข้อมูลในเวอร์ชันถัดไป")
else:
    st.subheader("รายงานใบแจ้งซ่อม")
    data=pd.DataFrame(st.session_state.tickets)
    st.dataframe(data,use_container_width=True)
    st.download_button("ดาวน์โหลด CSV",data.to_csv(index=False).encode("utf-8-sig"),"repair_demo.csv","text/csv")
