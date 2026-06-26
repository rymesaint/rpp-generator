import streamlit as st
import google.generativeai as genai
import midtransclient
import uuid
import sqlite3
import datetime
import pandas as pd
from dotenv import load_dotenv
import docx
from io import BytesIO

# ==========================================
# 1. KONFIGURASI & SETUP
# ==========================================
load_dotenv()
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None
MIDTRANS_SERVER_KEY = st.secrets.get("MIDTRANS_SERVER_KEY") if "MIDTRANS_SERVER_KEY" in st.secrets else None

st.set_page_config(page_title="RPP Merdeka Generator", page_icon="📚", layout="centered")

# ==========================================
# 2. FUNGSI DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS log_transaksi
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  waktu TEXT, order_id TEXT, mata_pelajaran TEXT,
                  materi TEXT, tipe_rpp TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def simpan_log(order_id, mapel, materi, tipe_rpp, status):
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    waktu = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO log_transaksi (waktu, order_id, mata_pelajaran, materi, tipe_rpp, status) VALUES (?,?,?,?,?,?)",
              (waktu, order_id, mapel, materi, tipe_rpp, status))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 3. FUNGSI BISNIS
# ==========================================
def buat_link_pembayaran(harga, order_id):
    try:
        snap = midtransclient.Snap(is_production=True, server_key=MIDTRANS_SERVER_KEY)
        param = {
            "transaction_details": {"order_id": order_id, "gross_amount": int(harga)},
            "customer_details": {"first_name": "Guru", "email": "guru@contoh.com"}
        }
        transaction = snap.create_transaction(param)
        return transaction['redirect_url']
    except Exception as e:
        st.error(f"Error Midtrans: {e}")
        return None

def generate_rpp_ai(data):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""Bertindak sebagai Ahli Kurikulum. Buatkan Modul Ajar Kurikulum Merdeka DETAIL untuk:
    Mapel: {data['mapel']}, Fase: {data['fase']}, Materi: {data['materi']}, Waktu: {data['waktu']}, Tujuan: {data['tujuan']}.
    Struktur: 1. Informasi Umum, 2. Kegiatan Pembelajaran, 3. Asesmen (HOTS), 4. Lampiran. Gunakan format Markdown."""
    response = model.generate_content(prompt)
    return response.text

# ==========================================
# 4. LOGIKA APLIKASI
# ==========================================
st.title("📚 RPP Kurikulum Merdeka Generator")

# A. Menangkap Redirect dari Midtrans
params = st.query_params
if "transaction_status" in params and params["transaction_status"] == "settlement":
    st.success("✅ Pembayaran terdeteksi! Sedang menyiapkan RPP...")
    order_id_from_url = params.get("order_id")
    # Logika untuk langsung generate jika status settlement
    if 'hasil_rpp' not in st.session_state:
        with st.spinner("AI sedang menyusun materi..."):
            st.session_state.hasil_rpp = generate_rpp_ai(st.session_state.data_rpp)
            simpan_log(order_id_from_url, st.session_state.data_rpp['mapel'], st.session_state.data_rpp['materi'], st.session_state.data_rpp['tipe'], "Settlement")

# B. Tampilan Form
if 'hasil_rpp' not in st.session_state:
    with st.form("rpp_form"):
        st.subheader("Data RPP")
        mapel = st.text_input("Mata Pelajaran:")
        fase = st.text_input("Fase / Kelas:")
        materi = st.text_input("Materi Pokok:")
        waktu = st.text_input("Alokasi Waktu:")
        tujuan = st.text_area("Tujuan Pembelajaran:")
        tipe = st.radio("Pilih layanan:", ["RPP Standar (Rp 5.000)", "Modul Ajar PRO (Rp 10.000)"])
        submit = st.form_submit_button("Lanjut Pembayaran")

    if submit:
        harga = 5000 if "Standar" in tipe else 10000
        order_id = f"RPP-{str(uuid.uuid4().hex[:8]).upper()}"
        st.session_state.data_rpp = {"mapel": mapel, "fase": fase, "materi": materi, "waktu": waktu, "tujuan": tujuan, "tipe": tipe}
        
        url = buat_link_pembayaran(harga, order_id)
        if url:
            st.session_state.payment_url = url
            st.rerun()

# C. Tombol Pembayaran
if 'payment_url' in st.session_state and 'hasil_rpp' not in st.session_state:
    st.info("Selesaikan pembayaran untuk melanjutkan.")
    st.link_button("👉 KLIK UNTUK BAYAR", url=st.session_state.payment_url, type="primary")

# D. Menampilkan Hasil
if 'hasil_rpp' in st.session_state:
    st.subheader("Hasil RPP Anda")
    st.markdown(st.session_state.hasil_rpp)
    if st.button("Buat Baru"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
