# invoice_app.py
# Crux Invoice Management System
# Built by Aiclex Technologies
#
# Notes:
# - Put images in assets/ as .jpg:
#     assets/logo_top.jpg
#     assets/company_text.jpg   # optional (not used in layout below but kept)
#     assets/tagline.jpg
#     assets/signature_stamp.jpg
# - Appyflow GST API key should be stored in .streamlit/secrets.toml:
#     [appyflow]
#     key_secret = "YOUR_APPYFLOW_KEY_SECRET"
# - This app DOES NOT collect client email when adding a client (per user's request).

import streamlit as st
import sqlite3
from datetime import date, datetime
import pandas as pd
import os
import traceback
import requests
from num2words import num2words
from decimal import Decimal, ROUND_HALF_UP

# ReportLab imports
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

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, gstin TEXT, pan TEXT, address TEXT, email TEXT
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
    conn.execute("INSERT INTO clients (name,gstin,pan,address,email) VALUES (?,?,?,?,?)", (name,gstin,pan,address,email))
    conn.commit()
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
def fetch_gst_from_appyflow(gstin, timeout=8):
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

    # Parse API response (best-effort)
    if isinstance(j, dict) and ("taxpayerInfo" in j or j.get("error") is False):
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

# ---------------- PDF generation (improved table + supporting sheet wrapping) ----------------
def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    """
    Generates PDF with layout:
    - Top: logo then tagline
    - Centered "INVOICE"
    - GST IN (left) and PAN NO (right)
    - Big boxed area with Service Location (left) and Invoice + Vendor Bank (right)
    - Items table (fixed widths, wrapped text, right-aligned numbers)
    - Totals, amount in words, signature, footer
    - Supporting Excel data as last page with wrapped cells & adaptive font size
    """
    from decimal import Decimal, ROUND_HALF_UP
    from reportlab.lib.styles import ParagraphStyle

    def q(v):
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    filename = f"Invoice_{invoice_meta.get('invoice_no','NA')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    story = []
    page_width = A4[0] - (15*mm + 15*mm)

    # helper styles
    cell_style = ParagraphStyle("cell", fontSize=9, leading=11)
    header_style = ParagraphStyle("hdr", fontSize=9, leading=11, alignment=1)
    desc_style = ParagraphStyle("desc", fontSize=9, leading=12)
    right_style = ParagraphStyle("right", fontSize=9, leading=11, alignment=2)

    def safe_img(path, w, h, align='CENTER'):
        if path and os.path.exists(path):
            img = Image(path, width=w, height=h)
            img.hAlign = align
            story.append(img)

    # Top assets
    safe_img(COMPANY.get('logo_top'), 87*mm, 25.2*mm, align='CENTER')
    story.append(Spacer(1,4))
    safe_img(COMPANY.get('tagline'), 164.8*mm, 5.4*mm, align='CENTER')
    story.append(Spacer(1,8))

    # Title
    story.append(Paragraph("INVOICE", styles['title_center']))
    story.append(Spacer(1,6))

    # GST / PAN row
    gst_text = f"<b>GST IN :</b> {COMPANY.get('gstin','')}"
    pan_text = f"<b>PAN NO :</b> {COMPANY.get('pan','')}"
    gst_pan = Table([[Paragraph(gst_text, cell_style), Paragraph(pan_text, right_style)]], colWidths=[page_width*0.6, page_width*0.4])
    gst_pan.setStyle(TableStyle([('ALIGN',(1,0),(1,0),'RIGHT'), ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(gst_pan)
    story.append(Spacer(1,8))

    # Big boxed area
    client = invoice_meta.get('client', {}) or {}
    left_lines = ["<b>Service Location</b>", "<br/>"]
    if client.get('name'):
        left_lines.append(f"To M/s: {client.get('name')}")
    if client.get('address'):
        left_lines.append(client.get('address'))
    left_lines += ["<br/>", f"<b>GSTIN NO:</b> {client.get('gstin','')}", "<br/>", "<b>PURCHASE ORDER</b>"]
    left_html = "<br/>".join(left_lines)

    inv_no = invoice_meta.get('invoice_no','')
    inv_date = invoice_meta.get('invoice_date','')
    right_top = f"<b>INVOICE NO. :</b> {inv_no} <br/><b>DATE :</b> {inv_date}"
    vendor_lines = [
        "<b>Vendor Electronic Remittance</b>",
        f"Bank Name : {COMPANY.get('bank_name')}",
        f"A/C No : {COMPANY.get('bank_account')}",
        f"IFS Code : {COMPANY.get('ifsc')}",
        f"Swift Code : {COMPANY.get('swift','-')}",
        f"MICR No : {COMPANY.get('micr','-')}",
        f"Branch : {COMPANY.get('branch')}"
    ]
    right_html = right_top + "<br/><br/>" + "<br/>".join(vendor_lines)

    boxes = Table([[Paragraph(left_html, cell_style), Paragraph(right_html, cell_style)]], colWidths=[page_width*0.55, page_width*0.45])
    boxes.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.5,colors.grey),
        ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
    ]))
    story.append(boxes)
    story.append(Spacer(1,10))

    # Items table
    # Column widths tuned to expected layout; adjust if needed
    col_widths = [
        12*mm,   # SL.NO
        46*mm,   # PARTICULARS
        70*mm,   # DESCRIPTION (reasonable default)
        22*mm,   # SAC CODE
        14*mm,   # QTY
        22*mm,   # RATE
        26*mm    # TAXABLE AMOUNT
    ]

    # If sum exceeds page width, scale down
    total_w = sum(col_widths)
    if total_w > page_width:
        scale = page_width / total_w
        col_widths = [w * scale for w in col_widths]

    headers = ["SL.NO","PARTICULARS","DESCRIPTION of SAC CODE","SAC CODE","QTY","RATE","TAXABLE AMOUNT"]
    table_data = [[Paragraph(h, header_style) for h in headers]]

    for r in line_items:
        qty = Decimal(str(r.get('qty',0) or 0))
        rate = Decimal(str(r.get('rate',0) or 0))
        amt = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        row = [
            Paragraph(str(r.get('slno','')), cell_style),
            Paragraph(str(r.get('particulars','')), cell_style),
            Paragraph(str(r.get('description','')), desc_style),
            Paragraph(str(r.get('sac_code','')), cell_style),
            Paragraph(str(qty), right_style),
            Paragraph(f"{rate:,.2f}", right_style),
            Paragraph(f"{amt:,.2f}", right_style)
        ]
        table_data.append(row)

    items_table = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    items_table.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.black),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ALIGN',(0,0),(0,-1),'CENTER'),
        ('ALIGN',(-3,1),(-1,-1),'RIGHT'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),4),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    story.append(items_table)
    story.append(Spacer(1,8))

    # Totals
    subtotal = sum([Decimal(str(r.get('qty',0) or 0)) * Decimal(str(r.get('rate',0) or 0)) for r in line_items])
    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    adv = Decimal(str(invoice_meta.get('advance_received', 0) or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    comp_state = gst_state_code(COMPANY.get('gstin',''))
    cli_state = gst_state_code(client.get('gstin',''))
    use_igst = invoice_meta.get('use_igst', False)
    if comp_state and cli_state and comp_state != cli_state:
        use_igst = True

    if use_igst:
        igst = (subtotal * Decimal('0.18')).quantize(Decimal("0.01")); sgst = cgst = Decimal('0')
    else:
        sgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01")); cgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01")); igst = Decimal('0')

    total = (subtotal + sgst + cgst + igst).quantize(Decimal("0.01"))
    net = (total - adv).quantize(Decimal("0.01"))

    totals = [
        ["Sub Total", Paragraph(f"Rs. {subtotal:,.2f}", right_style)]
    ]
    if use_igst:
        totals.append(["IGST (18%)", Paragraph(f"Rs. {igst:,.2f}", right_style)])
    else:
        totals.append(["SGST (9%)", Paragraph(f"Rs. {sgst:,.2f}", right_style)])
        totals.append(["CGST (9%)", Paragraph(f"Rs. {cgst:,.2f}", right_style)])
    if adv > 0:
        totals.append(["Less Advance Received", Paragraph(f"Rs. {adv:,.2f}", right_style)])
    totals.append(["TOTAL", Paragraph(f"Rs. {net:,.2f}", right_style)])

    tot_tbl = Table(totals, colWidths=[page_width*0.65, page_width*0.35], hAlign='RIGHT')
    tot_tbl.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.grey),
        ('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('BACKGROUND',(0,-1),(-1,-1),colors.whitesmoke),
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1,8))

    # In words
    story.append(Paragraph(f"In Words : ( {rupees_in_words(net)} )", cell_style))
    story.append(Spacer(1,12))

    # Signature
    if COMPANY.get('signature') and os.path.exists(COMPANY.get('signature')):
        sig = Image(COMPANY['signature'], width=44.6*mm, height=31.3*mm)
        sig.hAlign = 'LEFT'
        story.append(KeepTogether([sig, Spacer(1,4), Paragraph("For Crux Management Services (P) Ltd<br/><br/>Authorised Signatory", styles['Normal'])]))
    else:
        story.append(Paragraph("For Crux Management Services (P) Ltd<br/><br/>Authorised Signatory", styles['Normal']))

    story.append(Spacer(1,10))
    story.append(HR(page_width, thickness=0.5, color=colors.grey))
    footer = COMPANY['address'] + " | Phone: " + COMPANY['phone'] + " | Email: " + COMPANY['email'] + " | " + APP_BUILT_BY
    story.append(Paragraph(footer, styles['footer']))

    # Supporting DataFrame: final page, wrapped cells, adaptive font-size
    if supporting_df is not None and not supporting_df.empty:
        try:
            story.append(PageBreak())
            story.append(Paragraph("Supporting Documents / Excel data", styles['Heading2']))
            df = supporting_df.fillna("").astype(str)
            n_cols = len(df.columns)
            if n_cols <= 5:
                font_size = 8
            elif n_cols <= 8:
                font_size = 7
            else:
                font_size = 6
            sup_style = ParagraphStyle(name="sup_style", fontSize=font_size, leading=max(font_size+1,7))
            min_col = 20*mm
            default_col = page_width / n_cols
            col_widths_sup = [max(default_col, min_col) for _ in df.columns]
            totalw = sum(col_widths_sup)
            if totalw > page_width:
                scale = page_width / totalw
                col_widths_sup = [w * scale for w in col_widths_sup]
            table_data = []
            header_row = [Paragraph(str(c), ParagraphStyle('hdr', fontSize=font_size, leading=font_size+1)) for c in df.columns]
            table_data.append(header_row)
            for _, row in df.iterrows():
                row_cells = []
                for col in df.columns:
                    cell_text = " ".join(str(row[col]).split())
                    row_cells.append(Paragraph(cell_text, sup_style))
                table_data.append(row_cells)
            sup_tbl = Table(table_data, colWidths=col_widths_sup, repeatRows=1)
            sup_tbl.setStyle(TableStyle([
                ('GRID',(0,0),(-1,-1),0.25,colors.grey),
                ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),4),
                ('RIGHTPADDING',(0,0),(-1,-1),4),
            ]))
            story.append(sup_tbl)
        except Exception as e:
            story.append(Paragraph("Error adding supporting sheet: " + str(e), styles['wrap']))

    doc.build(story)
    return path

