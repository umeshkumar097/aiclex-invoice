# invoice_app.py
# Crux Invoice Management System (fixed layout + black-cell logic + company_text on same page)
# Built by Aiclex Technologies
#
# Requirements:
# pip install streamlit pandas reportlab num2words openpyxl requests

import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import os
import traceback
import requests
from num2words import num2words
from decimal import Decimal, ROUND_HALF_UP
import time

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, Flowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------- Constants ----------------
APP_TITLE = "Crux Invoice Management System"
APP_BUILT_BY = "Built by Aiclex Technologies"
DB_PATH = "invoices.db"
PDF_DIR = "generated_pdfs"
ASSETS_DIR = "assets"
os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

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
    "logo_top": os.path.join(ASSETS_DIR, "logo_top.jpg"),
    "tagline": os.path.join(ASSETS_DIR, "tagline.jpg"),
    "company_text": os.path.join(ASSETS_DIR, "company_text.jpg"),
    "signature": os.path.join(ASSETS_DIR, "signature_stamp.jpg"),
    "calibri_ttf": os.path.join(ASSETS_DIR, "Calibri.ttf")
}

# Register Calibri if provided
FONT_NAME = "Helvetica"
if os.path.exists(COMPANY["calibri_ttf"]):
    try:
        pdfmetrics.registerFont(TTFont("Calibri", COMPANY["calibri_ttf"]))
        FONT_NAME = "Calibri"
    except Exception:
        FONT_NAME = "Helvetica"

# Styles
base_styles = getSampleStyleSheet()
BODY_STYLE = ParagraphStyle("body", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11)
HEADER_STYLE = ParagraphStyle("header", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=11, leading=12, alignment=1)
TITLE_STYLE = ParagraphStyle("title", parent=base_styles["Heading1"], fontName=FONT_NAME, fontSize=16, leading=18, alignment=1)
RIGHT_STYLE = ParagraphStyle("right", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11, alignment=2)
DESC_STYLE = ParagraphStyle("desc", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11)
TOTAL_LABEL_STYLE = ParagraphStyle("tot_label", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=12)
TOTAL_VALUE_STYLE = ParagraphStyle("tot_val", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=12, alignment=2)
FOOTER_STYLE = ParagraphStyle("footer", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=7, leading=8, alignment=1)

# Helpers
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
        s = str(gstin).strip()
        if len(s) >= 2 and s[:2].isdigit():
            return s[:2]
    except:
        pass
    return ""

STATE_MAP = {
    "01":"JK","02":"HP","03":"PB","04":"CH","05":"HR","06":"DL","07":"RJ","08":"UP","09":"UK","10":"BR",
    "11":"SK","12":"AR","13":"NL","14":"MN","15":"MZ","16":"TR","17":"ML","18":"AS","19":"WB","20":"JH",
    "21":"OR","22":"CG","23":"MP","24":"GJ","25":"DNH","26":"DD","27":"MH","28":"AP","29":"KA","30":"GA",
    "31":"LD","32":"PY","33":"TN","34":"KL","35":"LA","36":"AN","37":"CHH","38":"UTT"
}

def state_label_from_gst(gstin):
    sc = gst_state_code(gstin)
    return STATE_MAP.get(sc, sc) if sc else ""

def safe_rerun():
    if hasattr(st, "experimental_rerun"):
        try:
            st.experimental_rerun()
        except Exception:
            pass

