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
    except Exception:
        FONT_NAME = "Helvetica"

# Styles - Reduced font sizes and leading for compact layout
base_styles = getSampleStyleSheet()
BODY_STYLE = ParagraphStyle("body", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=9.5)  # Reduced from 9/11
HEADER_STYLE = ParagraphStyle("header", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=11, alignment=1)  # Reduced from 11/12
TITLE_STYLE = ParagraphStyle("title", parent=base_styles["Heading1"], fontName=FONT_NAME, fontSize=14, leading=16, alignment=1)  # Reduced from 16/18
RIGHT_STYLE = ParagraphStyle("right", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=9.5, alignment=2)  # Reduced from 9/11
DESC_STYLE = ParagraphStyle("desc", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=9.5)  # Reduced from 9/11
TOTAL_LABEL_STYLE = ParagraphStyle("tot_label", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=10.5)  # Reduced from 10/12
TOTAL_VALUE_STYLE = ParagraphStyle("tot_val", parent=base_styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=10.5, alignment=2)  # Reduced from 10/12
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


def render_invoice_preview(meta, rows, subtotal, force_igst=False, advance_received=0.0):
    """Render a professional bordered invoice preview in the Streamlit UI using HTML/CSS with light-grey borders."""
    inv_no = meta.get('invoice_no', '')
    inv_date = meta.get('invoice_date', '')
    client = meta.get('client') or {}
    client_name = client.get('name','') if isinstance(client, dict) else ''
    client_gstin = client.get('gstin','') if isinstance(client, dict) else ''
    
    # Get Training/Exam Dates and Process Name from meta
    train_val = meta.get('training_dates') or meta.get('training_exam_dates') or meta.get('training') or ""
    process_val = meta.get('process_name') or ""
    
    # Calculate taxes on the original subtotal
    if force_igst:
        igst_val = subtotal * 0.18
        sgst_val = 0.0
        cgst_val = 0.0
    else:
        sgst_val = subtotal * 0.09
        cgst_val = subtotal * 0.09
        igst_val = 0.0
    
    # Calculate total after taxes
    total_val = subtotal + sgst_val + cgst_val + igst_val
    
    # Subtract advance from final total
    advance_amount = float(advance_received) if advance_received else 0.0
    payable_to_crux = total_val - advance_amount

    # Main container wrapping all invoice content - single parent div with zero top margin/padding
    # Using inline CSS and style tag to override any Streamlit default margins
    style_reset = "<style>div[data-testid='stMarkdownContainer'] { margin-top: 0 !important; padding-top: 0 !important; }</style>"
    main_container_start = "<div style='width:100%;margin:0 !important;margin-top:0 !important;padding:0 !important;padding-top:0 !important;box-sizing:border-box;display:block'>"
    
    # Start with outer container with light-grey borders (no top margin)
    invoice_container = "<div style='border:1px solid #ccc;margin-top:0;margin-bottom:6px'>"
    
    # Header block: INVOICE title
    invoice_title = "<div style='border-bottom:1px solid #ccc;padding:8px;text-align:center;font-weight:700;font-size:18px'>INVOICE</div>"
    
    # GST/PAN/Phone row
    gst_row = (
        "<div style='border-bottom:1px solid #ccc;display:flex;font-size:12px'>"
        f"<div style='flex:2;padding:8px;border-right:1px solid #ccc'><b>GST IN : </b>{COMPANY.get('gstin','')}</div>"
        f"<div style='flex:2;padding:8px;border-right:1px solid #ccc'><b>PAN NO : </b>{COMPANY.get('pan','')}</div>"
        f"<div style='flex:1;padding:8px'><b>Phone No. </b>{COMPANY.get('phone','')}</div>"
        "</div>"
    )
    
    # Service Location and Invoice Details with proper borders
    details_section = (
        "<div style='display:flex'>"
        "<div style='flex:1;border-right:1px solid #ccc'>"
        "<div style='border-bottom:1px solid #ccc;padding:8px;font-weight:bold'>Service Location</div>"
        f"<div style='padding:8px'>"
        f"To M/s: {client_name}<br/>"
        f"{client.get('address', '').replace(chr(10), '<br/>')}</div>"
        f"<div style='border-top:1px solid #ccc;border-bottom:1px solid #ccc;padding:8px'>"
        f"GSTIN NO: {client_gstin}</div>"
        "<div style='border-bottom:1px solid #ccc;padding:8px'>Purchase Order</div>"
        "</div>"
        "<div style='flex:1'>"
        "<div style='border-bottom:1px solid #ccc;padding:8px'>"
        f"<div><b>INVOICE NO. : </b>{inv_no}</div>"
        "</div>"
        "<div style='border-bottom:1px solid #ccc;padding:8px'>"
        f"<div><b>DATE : </b>{inv_date}</div>"
        "</div>"
        "<div style='padding:8px'>"
        "<div style='font-weight:bold;text-align:center;margin-bottom:12px;font-family:Arial,sans-serif;font-size:15px'>Vendor Electronic Remittance</div>"
        "<table style='width:100%;border-collapse:collapse;border:1px solid #d3d3d3;background-color:#ffffff;font-family:Arial,sans-serif;font-size:14px'>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;width:35%;background-color:#ffffff;font-weight:600'>Bank Name</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;width:65%;background-color:#ffffff'>{COMPANY.get('bank_name', '')}</td></tr>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff;font-weight:600'>A/C No</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff'>{COMPANY.get('bank_account', '')}</td></tr>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff;font-weight:600'>IFS Code</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff'>{COMPANY.get('ifsc', '')}</td></tr>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff;font-weight:600'>Swift Code</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff'>{COMPANY.get('swift', '')}</td></tr>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff;font-weight:600'>MICR No</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff'>{COMPANY.get('micr', '')}</td></tr>"
        f"<tr><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff;font-weight:600'>Branch</td><td style='border:1px solid #d3d3d3;padding:10px;text-align:left;background-color:#ffffff'>{COMPANY.get('branch', '')}</td></tr>"
        "</table>"
        "</div>"
        "</div>"
        "</div>"
    )
    
    # Combine all sections
    invoice_html = invoice_container + invoice_title + gst_row + details_section + "</div>"

    # Add logo if it exists (removed top margin)
    logo_html = ""
    if os.path.exists(COMPANY.get('logo_top','')):
        logo_path = COMPANY.get('logo_top')
        logo_html = f"<div style='text-align:center;margin-top:0;margin-bottom:6px'><img src='file://{logo_path}' style='max-width:220px;max-height:60px'/></div>"

    # Line items table with light-grey borders
    table_html = [
        '<table style="width:100%;border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;border:1px solid #ccc;margin-top:6px">',
        '<thead>',
        '<tr>',
        '<th style="border:1px solid #ccc;padding:8px;width:5%;text-align:center">S.NO</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:20%">PARTICULARS</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:35%">DESCRIPTION of SAC CODE</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:10%;text-align:center">SAC CODE</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:10%;text-align:center">QTY</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:10%;text-align:center">RATE</th>',
        '<th style="border:1px solid #ccc;padding:8px;width:10%;text-align:center">TAXABLE AMOUNT</th>',
        '</tr>',
        '</thead>',
        '<tbody>'
    ]

    for i, r in enumerate(rows, start=1):
        try:
            qty = float(str(r.get('qty','')).replace(',','')) if (r.get('qty') and str(r.get('qty')).strip()!='') else None
        except:
            qty = None
        try:
            rate = float(str(r.get('rate','')).replace(',','')) if (r.get('rate') and str(r.get('rate')).strip()!='') else None
        except:
            rate = None
        taxable = qty * rate if (qty is not None and rate is not None) else ''
        table_html.append('<tr>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:center">{r.get("slno", i)}</td>')
        part_val = r.get('particulars','')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px">{part_val}</td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px">{r.get("description","")}</td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:center">{r.get("sac_code","")}</td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{("{:,}".format(qty)) if qty is not None else ""}</td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{("{:,.2f}".format(rate)) if rate is not None else ""}</td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{("{:,.2f}".format(taxable)) if taxable != "" else ""}</td>')
        table_html.append('</tr>')

    # Add Training/Exam Dates row if present
    if train_val:
        table_html.append('<tr>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"><b>Training Dates/Exam Dates:</b></td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px">{train_val}</td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('</tr>')
    
    # Add Process Name row if present
    if process_val:
        table_html.append('<tr>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"><b>Process Name:</b></td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px">{process_val}</td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('</tr>')
    
    # Add Advance Received row if present (below last inserted row)
    if advance_received > 0:
        table_html.append('<tr>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"><b>Advance Received:</b></td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px">{float(advance_received):,.2f}</td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append('</tr>')

    # Subtotal row - spanning first 5 columns, value in last column, left-aligned label
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left;font-weight:700;background-color:#f5f5f5">Sub Total</td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;background-color:#f5f5f5"></td>')
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right;font-weight:700;background-color:#f5f5f5">{subtotal:,.2f}</td>')
    table_html.append('</tr>')
    
    # Tax rows - 3 column format: Label (col 1-5, left-aligned), Percentage (col 6, left-aligned), Value (col 7, right-aligned)
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left">SGST</td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;text-align:left">9%</td>')
    sgst_display = f"{sgst_val:,.2f}" if sgst_val > 0 else ""
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{sgst_display}</td>')
    table_html.append('</tr>')
    
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left">CGST</td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;text-align:left">9%</td>')
    cgst_display = f"{cgst_val:,.2f}" if cgst_val > 0 else ""
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{cgst_display}</td>')
    table_html.append('</tr>')
    
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left">IGST</td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;text-align:left">18%</td>')
    igst_display = f"{igst_val:,.2f}" if igst_val > 0 else ""
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{igst_display}</td>')
    table_html.append('</tr>')
    
    # Total row - 3 column format with bold, left-aligned label
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left;font-weight:700;background-color:#f5f5f5"><b>TOTAL</b></td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;background-color:#f5f5f5"></td>')
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right;font-weight:700;background-color:#f5f5f5"><b>{total_val:,.2f}</b></td>')
    table_html.append('</tr>')
    
    # Less Advance Received row - 3 column format, left-aligned label (only shown if > 0)
    if advance_received > 0:
        table_html.append('<tr>')
        table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left">Less Advance Received</td>')
        table_html.append('<td style="border:1px solid #ccc;padding:8px"></td>')
        table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right">{float(advance_received):,.2f}</td>')
        table_html.append('</tr>')
    
    # Payable To Crux row - 3 column format, bold with light grey background, left-aligned label
    table_html.append('<tr>')
    table_html.append('<td colspan="5" style="border:1px solid #ccc;padding:8px;text-align:left;font-weight:700;background-color:#f2f2f2"><b>Payable To Crux</b></td>')
    table_html.append('<td style="border:1px solid #ccc;padding:8px;background-color:#f2f2f2"></td>')
    table_html.append(f'<td style="border:1px solid #ccc;padding:8px;text-align:right;font-weight:700;background-color:#f2f2f2"><b>{payable_to_crux:,.2f}</b></td>')
    table_html.append('</tr>')
    
    # In Words row - as part of the same continuous table
    from num2words import num2words
    try:
        words = num2words(int(payable_to_crux), lang='en_IN', to='cardinal').title()
        words_text = f"<b>In Words:</b> ({words})"
    except:
        words_text = ""
    
    if words_text:
        table_html.append('<tr>')
        table_html.append(f'<td colspan="7" style="border:1px solid #ccc;padding:8px;text-align:left">{words_text}</td>')
        table_html.append('</tr>')
    
    table_html.append('</tbody></table>')
    
    # Close main container
    main_container_end = "</div>"
    
    # Combine all content within the main container div (style reset first to override Streamlit defaults)
    final_html = style_reset + main_container_start + logo_html + invoice_html + ''.join(table_html) + main_container_end
    
    # Render everything as a single unit with no top margin/padding
    st.markdown(final_html, unsafe_allow_html=True)

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

# Signature and company text handler for onPage callback
def add_signature_and_company_text(canv, doc, signature_path, signature_width, signature_height, company_text_path):
    """Callback function to add signature at bottom left and company_text at bottom of page 1"""
    page_num = canv.getPageNumber()
    if page_num == 1:
        # Add signature at bottom left
        if signature_path and os.path.exists(signature_path):
            try:
                # Position: 35mm from bottom to avoid overlap with content, 12mm from left (matching left margin)
                sig_y_position = 35*mm  # Increased to 35mm to move stamp higher and avoid overlap
                sig_x_position = 12*mm
                
                # Draw the signature image at fixed position on page 1
                canv.drawImage(signature_path, sig_x_position, sig_y_position, 
                              width=signature_width, height=signature_height, 
                              preserveAspectRatio=True, mask='auto')
            except Exception:
                pass  # Silently fail if signature image cannot be drawn
        
        # Add company_text at bottom center (above signature)
        if company_text_path and os.path.exists(company_text_path):
            try:
                # Get page dimensions
                page_width = A4[0]
                
                # Load image to get dimensions - use PIL/Pillow approach
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(company_text_path) as img:
                        img_width, img_height = img.size
                except:
                    # Fallback: try to open and measure using reportlab Image
                    from reportlab.lib.utils import ImageReader
                    img_reader = ImageReader(company_text_path)
                    img_width, img_height = img_reader.getSize()
                
                # Scale to fit page width with margin (leaving ~20mm on each side)
                max_width = page_width - 40*mm
                scale = min(1.0, max_width / img_width) if img_width > 0 else 1.0
                scaled_width = img_width * scale
                scaled_height = img_height * scale
                
                # Position: bottom center, below signature
                # Signature is at 25mm from bottom with height 31.3mm
                # Place company_text below signature (closer to bottom)
                comp_y_position = 10*mm  # Position below signature area, near bottom of page
                comp_x_position = (page_width - scaled_width) / 2  # Centered horizontally
                
                # Draw the company_text image at bottom center
                canv.drawImage(company_text_path, comp_x_position, comp_y_position, 
                              width=scaled_width, height=scaled_height, 
                              preserveAspectRatio=True, mask='auto')
            except Exception:
                pass  # Silently fail if company_text image cannot be drawn

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
    # Minimized top margin to 3mm for maximum space efficiency
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=3*mm, bottomMargin=12*mm)
    
    # Add signature and company_text to page 1 using onPage callback
    signature_path = COMPANY.get('signature', '')
    signature_width = 44.6*mm
    signature_height = 31.3*mm
    company_text_path = COMPANY.get('company_text', '')
    
    # Create a callback function that will be called on first page
    def on_first_page(canv, doc):
        add_signature_and_company_text(canv, doc, signature_path, signature_width, signature_height, company_text_path)
    doc.onFirstPage = on_first_page
    
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

    # Add company logo (centered) - no extra spacing before
    if os.path.exists(COMPANY.get('logo_top','')):
        logo = Image(COMPANY.get('logo_top'), width=220, height=60)
        logo.hAlign = 'CENTER'
        story.append(logo)
    
    # Add tagline image - minimal spacing after logo
    if os.path.exists(COMPANY.get('tagline','')):
        tagline = Image(COMPANY.get('tagline'), width=400, height=15)
        tagline.hAlign = 'CENTER'
        story.append(tagline)
        story.append(Spacer(1, 2))  # Very minimal spacing after tagline (reduced from 4 to 2)
    else:
        # If no tagline, add very minimal spacing after logo
        story.append(Spacer(1, 2))
    
    # Minimized space before invoice title (reduced from 4 to 2)
    story.append(Spacer(1, 2))
    
    # 1. INVOICE title with single border - reduced padding for tighter layout
    invoice_title = Table([[Paragraph("INVOICE", TITLE_STYLE)]], colWidths=[page_width])
    invoice_title.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 1.0, colors.black),
        ('LINEBELOW', (0,0), (-1,0), 1.0, colors.black),
        ('LINEBEFORE', (0,0), (0,-1), 1.0, colors.black),
        ('LINEAFTER', (-1,0), (-1,-1), 1.0, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
    ]))
    story.append(invoice_title)

    # 2. GST/PAN/Phone row with shared borders
    gst_data = [[
        Paragraph(f"GST IN : {COMPANY.get('gstin','').upper()}", BODY_STYLE),  # GST number in uppercase
        Paragraph(f"PAN NO : {COMPANY.get('pan','')}", BODY_STYLE),
        Paragraph(f"Phone No. {COMPANY.get('phone','')}", RIGHT_STYLE)
    ]]
    gst_table = Table(gst_data, colWidths=[page_width*0.4, page_width*0.35, page_width*0.25])
    gst_table.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 1.0, colors.black),
        ('LINEBELOW', (0,-1), (-1,-1), 1.0, colors.black),
        ('LINEBEFORE', (0,0), (0,-1), 1.0, colors.black),
        ('LINEAFTER', (-1,0), (-1,-1), 1.0, colors.black),
        ('LINEAFTER', (0,0), (0,-1), 1.0, colors.black),  # Vertical line after first column
        ('LINEAFTER', (1,0), (1,-1), 1.0, colors.black),  # Vertical line after second column
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('LEFTPADDING', (0,0), (-1,-1), 3),  # Aggressively reduced to 3
        ('RIGHTPADDING', (0,0), (-1,-1), 3),  # Aggressively reduced to 3
    ]))
    story.append(gst_table)

    # 3. Service Location and Invoice Details with shared borders
    client = invoice_meta.get('client', {}) or {}
    
    # Create Vendor Electronic Remittance table with light grey borders (nested table)
    light_grey = colors.HexColor('#D3D3D3')
    bank_details_data = [
        [Paragraph("<b>Bank Name</b>", BODY_STYLE), Paragraph(COMPANY.get('bank_name',''), BODY_STYLE)],
        [Paragraph("<b>A/C No</b>", BODY_STYLE), Paragraph(COMPANY.get('bank_account',''), BODY_STYLE)],
        [Paragraph("<b>IFS Code</b>", BODY_STYLE), Paragraph(COMPANY.get('ifsc',''), BODY_STYLE)],
        [Paragraph("<b>Swift Code</b>", BODY_STYLE), Paragraph(COMPANY.get('swift',''), BODY_STYLE)],
        [Paragraph("<b>MICR No</b>", BODY_STYLE), Paragraph(COMPANY.get('micr',''), BODY_STYLE)],
        [Paragraph("<b>Branch</b>", BODY_STYLE), Paragraph(COMPANY.get('branch',''), BODY_STYLE)],
    ]
    
    # Calculate width to fit within parent cell (accounting for parent padding)
    parent_cell_width = page_width * 0.5
    available_width = parent_cell_width - 12  # Subtract parent padding (6+6)
    bank_table = Table(bank_details_data, colWidths=[available_width*0.38, available_width*0.62])
    bank_table.setStyle(TableStyle([
        # Light grey borders with thinner width (0.5 instead of 1.0) and reduced padding
        ('BOX', (0,0), (-1,-1), 0.5, light_grey),
        ('INNERGRID', (0,0), (-1,-1), 0.5, light_grey),
        ('LINEAFTER', (0,0), (0,-1), 0.5, light_grey),  # Vertical line between label and value
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
    ]))
    
    # Combine all details into a single table structure
    details_data = [
        # Headers row
        [Paragraph("<b>Service Location</b>", HEADER_STYLE), 
         Paragraph(f"<b>INVOICE NO. : </b>{invoice_meta.get('invoice_no','')}", BODY_STYLE)],
        
        # Address and Date row
        [Paragraph(f"To M/s: {client.get('name','')}", BODY_STYLE),
         Paragraph(f"<b>DATE : </b>{invoice_meta.get('invoice_date','')}", BODY_STYLE)],
        
        # Client address and Vendor header row
        [Paragraph(client.get('address','').replace("\n", "<br/>"), BODY_STYLE),
         Paragraph("<b>Vendor Electronic Remittance</b>", ParagraphStyle("vend_header", fontName=FONT_NAME, fontSize=11, leading=13, alignment=1))],
        
        # GSTIN and Bank details row
        [Paragraph(f"GSTIN NO: {client.get('gstin','').upper()}", BODY_STYLE),  # Client GST number in uppercase
         bank_table],  # Nested table for bank details
        
        # Purchase Order row
        [Paragraph("Purchase Order", BODY_STYLE), ""]
    ]

    details_table = Table(details_data, colWidths=[page_width*0.5, page_width*0.5])
    details_table.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,0), 1.0, colors.black),
        ('LINEBELOW', (0,-1), (-1,-1), 1.0, colors.black),
        ('LINEBEFORE', (0,0), (0,-1), 1.0, colors.black),
        ('LINEAFTER', (-1,0), (-1,-1), 1.0, colors.black),
        ('LINEAFTER', (0,0), (0,-1), 1.0, colors.black),  # Vertical line between columns
        ('LINEBELOW', (0,0), (-1,0), 1.0, colors.black),  # Line below headers
        ('LINEBELOW', (0,3), (-1,3), 1.0, colors.black),  # Line above Purchase Order
        # Box the GSTIN cell (left column, row index 3) so it has its own borders
        ('BOX', (0,3), (0,3), 1.0, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('LEFTPADDING', (0,0), (-1,-1), 3),  # Aggressively reduced to 3
        ('RIGHTPADDING', (0,0), (-1,-1), 3),  # Aggressively reduced to 3
    ]))
    
    story.append(details_table)
    story.append(Spacer(1, 2))  # Aggressively reduced to 2

    # Items table
    headers = ["SL.NO","PARTICULARS","DESCRIPTION of SAC CODE","SAC CODE","QTY","RATE","TAXABLE AMOUNT"]
    col_w = [12*mm, 45*mm, (page_width - (12*mm + 45*mm + 22*mm + 14*mm + 22*mm + 26*mm)), 22*mm, 14*mm, 22*mm, 26*mm]
    total_w = sum(col_w)
    if total_w > page_width:
        scale = page_width / total_w
        col_w = [w*scale for w in col_w]

    table_data = [[Paragraph(h, HEADER_STYLE) for h in headers]]
    # We'll append rows and compute current row index dynamically
    for r in prepared:
        sl = str(r['slno'])
        part = r['particulars']
        desc = r['description']
        sac = r['sac_code']
        # Display: if None => blank; if numeric 0 -> show blank (per user's preference)
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

    # ensure at least one data row exists
    if len(table_data) == 1:
        table_data.append([Paragraph("-", BODY_STYLE)] + [Paragraph("-", BODY_STYLE)]*(len(headers)-1))

    # Append Training/Exam Dates inside the items table as a final row
    # Label in PARTICULARS column, dynamic date value in DESCRIPTION column
    train_val = invoice_meta.get('training_dates') or invoice_meta.get('training_exam_dates') or invoice_meta.get('training') or ""
    if train_val:
        # create a row where PARTICULARS column (index 1) has the label and DESCRIPTION column (index 2) has the date value
        training_row = [Paragraph("", BODY_STYLE),
                        Paragraph("<b>Training Dates/Exam Dates:</b>", BODY_STYLE),
                        Paragraph(train_val, DESC_STYLE),
                        Paragraph("", BODY_STYLE),
                        Paragraph("", BODY_STYLE),
                        Paragraph("", BODY_STYLE),
                        Paragraph("", BODY_STYLE)]
        table_data.append(training_row)
    
    # Append Process Name inside the items table as a final row (below Training/Exam Dates)
    # Label in PARTICULARS column, dynamic value in DESCRIPTION column
    process_val = invoice_meta.get('process_name') or ""
    if process_val:
        # create a row where PARTICULARS column (index 1) has the label and DESCRIPTION column (index 2) has the process name value
        process_row = [Paragraph("", BODY_STYLE),
                       Paragraph("<b>Process Name:</b>", BODY_STYLE),
                       Paragraph(process_val, DESC_STYLE),
                       Paragraph("", BODY_STYLE),
                       Paragraph("", BODY_STYLE),
                       Paragraph("", BODY_STYLE),
                       Paragraph("", BODY_STYLE)]
        table_data.append(process_row)
    
    # Append Advance Received inside the items table (below Process Name, if present)
    # Label in PARTICULARS column, value in DESCRIPTION column
    adv_received = invoice_meta.get('advance_received', 0) or 0
    if adv_received > 0:
        # create a row where PARTICULARS column (index 1) has the label and DESCRIPTION column (index 2) has the advance value
        adv_row = [Paragraph("", BODY_STYLE),
                   Paragraph("<b>Advance Received:</b>", BODY_STYLE),
                   Paragraph(f"{float(adv_received):,.2f}", DESC_STYLE),
                   Paragraph("", BODY_STYLE),
                   Paragraph("", BODY_STYLE),
                   Paragraph("", BODY_STYLE),
                   Paragraph("", BODY_STYLE)]
        table_data.append(adv_row)

    items_tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    tbl_style = [
        ('LINEABOVE', (0,0), (-1,0), 1.0, colors.black),  # Top border
        ('LINEBELOW', (0,-1), (-1,-1), 1.0, colors.black),  # Bottom border
        ('LINEBEFORE', (0,0), (0,-1), 1.0, colors.black),  # Left border
        ('LINEAFTER', (-1,0), (-1,-1), 1.0, colors.black),  # Right border
        ('LINEBELOW', (0,0), (-1,0), 1.0, colors.black),  # Header bottom border
        ('LINEAFTER', (0,0), (0,-1), 1.0, colors.black),  # Column dividers
        ('LINEAFTER', (1,0), (1,-1), 1.0, colors.black),
        ('LINEAFTER', (2,0), (2,-1), 1.0, colors.black),
        ('LINEAFTER', (3,0), (3,-1), 1.0, colors.black),
        ('LINEAFTER', (4,0), (4,-1), 1.0, colors.black),
        ('LINEAFTER', (5,0), (5,-1), 1.0, colors.black),
        ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.black),  # Thinner row dividers
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),  # Center align first column
        ('ALIGN', (-3,1), (-1,-1), 'RIGHT'),  # Right align last 3 columns
        ('LEFTPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('RIGHTPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('TOPPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),  # Aggressively reduced to 2
        ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),  # Header background
    ]
    # Blank cells will appear as empty/white (no black background)

    items_tbl.setStyle(TableStyle(tbl_style))
    story.append(items_tbl)

    

    # Totals calculation
    subtotal = sum([r['taxable_amount'] for r in prepared]) if prepared else Decimal("0.00")
    adv = Decimal(str(invoice_meta.get('advance_received', 0) or 0)).quantize(Decimal("0.01"))
    
    comp_state = gst_state_code(COMPANY.get('gstin',''))
    cli_state = gst_state_code(client.get('gstin','')) if client.get('gstin') else ""
    # Determine IGST usage: checkbox overrides everything (same logic as preview)
    force_igst = invoice_meta.get('use_igst', False)
    auto_igst = (comp_state and cli_state and comp_state != cli_state)
    # Manual checkbox takes priority: if explicitly set (checked), use that value
    # If checkbox unchecked, force SGST/CGST (override auto-detection)
    if force_igst is True:
        use_igst = True  # Checkbox checked -> force IGST
    elif force_igst is False:
        use_igst = False  # Checkbox unchecked -> force SGST/CGST (override auto-detection)
    else:
        use_igst = auto_igst  # Checkbox not set -> use auto-detection

    # Calculate taxes on the original subtotal
    if use_igst:
        igst = (subtotal * Decimal('0.18')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst = cgst = Decimal('0.00')
    else:
        sgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        igst = Decimal('0.00')

    # Calculate total after taxes, then subtract advance from final total
    total = subtotal + sgst + cgst + igst
    net = (total - adv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    totals_rows = []
    totals_rows.append([Paragraph("Sub Total", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {subtotal:,.2f}", TOTAL_VALUE_STYLE)])
    # Always show all tax rows with values (show 0.00 if not applicable)
    sgst_display = f"Rs. {sgst:,.2f}" if sgst > 0 else "Rs. 0.00"
    totals_rows.append([Paragraph("SGST (9%)", TOTAL_LABEL_STYLE), Paragraph(sgst_display, TOTAL_VALUE_STYLE)])
    cgst_display = f"Rs. {cgst:,.2f}" if cgst > 0 else "Rs. 0.00"
    totals_rows.append([Paragraph("CGST (9%)", TOTAL_LABEL_STYLE), Paragraph(cgst_display, TOTAL_VALUE_STYLE)])
    igst_display = f"Rs. {igst:,.2f}" if igst > 0 else "Rs. 0.00"
    totals_rows.append([Paragraph("IGST (18%)", TOTAL_LABEL_STYLE), Paragraph(igst_display, TOTAL_VALUE_STYLE)])
    totals_rows.append([Paragraph("<b>TOTAL</b>", ParagraphStyle("tot_bold_label", fontName=FONT_NAME, fontSize=11, leading=13)),
                        Paragraph(f"<b>Rs. {total:,.2f}</b>", ParagraphStyle("tot_bold_val", fontName=FONT_NAME, fontSize=11, leading=13, alignment=2))])
    # Show Less Advance Received row only if it exists (greater than 0)
    if adv > 0:
        totals_rows.append([Paragraph("Less Advance Received", TOTAL_LABEL_STYLE), Paragraph(f"Rs. {adv:,.2f}", TOTAL_VALUE_STYLE)])
    totals_rows.append([Paragraph("<b>Payable To Crux</b>", ParagraphStyle("tot_bold_label", fontName=FONT_NAME, fontSize=11, leading=13)),
                        Paragraph(f"<b>Rs. {net:,.2f}</b>", ParagraphStyle("tot_bold_val", fontName=FONT_NAME, fontSize=11, leading=13, alignment=2))])

    tot_tbl = Table(totals_rows, colWidths=[page_width*0.65, page_width*0.35], hAlign='RIGHT')
    tot_tbl.setStyle(TableStyle([
        ('INNERGRID',(0,0),(-1,-2),0.25,colors.lightgrey),
        ('LINEABOVE',(0,-1),(-1,-1),0.8,colors.black),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
        ('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('LEFTPADDING',(0,0),(-1,-1),3),  # Aggressively reduced to 3
        ('RIGHTPADDING',(0,0),(-1,-1),3),  # Aggressively reduced to 3
        ('TOPPADDING',(0,0),(-1,-1),2),  # Added aggressive top padding reduction
        ('BOTTOMPADDING',(0,0),(-1,-1),2)  # Added aggressive bottom padding reduction
    ]))
    story.append(tot_tbl)
    story.append(Spacer(1, 2))  # Aggressively reduced to 2

    story.append(Paragraph(f"In Words : ( {rupees_in_words(net)} )", BODY_STYLE))
    story.append(Spacer(1, 2))  # Aggressively reduced to 2 to prevent overlap

    # Signature is now added via onFirstPage callback (removed from story flow)
    # This ensures it appears on page 1 at bottom left regardless of content flow

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
    
    # Check if password is configured
    password = None
    try:
        password = st.secrets["app"]["password"]
    except Exception:
        password = os.getenv("APP_PASSWORD")
    
    # If no password is set, allow access without authentication
    if password is None:
        if not st.session_state.authenticated:
            st.session_state.authenticated = True
        return True
    
    # Password is configured - require authentication
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
            training_exam_dates = st.text_input("Training/Exam Dates (optional)")
            process_name = st.text_input("Process Name (optional)")

        st.subheader("Line Items (default items pre-populated)")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1, "particulars":"DEGREE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":2, "particulars":"UNDER GRADUATE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":3, "particulars":"NO OF CANDIDATES", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":4, "particulars":"EXAM FEE", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""},
                {"slno":5, "particulars":"HAND BOOKS", "description":"Commercial Training and Coaching Services", "sac_code":"999293", "qty":"", "rate":""}
            ]

        if st.button("Add New Blank Row"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":"", "rate":""})
            safe_rerun()

        for idx in range(len(st.session_state.rows)):
            r = st.session_state.rows[idx]
            # Render a visible card-like row with columns (no expander)
            st.markdown(
                f"""
                <div style="border:1px solid #e9ecef;border-radius:8px;padding:12px;margin-bottom:12px;background:#ffffff;">
                    <div style="font-weight:600;margin-bottom:8px;">Row {r.get('slno', idx+1)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Use a container so the inputs look grouped; columns match the desired row/column layout
            with st.container():
                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.0, 3.0, 4.0, 1.2, 1.0, 1.0, 1.0])
                new_sl = c1.number_input("S.No", value=int(r.get('slno', idx+1)), min_value=1, step=1, key=f"sl_{idx}")
                new_part = c2.text_input("Particulars", value=r.get('particulars', ''), key=f"part_{idx}")
                new_desc = c3.text_input("Description", value=r.get('description', ''), key=f"desc_{idx}")
                new_sac = c4.text_input("SAC", value=r.get('sac_code', ''), key=f"sac_{idx}")
                new_qty = c5.text_input("Qty", value=str(r.get('qty', '')), key=f"qty_{idx}")
                new_rate = c6.text_input("Rate", value=str(r.get('rate', '')), key=f"rate_{idx}")
                try:
                    qv = float(new_qty.replace(",", "")) if (new_qty and str(new_qty).strip() != "") else None
                except:
                    qv = None
                try:
                    rv = float(new_rate.replace(",", "")) if (new_rate and str(new_rate).strip() != "") else None
                except:
                    rv = None
                taxable_val = (qv * rv) if (qv is not None and rv is not None) else None
                # Show taxable amount or placeholder
                c7.write(f"Taxable: Rs. {taxable_val:,.2f}" if taxable_val is not None else "Taxable: -")
                # Persist updates back to session_state
                st.session_state.rows[idx].update({
                    "slno": new_sl,
                    "particulars": new_part,
                    "description": new_desc,
                    "sac_code": new_sac,
                    "qty": new_qty,
                    "rate": new_rate,
                })
                # Action buttons in a single, compact row under the inputs
                btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([1, 1, 1, 1])
                with btn_col1:
                    if st.button("Remove", key=f"remove_{idx}"):
                        st.session_state.rows.pop(idx)
                        # reindex serial numbers
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with btn_col2:
                    if st.button("Duplicate", key=f"dup_{idx}"):
                        dup = st.session_state.rows[idx].copy()
                        st.session_state.rows.insert(idx + 1, dup)
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with btn_col3:
                    if st.button("Move Up", key=f"up_{idx}") and idx > 0:
                        st.session_state.rows[idx - 1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx - 1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()
                with btn_col4:
                    if st.button("Move Down", key=f"down_{idx}") and idx < len(st.session_state.rows) - 1:
                        st.session_state.rows[idx + 1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx + 1]
                        for i, rr in enumerate(st.session_state.rows, start=1):
                            rr['slno'] = i
                        safe_rerun()

        if st.button("Add New Row (Bottom)"):
            st.session_state.rows.append({"slno": len(st.session_state.rows)+1, "particulars":"", "description":"", "sac_code":"", "qty":"", "rate":""})
            safe_rerun()

        force_igst = st.checkbox("Force IGST manually", value=False)
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

        # Render on-screen preview that resembles the invoice layout
        preview_meta = {
            "invoice_no": invoice_no, 
            "invoice_date": invoice_date.strftime("%d-%m-%Y"), 
            "client": client_info,
            "training_exam_dates": training_exam_dates,
            "process_name": process_name
        }
        try:
            render_invoice_preview(preview_meta, st.session_state.rows, subtotal_calc, force_igst, advance_received)
        except Exception as e:
            # If preview fails for any reason, still show subtotal
            st.write("Preview unavailable")
            st.error(f"Preview error: {str(e)}")

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
                    "advance_received": float(advance_received),
                    # include training/exam dates entered in the UI so PDF generator can render them
                    "training_exam_dates": training_exam_dates,
                    "process_name": process_name
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