# ---------------- Streamlit UI ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(APP_BUILT_BY)
    init_db()

    mode = st.sidebar.selectbox("Mode", ["Manage Clients", "Create Invoice", "History"])

    # Manage Clients
    if mode == "Manage Clients":
        st.header("Manage Clients")
        clients = get_clients()
        if clients:
            dfc = pd.DataFrame(clients, columns=['id','name','gstin','address','email'])
            st.dataframe(dfc[['name','gstin','address']])

        with st.expander("Add New Client"):
            gstin_input = st.text_input("GSTIN (enter first to auto-fetch)", value="", max_chars=15)
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Fetch details from GST API"):
                    if not gstin_input.strip():
                        st.error("Please enter GSTIN first.")
                    else:
                        with st.spinner("Fetching from GST API..."):
                            res = fetch_gst_from_appyflow(gstin_input)
                        if res.get("ok"):
                            st.success("Details fetched. Verify & save.")
                            name = st.text_input("Company Name", value=res.get("name", ""))
                            address = st.text_area("Address", value=res.get("address", ""))
                            gstin = st.text_input("GSTIN", value=res.get("gstin", gstin_input))
                            pan = st.text_input("PAN (auto)", value=res.get("pan", "") or "")
                            # We do NOT ask client email per request
                            if st.button("Save Client (Using fetched data)"):
                                if not name:
                                    st.error("Name required")
                                else:
                                    add_client(name, gstin, pan, address, email="")
                                    st.success("Client saved (no email collected).")
                        else:
                            st.warning(f"API failed: {res.get('error')}. Fill manually below.")
                            name = st.text_input("Company Name")
                            address = st.text_area("Address")
                            gstin = st.text_input("GSTIN", value=gstin_input)
                            pan = st.text_input("PAN (if any)")
                            if st.button("Save Client (Manual)"):
                                if not name:
                                    st.error("Name required")
                                else:
                                    add_client(name, gstin, pan, address, email="")
                                    st.success("Client saved (manual, no email).")
            with c2:
                st.info("Put Appyflow key in Streamlit secrets: [appyflow] key_secret = \"YOUR_KEY\"")

        with st.expander("Edit / Delete Client"):
            clients_list = get_clients()
            clients_map = {f"{c[1]} ({c[2]})": c[0] for c in clients_list}
            sel = st.selectbox("Select client", options=["--select--"] + list(clients_map.keys()))
            if sel != "--select--":
                cid = clients_map[sel]
                rec = get_client_by_id(cid)
                if rec:
                    cid, name, gstin, pan, address, email = rec
                    name2 = st.text_input("Company Name", value=name)
                    gstin2 = st.text_input("GSTIN", value=gstin)
                    pan2 = st.text_input("PAN", value=pan or "")
                    address2 = st.text_area("Address", value=address)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Update Client"):
                            update_client(cid, name2, gstin2, pan2, address2, email or "")
                            st.success("Updated")
                    with col2:
                        if st.button("Delete Client"):
                            delete_client(cid)
                            st.success("Deleted")

    # Create Invoice
    elif mode == "Create Invoice":
        st.header("Create Invoice")
        clients = get_clients()
        client_options = ["--select--"] + [f"{c[1]} ({c[2]})" for c in clients]
        selected = st.selectbox("Select Client", client_options)
        client_info = None
        if selected != "--select--":
            cid = [c[0] for c in clients if f"{c[1]} ({c[2]})" == selected][0]
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
            st.rerun()

        for idx in range(len(st.session_state.rows)):
            r = st.session_state.rows[idx]
            with st.expander(f"Row {r.get('slno', idx+1)} — {r.get('particulars','') or 'New Item'}", expanded=False):
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
                        st.rerun()
                with bcol2:
                    if st.button("Duplicate", key=f"dup_{idx}"):
                        dup = st.session_state.rows[idx].copy()
                        st.session_state.rows.insert(idx+1, dup)
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        st.rerun()
                with bcol3:
                    if st.button("Move Up", key=f"up_{idx}") and idx > 0:
                        st.session_state.rows[idx-1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx-1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        st.rerun()
                with bcol4:
                    if st.button("Move Down", key=f"down_{idx}") and idx < len(st.session_state.rows)-1:
                        st.session_state.rows[idx+1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx+1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        st.rerun()

        if st.button("Add New Row (Bottom)"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":0, "rate":0, "taxable_amount":0})
            st.rerun()

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

    # History
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
