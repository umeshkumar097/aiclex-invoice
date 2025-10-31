# invoice_app.py
# Crux Invoice Management System (with bulk client upload + verification)
# Built by Aiclex Technologies
#
# Requirements:
# pip install streamlit pandas reportlab num2words openpyxl requests

import streamlit as st
import sqlite3
from datetime import date, datetime
import pandas as pd
import os
import traceback
import requests
from num2words import num2words
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
import io
import csv
import time

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, Flowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------------- App constants ----------------
APP_TITLE = "Crux Invoice Management System"
APP_BUILT_BY = "Built by Aiclex Technologies"
DB_PATH = "invoices.db"
PDF_DIR = "generated_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

# ---------------- Company & asset paths (.jpg) ----------------
COMPANY = {
    "name": "CRUX MANAGEMENT SERVICES (P) LTD",
    "gstin": "36AABCC4754D1ZX",
    "pan": "AABCC4754D",
    "phone": "040-66345537",
    "bank_name": "HDFC BANK",
    "bank_account": "00212320004244",
    "ifsc": "HDFC0000021",
    "swift": "HDFCINBBHYD",
    "micr": "500240002",
    "branch": "LAKDIKAPUL, HYD-004",
    "address": "#403, 4th Floor, Diamond Block, Lumbini Rockdale, Somajiguda, Hyderabad - 500082, Telangana",
    "email": "mailadmin@cruxmanagement.com",
    "logo_top": "assets/logo_top.jpg",
    "company_text": "assets/company_text.jpg",
    "tagline": "assets/tagline.jpg",
    "signature": "assets/signature_stamp.jpg"
}

# ---------------- Styles ----------------
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='wrap', fontSize=9, leading=11))
styles.add(ParagraphStyle(name='title_center', fontSize=18, leading=20, alignment=1))
styles.add(ParagraphStyle(name='small_right', fontSize=9, alignment=2))
styles.add(ParagraphStyle(name='footer', fontSize=7, alignment=1, leading=9))

# ---------------- Helpers ----------------
def money(v):
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def rupees_in_words(amount):
    try:
        amt = float(amount)
    except:
        return ""
    rupees = int(amt)
    paise = int(round((amt - rupees) * 100))
    parts = []
    if rupees > 0:
        parts.append(num2words(rupees, lang='en_IN').replace('-', ' ').title() + " Rupees")
    if paise > 0:
        parts.append(num2words(paise, lang='en_IN').replace('-', ' ').title() + " Paise")
    if not parts:
        return "Zero Rupees Only"
    return " and ".join(parts) + " Only"

def gst_state_code(gstin):
    try:
        return int(str(gstin).strip()[:2])
    except:
        return None

def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
        except Exception:
            pass

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, gstin TEXT UNIQUE, pan TEXT, address TEXT, email TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT, invoice_date TEXT, client_id INTEGER,
            subtotal REAL, sgst REAL, cgst REAL, igst REAL, total REAL, pdf_path TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_clients():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id,name,gstin,address,email FROM clients ORDER BY name").fetchall()
    conn.close()
    return rows

def get_client_by_id(cid):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id,name,gstin,pan,address,email FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return row