# DB init & migrate
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            gstin TEXT UNIQUE,
            pan TEXT,
            address TEXT,
            email TEXT,
            purchase_order TEXT,
            state_code TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT,
            invoice_date TEXT,
            client_id INTEGER,
            subtotal REAL,
            sgst REAL,
            cgst REAL,
            igst REAL,
            total REAL,
            pdf_path TEXT
        )
    """)
    conn.commit()
    conn.close()

def migrate_db_add_columns():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(clients)")
    cols = [r[1] for r in cur.fetchall()]
    if "purchase_order" not in cols:
        try:
            cur.execute("ALTER TABLE clients ADD COLUMN purchase_order TEXT")
        except:
            pass
    if "state_code" not in cols:
        try:
            cur.execute("ALTER TABLE clients ADD COLUMN state_code TEXT")
        except:
            pass
    conn.commit()
    conn.close()

# DB helpers
def get_clients():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id,name,gstin,pan,address,email,purchase_order,state_code FROM clients ORDER BY name").fetchall()
    conn.close()
    return rows

def get_client_by_id(cid):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id,name,gstin,pan,address,email,purchase_order,state_code FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return row

def add_client(name, gstin, pan, address, email="", purchase_order="", state_code=""):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT OR REPLACE INTO clients (name,gstin,pan,address,email,purchase_order,state_code) VALUES (?,?,?,?,?,?,?)",
                     (name,gstin,pan,address,email,purchase_order,state_code))
        conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_client(cid, name, gstin, pan, address, email="", purchase_order="", state_code=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET name=?,gstin=?,pan=?,address=?,email=?,purchase_order=?,state_code=? WHERE id=?",
                 (name,gstin,pan,address,email,purchase_order,state_code,cid))
    conn.commit()
    conn.close()

def delete_client(cid):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit()
    conn.close()

# GST API
def fetch_gst_from_appyflow(gstin, timeout=8):
    gstin = str(gstin).strip()
    if not gstin:
        return {"ok": False, "error": "Empty GSTIN"}
    key = None
    try:
        key = st.secrets["appyflow"]["key_secret"]
    except Exception:
        key = os.getenv("APPYFLOW_KEY_SECRET")
    if not key:
        return {"ok": False, "error": "API key missing in secrets or env var."}
    url = "https://appyflow.in/api/verifyGST"
    params = {"key_secret": key, "gstNo": gstin}
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        j = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Request failed: {e}"}
    if isinstance(j, dict) and ("taxpayerInfo" in j or j.get("error") is False or j.get("status") == "success"):
        info = j.get("taxpayerInfo") or j.get("taxpayerinfo") or j.get("taxpayer") or j
        name = info.get("tradeNam") or info.get("lgnm") or info.get("tradeName") or info.get("name") or ""
        addr = ""
        try:
            pradr = info.get("pradr",{}) or {}
            a = pradr.get("addr",{}) or {}
            parts = []
            for k in ("bno","st","loc","city","dst","pncd","stcd","bn","addr1","addr2","state"):
                v = a.get(k) or a.get(k.upper()) or a.get(k.lower())
                if v:
                    parts.append(str(v))
            addr = ", ".join(parts)
        except:
            addr = ""
        pan = None
        for pk in ("pan","panno","panNo","PAN"):
            if info.get(pk):
                pan = str(info.get(pk)).strip(); break
        if not pan and len(gstin) >= 12:
            pan = gstin[2:12].upper()
        state_code = gst_state_code(gstin)
        return {"ok": True, "name": name, "address": addr, "gstin": gstin, "pan": pan, "state_code": state_code, "raw": j}
    else:
        msg = j.get("message") if isinstance(j, dict) else str(j)
        return {"ok": False, "error": msg or "API returned error"}

# HR Flowable
class HR(Flowable):
    def __init__(self, width, thickness=1, color=colors.black):
        Flowable.__init__(self)
        self.width = width; self.thickness = thickness; self.color = color
    def draw(self):
        self.canv.setLineWidth(self.thickness)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0,0,self.width,0)

# ------------------ IMPORTANT: Updated generate_invoice_pdf ------------------
def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    """
    Key fixes:
    - Place logo, tagline, company_text on same invoice page (under INVOICE header)
    - Black-cell logic: only blank/None cells are black. '0' or '0.00' are NOT black.
    - Avoid whole-column-black bug by calculating row index dynamically.
    - Place stamp (signature image) at bottom-right on supporting page last page.
    """
    from decimal import Decimal, ROUND_HALF_UP
    def q(v):
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Normalize/prep rows: allow blank (None or "")
    prepared = []
    for idx, r in enumerate(line_items, start=1):
        partic = str(r.get('particulars') or "").strip()
        desc = str(r.get('description') or "")
        sac = str(r.get('sac_code') or "")
        qty_raw = r.get('qty')
        rate_raw = r.get('rate')
        # treat empty string or None as None (blank)
        qty_val = None
        rate_val = None
        try:
            if qty_raw is not None and str(qty_raw).strip() != "":
                qty_val = float(str(qty_raw).replace(",", "").strip())
        except:
            qty_val = None
        try:
            if rate_raw is not None and str(rate_raw).strip() != "":
                rate_val = float(str(rate_raw).replace(",", "").strip())
        except:
            rate_val = None
        taxable_num = q(qty_val * rate_val) if (qty_val is not None and rate_val is not None) else Decimal("0.00")
        prepared.append({
            "slno": r.get('slno') or idx,
            "particulars": partic,
            "description": desc,
            "sac_code": sac,
            "qty": qty_val,
            "rate": q(rate_val) if rate_val is not None else None,
            "taxable_amount": taxable_num
        })

    filename = f"Invoice_{invoice_meta.get('invoice_no','NA')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    story = []
    page_width = A4[0] - (12*mm + 12*mm)

    def add_image_if(path, w_mm=None, h_mm=None, align='CENTER', spacer_after=4):
        if path and os.path.exists(path):
            try:
                w = (w_mm*mm) if w_mm else None
                h = (h_mm*mm) if h_mm else None
                img = Image(path, width=w, height=h) if (w and h) else Image(path)
                img.hAlign = align
                story.append(img)
                if spacer_after:
                    story.append(Spacer(1, spacer_after))
            except Exception:
                pass

    # Header: INVOICE centered on its own row
    story.append(Paragraph("INVOICE", TITLE_STYLE))
    story.append(Spacer(1,6))

    # Under header: GST left, PAN right (single row)
    gst_html = f"<b>GST IN :</b> {COMPANY.get('gstin','')}"
    pan_html = f"<b>PAN NO :</b> {COMPANY.get('pan','')}"
    gst_pan_tbl = Table([[Paragraph(gst_html, BODY_STYLE), Paragraph(pan_html, RIGHT_STYLE)]], colWidths=[page_width*0.6, page_width*0.4])
    gst_pan_tbl.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(gst_pan_tbl)
    story.append(Spacer(1,6))

    # Now add logo, tagline, AND company_text all on same invoice page (logo centered, tagline under it, company_text under tagline)
    # You can adjust sizes if required.
    add_image_if(COMPANY.get('logo_top'), w_mm=87, h_mm=25.2, align='CENTER', spacer_after=6)
    add_image_if(COMPANY.get('tagline'), w_mm=164.8, h_mm=5.4, align='CENTER', spacer_after=6)
    # company_text image (previously footer) placed here on same page under tagline
    add_image_if(COMPANY.get('company_text'), w_mm=177, h_mm=27.2, align='CENTER', spacer_after=6)

    # Client & Invoice Details box (left / right)
    client = invoice_meta.get('client', {}) or {}
    left_lines = ["<b>Service Location</b>"]
    if client.get('name'): left_lines.append(f"To M/s: {client.get('name')}")
    if client.get('address'): left_lines.append(str(client.get('address')).replace("\n","<br/>"))
    left_lines.append("<br/>")
    if client.get('gstin'): left_lines.append(f"<b>GSTIN NO:</b> {client.get('gstin')}")
    po = client.get('purchase_order','')
    if po:
        left_lines.append(f"<b>Purchase Order:</b> {po}")
    left_html = "<br/>".join(left_lines)

    inv_no = invoice_meta.get('invoice_no','')
    inv_date = invoice_meta.get('invoice_date','')
    right_lines = [
        f"<b>INVOICE NO. :</b> {inv_no}",
        f"<b>DATE :</b> {inv_date}",
        "<br/>",
        "<b>Vendor Electronic Remittance</b>",
        f"Bank Name : {COMPANY.get('bank_name','')}",
        f"A/C No : {COMPANY.get('bank_account','')}",
        f"IFS Code : {COMPANY.get('ifsc','')}",
        f"Swift Code : {COMPANY.get('swift','')}",
        f"MICR No : {COMPANY.get('micr','')}",
        f"Branch : {COMPANY.get('branch','')}"
    ]
    right_html = "<br/>".join(right_lines)

    big_box = Table([[Paragraph(left_html, BODY_STYLE), Paragraph(right_html, BODY_STYLE)]], colWidths=[page_width*0.55, page_width*0.45])
    big_box.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.6,colors.black),
        ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),
    ]))
    story.append(big_box)
    story.append(Spacer(1,8))

    # Items table
    headers = ["SL.NO","PARTICULARS","DESCRIPTION of SAC CODE","SAC CODE","QTY","RATE","TAXABLE AMOUNT"]
    col_w = [12*mm, 45*mm, (page_width - (12*mm + 45*mm + 22*mm + 14*mm + 22*mm + 26*mm)), 22*mm, 14*mm, 22*mm, 26*mm]
    total_w = sum(col_w)
    if total_w > page_width:
        scale = page_width / total_w
        col_w = [w*scale for w in col_w]

    table_data = [[Paragraph(h, HEADER_STYLE) for h in headers]]
    black_cells = []  # (col_idx, row_idx)
    # We'll append rows and compute current row index dynamically to avoid whole-column black bug
    for r in prepared:
        current_row_idx = len(table_data)  # header is 0, first data row will be index 1
        sl = str(r['slno'])
        part = r['particulars']
        desc = r['description']
        sac = r['sac_code']
        # Display: if None => blank; if numeric 0 -> show 0.00? user wants blank instead of zero — they said zero shouldn't be written, blank would be fine.
        # We'll display blank when None; if numeric 0.0 then display blank too (per user's preference).
        qty_display = "" if (r['qty'] is None or float(r['qty']) == 0.0) else (str(int(r['qty'])) if float(r['qty']).is_integer() else str(r['qty']))
        rate_display = "" if (r['rate'] is None or float(r['rate']) == 0.0) else f"{r['rate']:,.2f}"
        tax_display = "" if (r['qty'] is None or r['rate'] is None or (r['taxable_amount'] == Decimal("0.00"))) else f"{r['taxable_amount']:,.2f}"

        row = [
            Paragraph(sl, BODY_STYLE),
            Paragraph(part, BODY_STYLE),
            Paragraph(desc, DESC_STYLE),
            Paragraph(sac, BODY_STYLE),
            Paragraph(qty_display, RIGHT_STYLE),
            Paragraph(rate_display, RIGHT_STYLE),
            Paragraph(tax_display, RIGHT_STYLE)
        ]
        table_data.append(row)

        # BLACK CELL RULE: only when cell is truly blank (empty string) -> mark black
        # (Do NOT mark black for '0' or '0.00' strings — we treat those as blank as per user)
        cell_values = [qty_display, rate_display, tax_display]
        for offset, val in enumerate(cell_values, start=4):  # columns 4,5,6 are qty,rate,tax
            if val == "" or val is None:
                black_cells.append((offset, current_row_idx))

    # ensure at least one data row exists
    if len(table_data) == 1:
        table_data.append([Paragraph("-", BODY_STYLE)] + [Paragraph("-", BODY_STYLE)]*(len(headers)-1))

    items_tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('GRID',(0,0),(-1,-1),0.35,colors.black),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ALIGN',(0,0),(0,-1),'CENTER'),
        ('ALIGN',(-3,1),(-1,-1),'RIGHT'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6)
    ]
    # apply black only to the specific blank cells
    for (cidx, ridx) in black_cells:
        tbl_style.append(('BACKGROUND',(cidx,ridx),(cidx,ridx),colors.black))
        tbl_style.append(('TEXTCOLOR',(cidx,ridx),(cidx,ridx),colors.white))

    items_tbl.setStyle(TableStyle(tbl_style))
    story.append(items_tbl)
    story.append(Spacer(1,8))

    # Totals calculation
    subtotal = sum([r['taxable_amount'] for r in prepared]) if prepared else Decimal("0.00")
    adv = Decimal(str(invoice_meta.get('advance_received', 0) or 0)).quantize(Decimal("0.01"))
    comp_state = gst_state_code(COMPANY.get('gstin',''))
    cli_state = gst_state_code(client.get('gstin','')) if client.get('gstin') else ""
    use_igst = invoice_meta.get('use_igst', False)
    if comp_state and cli_state and comp_state != cli_state:
        use_igst = True

    if use_igst:
        igst = (subtotal * Decimal('0.18')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst = cgst = Decimal('0.00')
    else:
        sgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        igst = Decimal('0.00')

    total = subtotal + sgst + cgst + igst
    net = (total - adv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    totals_rows = []
    totals_rows.append([Paragraph("Sub Total", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {subtotal:,.2f}", TOTAL_VALUE_STYLE)])
    if use_igst:
        totals_rows.append([Paragraph("IGST (18%)", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {igst:,.2f}", TOTAL_VALUE_STYLE)])
    else:
        totals_rows.append([Paragraph("SGST (9%)", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {sgst:,.2f}", TOTAL_VALUE_STYLE)])
        totals_rows.append([Paragraph("CGST (9%)", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {cgst:,.2f}", TOTAL_VALUE_STYLE)])
    if adv > 0:
        totals_rows.append([Paragraph("Less Advance Received", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {adv:,.2f}", TOTAL_VALUE_STYLE)])
    totals_rows.append([Paragraph("<b>TOTAL</b>", ParagraphStyle("tot_bold_label", fontName=FONT_NAME, fontSize=11, leading=13)),
                        Paragraph(f"<b>Rs. {net:,.2f}</b>", ParagraphStyle("tot_bold_val", fontName=FONT_NAME, fontSize=11, leading=13, alignment=2))])

    tot_tbl = Table(totals_rows, colWidths=[page_width*0.65, page_width*0.35], hAlign='RIGHT')
    tot_tbl.setStyle(TableStyle([
        ('INNERGRID',(0,0),(-1,-2),0.25,colors.lightgrey),
        ('LINEABOVE',(0,-1),(-1,-1),0.8,colors.black),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
        ('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6)
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1,8))

    story.append(Paragraph(f"In Words : ( {rupees_in_words(net)} )", BODY_STYLE))
    story.append(Spacer(1,10))

    # Signature and authorised signatory
    if COMPANY.get('signature') and os.path.exists(COMPANY.get('signature')):
        try:
            sig = Image(COMPANY['signature'], width=44.6*mm, height=31.3*mm)
            sig.hAlign = 'LEFT'
            story.append(sig)
            story.append(Spacer(1,4))
        except Exception:
            pass
    story.append(Paragraph("For " + COMPANY.get('name',''), BODY_STYLE))
    story.append(Paragraph("Authorised Signatory", BODY_STYLE))
    story.append(Spacer(1,10))

    # (Do NOT append company_text again here — it's already displayed near header)
    # Supporting documents page(s)
    if supporting_df is not None and not supporting_df.empty:
        try:
            df = supporting_df.fillna("").astype(str)
            story.append(PageBreak())
            story.append(Paragraph("Supporting Documents / Excel data", TITLE_STYLE))
            story.append(Spacer(1,6))

            cols = list(df.columns)
            max_cols = 10
            for start in range(0, len(cols), max_cols):
                subset_cols = cols[start:start+max_cols]
                sub_df = df[subset_cols]
                header_row = [Paragraph(str(c), ParagraphStyle('sh', fontName=FONT_NAME, fontSize=9, leading=10, alignment=1)) for c in sub_df.columns]
                table_rows = [header_row]
                for _, row in sub_df.iterrows():
                    row_cells = []
                    for c in sub_df.columns:
                        txt = " ".join(str(row[c]).split())
                        row_cells.append(Paragraph(txt, ParagraphStyle('cell', fontName=FONT_NAME, fontSize=7, leading=8)))
                    table_rows.append(row_cells)
                colw = [page_width / len(subset_cols) for _ in subset_cols]
                sup_tbl = Table(table_rows, colWidths=colw, repeatRows=1)
                sup_tbl.setStyle(TableStyle([
                    ('GRID',(0,0),(-1,-1),0.25,colors.grey),
                    ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('LEFTPADDING',(0,0),(-1,-1),2),
                    ('RIGHTPADDING',(0,0),(-1,-1),2),
                ]))
                story.append(sup_tbl)
                story.append(Spacer(1,8))

            # stamp on last supporting page bottom-right if signature exists
            if COMPANY.get('signature') and os.path.exists(COMPANY.get('signature')):
                try:
                    stamp = Image(COMPANY['signature'], width=44.6*mm, height=31.3*mm)
                    stamp.hAlign = 'RIGHT'
                    story.append(Spacer(1,8))
                    story.append(stamp)
                except Exception:
                    pass

        except Exception as e:
            story.append(Paragraph("Error rendering supporting sheet: " + str(e), BODY_STYLE))

    doc.build(story)
    return path

# ---------------- Bulk helpers (unchanged logic) ----------------
def normalize_uploaded_df(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    lower = {c.lower(): c for c in df.columns}
    mapping = {}
    for expected in ("gstin","gst","gst_no","gst_no.","gst number"):
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
    if 'gstin' not in mapping:
        mapping['gstin'] = df.columns[0] if len(df.columns)>0 else None
    out = []
    for _, row in df.iterrows():
        gstin_val = row.get(mapping.get('gstin')) if mapping.get('gstin') else ''
        name_val = row.get(mapping.get('name')) if mapping.get('name') else ''
        address_val = row.get(mapping.get('address')) if mapping.get('address') else ''
        pan_val = row.get(mapping.get('pan')) if mapping.get('pan') else ''
        out.append({"gstin": str(gstin_val).strip(), "name": str(name_val).strip(), "address": str(address_val).strip(), "pan": str(pan_val).strip()})
    return pd.DataFrame(out)

def bulk_verify_and_prepare(df, verify_with_api=True, delay_between_calls=0.2, show_progress=True):
    results = []
    total = len(df)
    progress = None
    if show_progress and total>0:
        progress = st.progress(0)
    for i, row in df.iterrows():
        gstin = str(row.get('gstin','')).strip()
        given_name = row.get('name','') or ""
        given_addr = row.get('address','') or ""
        given_pan = row.get('pan','') or ""
        res_name, res_addr, res_pan, res_state = given_name, given_addr, given_pan, ""
        status = "Manual"; error = ""
        if not gstin:
            status = "Failed"; error = "Empty GSTIN"
        else:
            if verify_with_api:
                api_res = fetch_gst_from_appyflow(gstin)
                if api_res.get("ok"):
                    res_name = api_res.get("name") or given_name
                    res_addr = api_res.get("address") or given_addr
                    res_pan = api_res.get("pan") or given_pan
                    res_state = api_res.get("state_code") or gst_state_code(gstin)
                    status = "OK"
                else:
                    status = "Failed"; error = api_res.get("error","API failed")
            else:
                res_state = gst_state_code(gstin)
                status = "OK"
        results.append({"gstin": gstin, "name": res_name, "address": res_addr, "pan": res_pan, "state": res_state, "status": status, "error": error})
        if show_progress:
            progress.progress(int((i+1)/total*100))
        if verify_with_api:
            time.sleep(delay_between_calls)
    if show_progress:
        progress.empty()
    return pd.DataFrame(results)

def add_successful_results_to_db(results_df, only_status="OK"):
    added = 0; failed = []
    for _, r in results_df.iterrows():
        if r.get('status') == only_status:
            ok, err = add_client(r.get('name') or "", r.get('gstin') or "", r.get('pan') or "", r.get('address') or "", email="", purchase_order="", state_code=r.get('state') or "")
            if ok: added += 1
            else: failed.append({"gstin": r.get('gstin'), "error": err})
    return added, failed

# ---------------- Auth ----------------
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        val = st.sidebar.select_slider("Session", options=["Stay Logged In", "Logout"], value="Stay Logged In")
        if val == "Logout":
            st.session_state.authenticated = False
            safe_rerun()
        st.sidebar.markdown("**Logged in**")
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
            st.warning("No app password set in Streamlit secrets or environment variable.")
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

# ---------------- Streamlit UI (rest of app same as before) ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(APP_BUILT_BY)
    init_db()
    migrate_db_add_columns()

    if not check_password():
        return

    mode = st.sidebar.selectbox("Mode", ["Manage Clients", "Create Invoice", "History"])

    # Manage Clients
    if mode == "Manage Clients":
        st.header("Manage Clients")
        clients = get_clients()
        if clients:
            dfc = pd.DataFrame(clients, columns=['id','name','gstin','pan','address','email','purchase_order','state_code'])
            st.dataframe(dfc[['name','gstin','state_code','purchase_order']])

        st.subheader("Add New Client")
        with st.form("add_client_form"):
            gstin_input = st.text_input("GSTIN", value="", max_chars=15)
            name = st.text_input("Company Name")
            pan = st.text_input("PAN (optional)")
            address = st.text_area("Address")
            purchase_order = st.text_input("Purchase Order (optional)")
            submitted = st.form_submit_button("Save Client")
            if submitted:
                if not name:
                    st.error("Name required")
                else:
                    st_code = gst_state_code(gstin_input) or ""
                    ok, err = add_client(name, gstin_input, pan, address, email="", purchase_order=purchase_order, state_code=st_code)
                    if ok:
                        st.success("Client saved")
                        safe_rerun()
                    else:
                        st.error(f"Save error: {err}")

        # Fetch GST
        st.subheader("Fetch GST (API)")
        gst_fetch = st.text_input("GSTIN to fetch (for autofill)", value="", key="gst_fetch_input")
        if st.button("Fetch GST Details"):
            if not gst_fetch.strip():
                st.error("Enter GSTIN")
            else:
                with st.spinner("Fetching..."):
                    res = fetch_gst_from_appyflow(gst_fetch)
                st.session_state._last_gst_fetch = res
        last = st.session_state.get("_last_gst_fetch")
        if last:
            if last.get("ok"):
                st.success("Fetched — verify and Save")
                name_f = st.text_input("Company Name (fetched)", value=last.get("name",""), key="fetched_name")
                addr_f = st.text_area("Address (fetched)", value=last.get("address",""), key="fetched_addr")
                gstin_f = st.text_input("GSTIN (fetched)", value=last.get("gstin",""), key="fetched_gstin")
                pan_f = st.text_input("PAN (fetched)", value=last.get("pan",""), key="fetched_pan")
                po_f = st.text_input("Purchase Order (optional)", value="", key="fetched_po")
                if st.button("Save Fetched Client"):
                    if not name_f:
                        st.error("Name required")
                    else:
                        st_code = last.get("state_code") or gst_state_code(gstin_f)
                        ok, err = add_client(name_f, gstin_f, pan_f, addr_f, email="", purchase_order=po_f, state_code=st_code)
                        if ok:
                            st.success("Saved")
                            st.session_state._last_gst_fetch = None
                            safe_rerun()
                        else:
                            st.error(f"Save error: {err}")
            else:
                st.error(f"Fetch error: {last.get('error')}")
                st.session_state._last_gst_fetch = None

        # Bulk upload
        st.subheader("Bulk Upload Clients (CSV/XLSX)")
        uploaded = st.file_uploader("Upload file", type=["csv","xlsx"])
        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    df_raw = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
                else:
                    df_raw = pd.read_excel(uploaded, dtype=str)
                st.success(f"Loaded {uploaded.name} rows:{len(df_raw)}")
                st.dataframe(df_raw.head())
                st.session_state._bulk_df = normalize_uploaded_df(df_raw)
            except Exception as e:
                st.error(f"Error reading file: {e}")
                st.session_state._bulk_df = None

        bulk_df = st.session_state.get("_bulk_df")
        if bulk_df is not None:
            st.markdown("**Preview normalized**")
            st.dataframe(bulk_df.head(20))
            col1, col2 = st.columns(2)
            with col1:
                verify_api = st.checkbox("Verify GST via API (appyflow)", value=True)
            with col2:
                auto_add = st.checkbox("Auto-add verified to DB", value=False)
            if st.button("Process & Verify"):
                with st.spinner("Verifying..."):
                    results = bulk_verify_and_prepare(bulk_df, verify_with_api=verify_api, delay_between_calls=0.2, show_progress=True)
                st.session_state._bulk_results = results
                st.success("Done")
        results = st.session_state.get("_bulk_results")
        if results is not None:
            st.dataframe(results)
            if st.button("Add OK to DB"):
                added, failed = add_successful_results_to_db(results, only_status="OK")
                st.success(f"Added {added}; failed {len(failed)}")
                safe_rerun()
            if st.button("Clear Bulk"):
                st.session_state._bulk_df = None; st.session_state._bulk_results = None
                safe_rerun()

        st.subheader("Edit / Delete Client")
        clients_list = get_clients()
        def client_label(c):
            cid, name, gstin, pan, addr, email, po, stc = c
            stlbl = f"-{state_label_from_gst(gstin)}" if gstin else ""
            po_part = f" | PO:{po}" if po else ""
            return f"{name} | {gstin} {stlbl}{po_part}"
        clients_map = {client_label(c): c[0] for c in clients_list}
        sel = st.selectbox("Select client", options=["--select--"] + list(clients_map.keys()))
        if sel != "--select--":
            cid = clients_map[sel]
            rec = get_client_by_id(cid)
            if rec:
                cid, name, gstin, pan, address, email, po, stc = rec
                with st.form("edit_client_form"):
                    name2 = st.text_input("Company Name", value=name)
                    gstin2 = st.text_input("GSTIN", value=gstin)
                    pan2 = st.text_input("PAN", value=pan or "")
                    address2 = st.text_area("Address", value=address)
                    po2 = st.text_input("Purchase Order (optional)", value=po or "")
                    st_code_disp = st.text_input("State Code (auto)", value=stc or "", disabled=True)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("Update Client"):
                            if not name2:
                                st.error("Name required")
                            else:
                                st_code = gst_state_code(gstin2) or stc or ""
                                update_client(cid, name2, gstin2, pan2, address2, email or "", purchase_order=po2 or "", state_code=st_code)
                                st.success("Updated")
                                safe_rerun()
                    with col2:
                        if st.button("Delete Client"):
                            delete_client(cid)
                            st.success("Deleted")
                            safe_rerun()

    # Create Invoice
    elif mode == "Create Invoice":
        st.header("Create Invoice")
        clients = get_clients()
        client_options = []
        for c in clients:
            cid, name, gstin, pan, addr, email, po, stc = c
            stlbl = f"-{state_label_from_gst(gstin)}" if gstin else ""
            client_options.append((f"{name} | {gstin} {stlbl}", cid))
        client_select = ["--select--"] + [lbl for lbl,_ in client_options]
        selected = st.selectbox("Select Client", options=client_select)
        client_info = None
        if selected != "--select--":
            cid = None
            for lbl, idv in client_options:
                if lbl == selected:
                    cid = idv; break
            if cid:
                rec = get_client_by_id(cid)
                if rec:
                    cid, name, gstin, pan, address, email, purchase_order, state_code = rec
                    client_info = {"id": cid, "name": name, "gstin": gstin, "pan": pan, "address": address, "purchase_order": purchase_order, "state_code": state_code}

        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No", value=f"INV{int(datetime.now().timestamp())}")
            invoice_date = st.date_input("Invoice Date", value=date.today())
        with col2:
            payment_mode = st.selectbox("Payment Mode", ["Bank","UPI","Cash"])
            training_dates = st.text_input("Training/Exam Dates (optional)")

        st.subheader("Line Items (default items pre-populated)")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1, "particulars":"DEGREE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":2, "particulars":"UNDER GRADUATE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":3, "particulars":"NO OF CANDIDATES", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":4, "particulars":"EXAM FEE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":5, "particulars":"HAND BOOKS", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":6, "particulars":"Advance Received", "description":"", "sac_code":"", "qty":"", "rate":""}
            ]

        if st.button("Add New Blank Row"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":"", "rate":""})
            safe_rerun()

        for idx in range(len(st.session_state.rows)):
            r = st.session_state.rows[idx]
            with st.expander(f"Row {r.get('slno', idx+1)}", expanded=False):
                c1,c2,c3,c4,c5,c6,c7 = st.columns([1.0,3.0,4.0,1.2,1.0,1.0,1.0])
                new_sl = c1.number_input("S.No", value=int(r.get('slno', idx+1)), min_value=1, step=1, key=f"sl_{idx}")
                new_part = c2.text_input("Particulars", value=r.get('particulars',''), key=f"part_{idx}")
                new_desc = c3.text_input("Description", value=r.get('description',''), key=f"desc_{idx}")
                new_sac = c4.text_input("SAC", value=r.get('sac_code',''), key=f"sac_{idx}")
                new_qty = c5.text_input("Qty (leave blank if NA)", value=str(r.get('qty','')), key=f"qty_{idx}")
                new_rate = c6.text_input("Rate (leave blank if NA)", value=str(r.get('rate','')), key=f"rate_{idx}")
                try:
                    qv = float(new_qty.replace(",","")) if (new_qty and str(new_qty).strip()!="") else None
                except:
                    qv = None
                try:
                    rv = float(new_rate.replace(",","")) if (new_rate and str(new_rate).strip()!="") else None
                except:
                    rv = None
                taxable_val = (qv * rv) if (qv is not None and rv is not None) else 0.0
                c7.write(f"Taxable: Rs. {taxable_val:,.2f}" if (qv is not None and rv is not None) else "Taxable: -")
                st.session_state.rows[idx].update({
                    "slno": new_sl,
                    "particulars": new_part,
                    "description": new_desc,
                    "sac_code": new_sac,
                    "qty": new_qty,
                    "rate": new_rate
                })
                b1,b2,b3,b4 = st.columns([1,1,1,1])
                with b1:
                    if st.button("Remove", key=f"remove_{idx}"):
                        st.session_state.rows.pop(idx); safe_rerun()
                with b2:
                    if st.button("Duplicate", key=f"dup_{idx}"):
                        dup = st.session_state.rows[idx].copy()
                        st.session_state.rows.insert(idx+1, dup)
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with b3:
                    if st.button("Move Up", key=f"up_{idx}") and idx>0:
                        st.session_state.rows[idx-1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx-1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with b4:
                    if st.button("Move Down", key=f"down_{idx}") and idx < len(st.session_state.rows)-1:
                        st.session_state.rows[idx+1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx+1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()

        if st.button("Add New Row (Bottom)"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":"", "rate":""})
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

        subtotal_calc = 0.0
        for r in st.session_state.rows:
            try:
                qv = float(str(r.get('qty','')).replace(",","")) if (r.get('qty') and str(r.get('qty')).strip()!="") else None
            except:
                qv = None
            try:
                rv = float(str(r.get('rate','')).replace(",","")) if (r.get('rate') and str(r.get('rate')).strip()!="") else None
            except:
                rv = None
            if qv is not None and rv is not None:
                subtotal_calc += (qv * rv)
        st.metric("Subtotal", f"Rs. {subtotal_calc:,.2f}")

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
                    subtotal_dec = subtotal_calc
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
                    st.error("Error generating PDF. See traceback:")
                    st.text(traceback.format_exc())

    # History
    else:
        st.header("Invoice History")
        conn = sqlite3.connect(DB_PATH)
        col1, col2, col3 = st.columns([1,1,1])
        with col1:
            start_date = st.date_input("From", value=date.today() - timedelta(days=30))
        with col2:
            end_date = st.date_input("To", value=date.today())
        with col3:
            refresh = st.button("Refresh")
        q = """
            SELECT inv.id, inv.invoice_no, inv.invoice_date, c.name AS client_name, c.gstin AS client_gstin, c.purchase_order,
                   inv.subtotal, inv.sgst, inv.cgst, inv.igst, inv.total, inv.pdf_path
            FROM invoices inv
            LEFT JOIN clients c ON inv.client_id = c.id
            WHERE invoice_date BETWEEN ? AND ?
            ORDER BY inv.id DESC
        """
        dfhist = pd.read_sql_query(q, conn, params=(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        conn.close()
        if dfhist.empty:
            st.info("No invoices in selected date range.")
        else:
            st.dataframe(dfhist)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("App crashed. See traceback:")
        st.text(traceback.format_exc())
