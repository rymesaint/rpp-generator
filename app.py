import streamlit as st
import google.generativeai as genai
import midtransclient
import uuid
import sqlite3
import datetime
import pandas as pd
from io import BytesIO
import docx

# ==========================================
# 1. KONFIGURASI & SETUP
# ==========================================
# Gunakan st.secrets untuk keamanan di Streamlit Cloud
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
MIDTRANS_SERVER_KEY = st.secrets["MIDTRANS_SERVER_KEY"]

st.set_page_config(page_title="RPP Merdeka Generator", page_icon="📚", layout="centered")

# ==========================================
# 2. FUNGSI DATABASE (DENGAN PENYIMPANAN LENGKAP)
# ==========================================
def init_db():
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS log_transaksi
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id TEXT, mapel TEXT, fase TEXT, materi TEXT, 
                  waktu_durasi TEXT, tujuan TEXT, tipe_rpp TEXT, status TEXT)''')
    conn.commit()
    conn.close()

def simpan_data_input(order_id, data):
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    c.execute("INSERT INTO log_transaksi (order_id, mapel, fase, materi, waktu_durasi, tujuan, tipe_rpp, status) VALUES (?,?,?,?,?,?,?,?)",
              (order_id, data['mapel'], data['fase'], data['materi'], data['waktu'], data['tujuan'], data['tipe'], "Pending"))
    conn.commit()
    conn.close()

def update_status_db(order_id, status):
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    c.execute("UPDATE log_transaksi SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    conn.close()

def ambil_data_by_order_id(order_id):
    conn = sqlite3.connect('rpp_logs.db')
    c = conn.cursor()
    c.execute("SELECT mapel, fase, materi, waktu_durasi, tujuan, tipe_rpp FROM log_transaksi WHERE order_id = ?", (order_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"mapel": row[0], "fase": row[1], "materi": row[2], "waktu": row[3], "tujuan": row[4], "tipe": row[5]}
    return None

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

# A. Deteksi Redirect Midtrans
params = st.query_params
if "transaction_status" in params and params["transaction_status"] == "settlement":
    order_id = params.get("order_id")
    
    # Ambil data dari DB berdasarkan order_id
    data_tersimpan = ambil_data_by_order_id(order_id)
    
    if data_tersimpan:
        st.success("✅ Pembayaran terdeteksi! Sedang menyiapkan RPP...")
        if 'hasil_rpp' not in st.session_state:
            with st.spinner("AI sedang menyusun materi..."):
                st.session_state.hasil_rpp = generate_rpp_ai(data_tersimpan)
                update_status_db(order_id, "Settlement")
    else:
        st.error("Data transaksi tidak ditemukan (session expired).")

# B. Form Input
if 'hasil_rpp' not in st.session_state:
    with st.form("rpp_form"):
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
        
        data_input = {"mapel": mapel, "fase": fase, "materi": materi, "waktu": waktu, "tujuan": tujuan, "tipe": tipe}
        
        # Simpan ke DB sebelum redirect
        simpan_data_input(order_id, data_input)
        
        url = buat_link_pembayaran(harga, order_id)
        if url:
            st.session_state.payment_url = url
            st.rerun()

# C. Tombol Bayar
if 'payment_url' in st.session_state and 'hasil_rpp' not in st.session_state:
    st.info("Selesaikan pembayaran untuk melanjutkan.")
    st.link_button("👉 KLIK UNTUK BAYAR", url=st.session_state.payment_url, type="primary")

# D. Hasil
if 'hasil_rpp' in st.session_state:
    st.subheader("Hasil RPP Anda")
    st.markdown(st.session_state.hasil_rpp)
    if st.button("Buat RPP Baru"):
        st.session_state.clear()
        st.rerun()