def add_client(name, gstin, pan, address, email=""):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO clients (name,gstin,pan,address,email) VALUES (?,?,?,?,?)", (name,gstin,pan,address,email))
        conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_client(cid, name, gstin, pan, address, email=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET name=?,gstin=?,pan=?,address=?,email=? WHERE id=?", (name,gstin,pan,address,email,cid))
    conn.commit()
    conn.close()

def delete_client(cid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit()
    conn.close()

# ---------------- GST API (Appyflow) ----------------
def fetch_gst_from_appyflow(gstin, timeout=10):
    gstin = str(gstin).strip()
    if not gstin:
        return {"ok": False, "error": "Empty GSTIN"}

    key_secret = None
    try:
        key_secret = st.secrets["appyflow"]["key_secret"]
    except Exception:
        key_secret = os.getenv("APPYFLOW_KEY_SECRET")

    if not key_secret:
        return {"ok": False, "error": "API key missing in secrets."}

    url = "https://appyflow.in/api/verifyGST"
    params = {"key_secret": key_secret, "gstNo": gstin}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Request failed: {e}"}

    # Parse
    if isinstance(j, dict) and ("taxpayerInfo" in j or j.get("error") is False or j.get("status") == "success"):
        info = j.get("taxpayerInfo") or j.get("taxpayerinfo") or j.get("taxpayer") or j
        name = info.get("tradeNam") or info.get("lgnm") or info.get("tradeName") or info.get("name") or ""
        addr = ""
        try:
            pradr = info.get("pradr", {}) or {}
            a = pradr.get("addr", {}) or {}
            parts = []
            for k in ("bno","st","loc","city","dst","pncd","stcd","bn","addr1","addr2"):
                v = a.get(k) or a.get(k.upper()) or a.get(k.lower())
                if v:
                    parts.append(str(v))
            addr = ", ".join(parts)
        except:
            addr = ""
        pan = None
        for pk in ("pan", "panno", "panNo", "PAN"):
            if info.get(pk):
                pan = str(info.get(pk)).strip()
                break
        if not pan and len(gstin) >= 12:
            pan = gstin[2:12].upper()
        gstout = info.get("gstin") or gstin
        return {"ok": True, "name": name, "address": addr, "gstin": gstout, "pan": pan, "raw": j}
    else:
        msg = j.get("message") if isinstance(j, dict) else str(j)
        return {"ok": False, "error": msg or "API returned error"}

# ---------------- HR Flowable ----------------
class HR(Flowable):
    def __init__(self, width, thickness=1, color=colors.black):
        Flowable.__init__(self)
        self.width = width; self.thickness = thickness; self.color = color
    def draw(self):
        self.canv.setLineWidth(self.thickness)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0,0,self.width,0)

# ---------------- PDF generation (use your improved function here) ----------------
# For brevity, add the improved generate_invoice_pdf function from earlier messages.
# (Paste the full generate_invoice_pdf implementation you prefer here.)
def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    # Minimal PDF generator (replace with your improved function if you have it)
    from decimal import Decimal, ROUND_HALF_UP
    filename = f"Invoice_{invoice_meta.get('invoice_no','NA')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    story = []
    story.append(Paragraph("INVOICE (Sample)", styles['title_center']))
    story.append(Spacer(1,12))
    story.append(Paragraph(f"Invoice No: {invoice_meta.get('invoice_no')}", styles['wrap']))
    story.append(Paragraph(f"Client: {invoice_meta.get('client',{}).get('name','')}", styles['wrap']))
    story.append(Spacer(1,12))
    data = [["S.No","Particulars","Qty","Rate","Amount"]]
    for r in line_items:
        amt = float(r.get('qty',0)) * float(r.get('rate',0))
        data.append([str(r.get('slno','')), r.get('particulars',''), str(r.get('qty','')), str(r.get('rate','')), f"Rs. {amt:.2f}"])
    t = Table(data)
    t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.black)]))
    story.append(t)
    doc.build(story)
    return path

# ---------------- Bulk processing helpers ----------------
def normalize_uploaded_df(df):
    # Ensure columns lower-case keys for easier mapping
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # common column names mapping
    lower = {c.lower(): c for c in df.columns}
    mapping = {}
    for expected in ("gstin","gst","gst_no","gst_no.","gst_no","gst number"):
        if expected in lower:
            mapping['gstin'] = lower[expected]; break
    for expected in ("name","company","company_name","business_name","trade_name"):
        if expected in lower:
            mapping['name'] = lower[expected]; break
    for expected in ("address","addr","company_address"):
        if expected in lower:
            mapping['address'] = lower[expected]; break
    for expected in ("pan","pan_no","panno"):
        if expected in lower:
            mapping['pan'] = lower[expected]; break

    # If gstin not found but first column looks like GSTIN, assume first column
    if 'gstin' not in mapping:
        mapping['gstin'] = df.columns[0] if len(df.columns) > 0 else None

    # Build a standard df with columns gstin,name,address,pan
    out_rows = []
    for _, row in df.iterrows():
        gstin_val = row.get(mapping.get('gstin')) if mapping.get('gstin') else ''
        name_val = row.get(mapping.get('name')) if mapping.get('name') else ''
        address_val = row.get(mapping.get('address')) if mapping.get('address') else ''
        pan_val = row.get(mapping.get('pan')) if mapping.get('pan') else ''
        out_rows.append({
            "gstin": str(gstin_val).strip(),
            "name": str(name_val).strip(),
            "address": str(address_val).strip(),
            "pan": str(pan_val).strip()
        })
    return pd.DataFrame(out_rows)

def bulk_verify_and_prepare(df, verify_with_api=True, delay_between_calls=0.2, show_progress=True):
    """
    df: DataFrame with columns gstin,name,address,pan (normalized)
    verify_with_api: if True, call GST API for each gstin
    Returns a DataFrame with columns: gstin, name, address, pan, status, error
    status: "OK" if verified (or verification skipped but initial data present), "Failed" if verification failed
    """
    results = []
    total = len(df)
    progress = None
    if show_progress and total > 0:
        progress = st.progress(0)
    for i, row in df.iterrows():
        gstin = str(row.get('gstin','')).strip()
        given_name = row.get('name','') or ""
        given_addr = row.get('address','') or ""
        given_pan = row.get('pan','') or ""
        res_name = ""
        res_addr = ""
        res_pan = ""
        status = "Manual"
        error = ""
        if not gstin:
            status = "Failed"
            error = "Empty GSTIN"
        else:
            if verify_with_api:
                api_res = fetch_gst_from_appyflow(gstin)
                if api_res.get("ok"):
                    res_name = api_res.get("name","") or given_name
                    res_addr = api_res.get("address","") or given_addr
                    res_pan = api_res.get("pan","") or given_pan
                    status = "OK"
                else:
                    # verification failed — keep given values for manual review
                    status = "Failed"
                    error = api_res.get("error","API failed")
            else:
                # No verification, accept provided values
                res_name = given_name
                res_addr = given_addr
                res_pan = given_pan if given_pan else (gstin[2:12].upper() if len(gstin)>=12 else "")
                status = "OK" if res_name or res_addr else "Manual"
        results.append({
            "gstin": gstin,
            "name": res_name,
            "address": res_addr,
            "pan": res_pan,
            "status": status,
            "error": error
        })
        if show_progress:
            progress.progress(int((i+1)/total * 100))
        # delay lightly to avoid hammering API
        if verify_with_api:
            time.sleep(delay_between_calls)
    if show_progress:
        progress.empty()
    return pd.DataFrame(results)

def add_successful_results_to_db(results_df, only_status="OK"):
    """
    Add rows with results_df['status']==only_status to DB.
    Returns (added_count, failed_list)
    """
    added = 0
    failed = []
    for _, row in results_df.iterrows():
        if row.get('status') == only_status:
            ok, err = add_client(row.get('name') or "", row.get('gstin') or "", row.get('pan') or "", row.get('address') or "", "")
            if ok:
                added += 1
            else:
                failed.append({"gstin": row.get('gstin'), "error": err})
    return added, failed

# ---------------- Authentication UI ----------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.get("authenticated"):
        val = st.sidebar.select_slider("Session", options=["Stay Logged In", "Logout"], value="Stay Logged In")
        if val == "Logout":
            st.session_state.authenticated = False
            safe_rerun()
        cols = st.columns([1,2,1])
        with cols[1]:
            st.markdown("**Logged in**")
        return True

    st.write("**Enter password to continue**")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        password = None
        try:
            password = st.secrets["app"]["password"]
        except Exception:
            password = os.getenv("APP_PASSWORD")
        if password is None:
            st.warning("No app password set in Streamlit secrets or APP_PASSWORD environment variable.")
            return False
        if pwd == password:
            st.session_state.authenticated = True
            st.success("Logged in")
            safe_rerun()
            return True
        else:
            st.error("Incorrect password")
            return False
    return False

# ---------------- Streamlit UI ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(APP_BUILT_BY)
    init_db()

    # Authentication gate
    if not check_password():
        return

    mode = st.sidebar.selectbox("Mode", ["Manage Clients", "Create Invoice", "History"])

    # ----- Manage Clients -----
    if mode == "Manage Clients":
        st.header("Manage Clients")
        clients = get_clients()
        if clients:
            dfc = pd.DataFrame(clients, columns=['id','name','gstin','address','email'])
            st.dataframe(dfc[['name','gstin','address']])

        # Add client (form)
        st.subheader("Add New Client")
        with st.form("add_client_form"):
            gstin_input = st.text_input("GSTIN", value="", max_chars=15)
            name = st.text_input("Company Name")
            pan = st.text_input("PAN (optional)")
            address = st.text_area("Address")
            submitted = st.form_submit_button("Save Client")
            if submitted:
                if not name:
                    st.error("Name is required")
                else:
                    ok, err = add_client(name, gstin_input, pan, address, email="")
                    if ok:
                        st.success("Client saved")
                        safe_rerun()
                    else:
                        st.error(f"Could not save client: {err}")

        # Fetch from GST API (single-step)
        st.subheader("Fetch GST Details (one-by-one)")
        gst_fetch = st.text_input("GSTIN to fetch (for auto-fill)", value="", key="gst_fetch_input")
        if st.button("Fetch GST Details"):
            if not gst_fetch.strip():
                st.error("Enter GSTIN first")
            else:
                with st.spinner("Fetching from GST API..."):
                    res = fetch_gst_from_appyflow(gst_fetch)
                st.session_state._last_gst_fetch = res
        # If fetch result exists, show save option (not nested)
        last = st.session_state.get("_last_gst_fetch")
        if last:
            if last.get("ok"):
                st.success("Fetched — verify and Save")
                name_f = st.text_input("Company Name (fetched)", value=last.get("name",""), key="fetched_name")
                address_f = st.text_area("Address (fetched)", value=last.get("address",""), key="fetched_addr")
                gstin_f = st.text_input("GSTIN (fetched)", value=last.get("gstin",""), key="fetched_gstin")
                pan_f = st.text_input("PAN (fetched)", value=last.get("pan",""), key="fetched_pan")
                if st.button("Save Fetched Client"):
                    if not name_f:
                        st.error("Name required")
                    else:
                        ok, err = add_client(name_f, gstin_f, pan_f, address_f, email="")
                        if ok:
                            st.success("Client saved (from API)")
                            st.session_state._last_gst_fetch = None
                            safe_rerun()
                        else:
                            st.error(f"Save error: {err}")
            else:
                st.error(f"Fetch error: {last.get('error')}")
                st.session_state._last_gst_fetch = None

        # Bulk Upload
        st.subheader("Bulk Upload Clients (CSV / XLSX)")
        st.markdown("Upload a file with columns: `gstin`, `name` (optional), `address` (optional), `pan` (optional).")
        uploaded = st.file_uploader("Upload clients file", type=["csv","xlsx"])
        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    df_raw = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
                else:
                    df_raw = pd.read_excel(uploaded, dtype=str)
                st.success(f"File loaded: {uploaded.name} (rows: {len(df_raw)})")
                st.dataframe(df_raw.head(10))
                # Normalize
                df_norm = normalize_uploaded_df(df_raw)
                st.session_state._bulk_df = df_norm
            except Exception as e:
                st.error(f"Error reading file: {e}")
                st.session_state._bulk_df = None

        bulk_df = st.session_state.get("_bulk_df")
        if bulk_df is not None:
            st.markdown("**Preview (normalized)**")
            st.dataframe(bulk_df.head(20))

            # Options
            col1, col2 = st.columns(2)
            with col1:
                verify_api = st.checkbox("Verify each GST using GST API (appyflow)", value=True)
            with col2:
                crux_mode = st.checkbox("Crux Team Mode (auto-add verified to DB)", value=False)

            # Process button
            if st.button("Process & Verify (bulk)"):
                if verify_api:
                    # check api key
                    key_present = False
                    try:
                        if st.secrets and st.secrets.get("appyflow") and st.secrets["appyflow"].get("key_secret"):
                            key_present = True
                    except Exception:
                        key_present = os.getenv("APPYFLOW_KEY_SECRET") is not None
                    if not key_present:
                        st.warning("GST API key missing in secrets. Verification will fail. You can uncheck verification to just import given data.")
                st.info("Starting verification... This will run sequentially and show progress.")
                with st.spinner("Verifying..."):
                    results_df = bulk_verify_and_prepare(bulk_df, verify_with_api=verify_api, delay_between_calls=0.2, show_progress=True)
                st.session_state._bulk_results = results_df
                st.success("Verification completed. See results below.")

            results = st.session_state.get("_bulk_results")
            if results is not None:
                st.markdown("**Verification Results**")
                # Provide download
                csv_bytes = results.to_csv(index=False).encode('utf-8')
                st.download_button("Download results CSV", data=csv_bytes, file_name=f"bulk_results_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv", mime="text/csv")
                st.dataframe(results)

                # Buttons to add successful ones
                colA, colB, colC = st.columns(3)
                with colA:
                    if st.button("Add All OK to DB"):
                        added, failed = add_successful_results_to_db(results, only_status="OK")
                        msg = f"Added {added} clients."
                        if failed:
                            msg += f" {len(failed)} failed to add."
                        st.success(msg)
                        # refresh clients listing
                        safe_rerun()
                with colB:
                    # allow selection of rows to add manually via checkboxes
                    st.write("Add selected rows:")
                    sel_idx = st.multiselect("Select row indices to add (0-based)", options=list(results.index))
                    if st.button("Add selected rows"):
                        chosen = results.loc[sel_idx]
                        added_count = 0
                        failed_list = []
                        for _, r in chosen.iterrows():
                            ok, err = add_client(r.get('name') or "", r.get('gstin') or "", r.get('pan') or "", r.get('address') or "", "")
                            if ok:
                                added_count += 1
                            else:
                                failed_list.append({"gstin": r.get('gstin'), "error": err})
                        st.success(f"Added {added_count}. Failed {len(failed_list)}.")
                        safe_rerun()
                with colC:
                    if st.button("Clear Bulk Data"):
                        st.session_state._bulk_df = None
                        st.session_state._bulk_results = None
                        safe_rerun()

        # Edit / Delete existing clients
        st.subheader("Edit / Delete Client")
        clients_list = get_clients()
        clients_map = {f"{c[1]} ({c[2]})": c[0] for c in clients_list}
        sel = st.selectbox("Select client", options=["--select--"] + list(clients_map.keys()))
        if sel != "--select--":
            cid = clients_map[sel]
            rec = get_client_by_id(cid)
            if rec:
                cid, name, gstin, pan, address, email = rec
                with st.form("edit_client_form"):
                    name2 = st.text_input("Company Name", value=name)
                    gstin2 = st.text_input("GSTIN", value=gstin)
                    pan2 = st.text_input("PAN", value=pan or "")
                    address2 = st.text_area("Address", value=address)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("Update Client"):
                            if not name2:
                                st.error("Name required")
                            else:
                                update_client(cid, name2, gstin2, pan2, address2, email or "")
                                st.success("Updated")
                                safe_rerun()
                    with col2:
                        if st.button("Delete Client"):
                            delete_client(cid)
                            st.success("Deleted")
                            safe_rerun()

    # ----- Create Invoice -----
    elif mode == "Create Invoice":
        st.header("Create Invoice")
        clients = get_clients()
        client_map = {f"{c[1]} ({c[2]})": c[0] for c in clients}
        client_options = ["--select--"] + list(client_map.keys())
        selected = st.selectbox("Select Client", client_options)
        client_info = None
        if selected != "--select--":
            cid = client_map[selected]
            rec = get_client_by_id(cid)
            if rec:
                client_info = {"id": rec[0], "name": rec[1], "gstin": rec[2], "pan": rec[3], "address": rec[4]}

        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No", value=f"INV{int(datetime.now().timestamp())}")
            invoice_date = st.date_input("Invoice Date", value=date.today())
        with col2:
            payment_mode = st.selectbox("Payment Mode", ["Bank", "UPI", "Cash"])
            training_dates = st.text_input("Training/Exam Dates (optional)")

        st.subheader("Line Items")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1,"particulars":"DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":1,"rate":100,"taxable_amount":100}
            ]

        if st.button("Add New Row"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":0, "rate":0, "taxable_amount":0})
            safe_rerun()

        for idx in range(len(st.session_state.rows)):
            r = st.session_state.rows[idx]
            with st.expander(f"Row {r.get('slno', idx+1)}", expanded=False):
                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.0, 3.0, 4.0, 1.2, 1.0, 1.0, 1.0])
                new_sl = c1.number_input("S.No", value=int(r.get('slno', idx+1)), min_value=1, step=1, key=f"sl_{idx}")
                new_part = c2.text_input("Particulars", value=r.get('particulars',''), key=f"part_{idx}")
                new_desc = c3.text_input("Description", value=r.get('description',''), key=f"desc_{idx}")
                new_sac = c4.text_input("SAC", value=r.get('sac_code',''), key=f"sac_{idx}")
                new_qty = c5.number_input("Qty", value=int(r.get('qty',0)), min_value=0, key=f"qty_{idx}")
                new_rate = c6.number_input("Rate", value=float(r.get('rate',0.0)), min_value=0.0, key=f"rate_{idx}")
                new_taxable = round(new_qty * new_rate, 2)
                c7.write(f"Taxable: Rs. {new_taxable:,.2f}")
                st.session_state.rows[idx].update({
                    "slno": new_sl,
                    "particulars": new_part,
                    "description": new_desc,
                    "sac_code": new_sac,
                    "qty": new_qty,
                    "rate": new_rate,
                    "taxable_amount": new_taxable
                })
                bcol1, bcol2, bcol3, bcol4 = st.columns([1,1,1,1])
                with bcol1:
                    if st.button("Remove", key=f"remove_{idx}"):
                        st.session_state.rows.pop(idx)
                        safe_rerun()
                with bcol2:
                    if st.button("Duplicate", key=f"dup_{idx}"):
                        dup = st.session_state.rows[idx].copy()
                        st.session_state.rows.insert(idx+1, dup)
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with bcol3:
                    if st.button("Move Up", key=f"up_{idx}") and idx > 0:
                        st.session_state.rows[idx-1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx-1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with bcol4:
                    if st.button("Move Down", key=f"down_{idx}") and idx < len(st.session_state.rows)-1:
                        st.session_state.rows[idx+1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx+1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()

        if st.button("Add New Row (Bottom)"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":0, "rate":0, "taxable_amount":0})
            safe_rerun()

        force_igst = st.checkbox("Force IGST (18%) manually", value=False)
        advance_received = st.number_input("Advance Received (if any)", min_value=0.0, value=0.0)

        uploaded_file = st.file_uploader("Upload Supporting Excel (.xlsx/.csv)", type=["xlsx","csv"])
        supporting_df = None
        if uploaded_file:
            try:
                if uploaded_file.name.lower().endswith(".csv"):
                    supporting_df = pd.read_csv(uploaded_file)
                else:
                    supporting_df = pd.read_excel(uploaded_file)
                st.dataframe(supporting_df.head())
            except Exception as e:
                st.error(f"Error reading file: {e}")

        subtotal = sum([r['taxable_amount'] for r in st.session_state.rows])
        st.metric("Subtotal", f"Rs. {subtotal:,.2f}")

        if st.button("Generate PDF Invoice"):
            if not client_info:
                st.error("Select a client first.")
            else:
                meta = {
                    "invoice_no": invoice_no,
                    "invoice_date": invoice_date.strftime("%d-%m-%Y"),
                    "client": client_info,
                    "use_igst": force_igst,
                    "advance_received": float(advance_received)
                }
                try:
                    pdf_path = generate_invoice_pdf(meta, st.session_state.rows, supporting_df)
                    # Save invoice summary to DB
                    subtotal_dec = float(sum([r['taxable_amount'] for r in st.session_state.rows]))
                    comp_state = gst_state_code(COMPANY.get('gstin',''))
                    cli_state = gst_state_code(client_info.get('gstin',''))
                    auto_igst = False
                    if comp_state and cli_state and comp_state != cli_state:
                        auto_igst = True
                    use_igst_final = force_igst or auto_igst
                    if use_igst_final:
                        igst_val = subtotal_dec * 0.18
                        sgst_val = cgst_val = 0.0
                    else:
                        sgst_val = subtotal_dec * 0.09
                        cgst_val = subtotal_dec * 0.09
                        igst_val = 0.0
                    total_val = subtotal_dec + sgst_val + cgst_val + igst_val - float(advance_received)
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("INSERT INTO invoices (invoice_no, invoice_date, client_id, subtotal, sgst, cgst, igst, total, pdf_path) VALUES (?,?,?,?,?,?,?,?,?)",
                                (meta['invoice_no'], invoice_date.strftime("%Y-%m-%d"), client_info['id'], subtotal_dec, sgst_val, cgst_val, igst_val, total_val, pdf_path))
                    conn.commit()
                    conn.close()
                    st.success(f"PDF generated: {pdf_path}")
                    with open(pdf_path, "rb") as f:
                        st.download_button("Download PDF", f, file_name=os.path.basename(pdf_path), mime="application/pdf")
                except Exception:
                    st.error("Error generating PDF. See traceback below.")
                    st.text(traceback.format_exc())

    # ----- History -----
    else:
        st.header("Invoice History")
        conn = sqlite3.connect(DB_PATH)
        dfhist = pd.read_sql_query("SELECT id, invoice_no, invoice_date, subtotal, sgst, cgst, igst, total, pdf_path FROM invoices ORDER BY id DESC", conn)
        conn.close()
        if not dfhist.empty:
            st.dataframe(dfhist)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("App crashed. See traceback:")
        st.text(traceback.format_exc())
