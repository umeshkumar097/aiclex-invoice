# invoice_app.py
# Crux Invoice Management System (layout updated to match client sample)
# Built by Aiclex Technologies
#
# Requirements:
# pip install streamlit pandas reportlab num2words openpyxl requests

import streamlit as st
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import os, time, traceback, requests
from decimal import Decimal, ROUND_HALF_UP
from num2words import num2words

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------- Config & assets ----------------
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

# Register Calibri if available
FONT_NAME = "Helvetica"
if os.path.exists(COMPANY["calibri_ttf"]):
    try:
        pdfmetrics.registerFont(TTFont("Calibri", COMPANY["calibri_ttf"]))
        FONT_NAME = "Calibri"
    except Exception:
        FONT_NAME = "Helvetica"

# ---------------- Styles ----------------
styles = getSampleStyleSheet()
TITLE = ParagraphStyle("title", parent=styles["Heading1"], fontName=FONT_NAME, fontSize=16, leading=18, alignment=1)
H1 = ParagraphStyle("h1", parent=styles["Normal"], fontName=FONT_NAME, fontSize=11, leading=13)
BODY = ParagraphStyle("body", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11)
RIGHT = ParagraphStyle("right", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11, alignment=2)
DESC = ParagraphStyle("desc", parent=styles["Normal"], fontName=FONT_NAME, fontSize=9, leading=11)
TOTAL_LABEL = ParagraphStyle("tlabel", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=12)
TOTAL_VALUE = ParagraphStyle("tval", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10, leading=12, alignment=2)
FOOTER = ParagraphStyle("footer", parent=styles["Normal"], fontName=FONT_NAME, fontSize=8, leading=9, alignment=1)

# ---------------- Helpers ----------------
def money(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
def rupees_in_words(amount):
    try:
        amt = float(amount)
    except:
        return ""
    rupees = int(amt)
    paise = int(round((amt - rupees) * 100))
    parts = []
    if rupees>0: parts.append(num2words(rupees, lang='en_IN').replace('-', ' ').title() + " Rupees")
    if paise>0: parts.append(num2words(paise, lang='en_IN').replace('-', ' ').title() + " Paise")
    if not parts: return "Zero Rupees Only"
    return " and ".join(parts) + " Only"

def gst_state_code(gstin):
    s = str(gstin or "").strip()
    if len(s)>=2 and s[:2].isdigit(): return s[:2]
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
        try: st.experimental_rerun()
        except: pass

# ---------------- Database ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, gstin TEXT UNIQUE, pan TEXT, address TEXT, email TEXT,
            purchase_order TEXT, state_code TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT, invoice_date TEXT, client_id INTEGER,
            subtotal REAL, sgst REAL, cgst REAL, igst REAL, total REAL, pdf_path TEXT
        )
    """)
    conn.commit(); conn.close()

def get_clients():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id,name,gstin,pan,address,email,purchase_order,state_code FROM clients ORDER BY name").fetchall()
    conn.close(); return rows

def get_client_by_id(cid):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id,name,gstin,pan,address,email,purchase_order,state_code FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close(); return row

def add_client(name,gstin,pan,address,email="",purchase_order="",state_code=""):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT OR REPLACE INTO clients (name,gstin,pan,address,email,purchase_order,state_code) VALUES (?,?,?,?,?,?,?)",
                     (name,gstin,pan,address,email,purchase_order,state_code))
        conn.commit(); return True, None
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_client(cid,name,gstin,pan,address,email="",purchase_order="",state_code=""):
    conn=sqlite3.connect(DB_PATH)
    conn.execute("UPDATE clients SET name=?,gstin=?,pan=?,address=?,email=?,purchase_order=?,state_code=? WHERE id=?",
                 (name,gstin,pan,address,email,purchase_order,state_code,cid))
    conn.commit(); conn.close()

def delete_client(cid):
    conn=sqlite3.connect(DB_PATH); conn.execute("DELETE FROM clients WHERE id=?", (cid,)); conn.commit(); conn.close()

# ---------------- GST API (optional) ----------------
def fetch_gst_from_appyflow(gstin, timeout=8):
    gstin=str(gstin).strip()
    if not gstin: return {"ok":False,"error":"Empty GSTIN"}
    key=None
    try: key=st.secrets["appyflow"]["key_secret"]
    except: key=os.getenv("APPYFLOW_KEY_SECRET")
    if not key: return {"ok":False,"error":"API key missing"}
    url="https://appyflow.in/api/verifyGST"
    try:
        r=requests.get(url, params={"key_secret":key,"gstNo":gstin}, timeout=timeout); r.raise_for_status(); j=r.json()
    except Exception as e: return {"ok":False,"error":f"Request failed: {e}"}
    info = j.get("taxpayerInfo") or j if isinstance(j,dict) else j
    name = info.get("tradeNam") or info.get("lgnm") or info.get("lgnm") or info.get("tradeName") or info.get("name") or ""
    pradr = info.get("pradr",{}) or {}
    addr_block = pradr.get("addr",{}) or {}
    addr_parts = []
    for key in ("bno","st","loc","city","dst","addr1","addr2","state"):
        if addr_block.get(key): addr_parts.append(str(addr_block.get(key)))
    addr = ", ".join(addr_parts)
    pan=None
    for pk in ("pan","panno","panNo","PAN"):
        if info.get(pk): pan=str(info.get(pk)); break
    if not pan and len(gstin)>=12: pan=gstin[2:12].upper()
    return {"ok":True,"name":name,"address":addr,"pan":pan,"gstin":gstin,"raw":j}

# ---------------- PDF generation (improved layout) ----------------
class HR(Flowable):
    def __init__(self,width,thickness=1,color=colors.black):
        Flowable.__init__(self); self.width=width; self.thickness=thickness; self.color=color
    def draw(self):
        self.canv.setLineWidth(self.thickness); self.canv.setStrokeColor(self.color); self.canv.line(0,0,self.width,0)

def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    """
    New invoice layout:
    - Header: centered logo + tagline
    - Bordered INVOICE area with GST/PAN/Phone row
    - Client box (left) & Invoice box (right) below
    - Items table (clean) — blank cells show nothing (no black)
    - Totals with lines; signature and footer image placed at bottom of same invoice page
    - Supporting docs appended in subsequent pages
    """
    from decimal import Decimal, ROUND_HALF_UP
    def q(v): return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Prepare items: convert to numeric where present, but allow blank strings -> treated as None (no black)
    prepared=[]
    for idx,r in enumerate(line_items, start=1):
        partic=str(r.get("particulars") or "").strip()
        desc=str(r.get("description") or "")
        sac=str(r.get("sac_code") or "")
        qty_raw=r.get("qty"); rate_raw=r.get("rate")
        # treat empty-string as None
        qty=None; rate=None
        try:
            if qty_raw is not None and str(qty_raw).strip()!="": qty=float(str(qty_raw).replace(",",""))
        except: qty=None
        try:
            if rate_raw is not None and str(rate_raw).strip()!="": rate=float(str(rate_raw).replace(",",""))
        except: rate=None
        taxable = q(qty*rate) if (qty is not None and rate is not None) else Decimal("0.00")
        prepared.append({"slno": r.get("slno") or idx, "particulars":partic, "description":desc, "sac_code":sac, "qty":qty, "rate":q(rate) if rate is not None else None, "taxable":taxable})

    # Build PDF
    filename = f"Invoice_{invoice_meta.get('invoice_no','NA')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    story=[]; page_width = A4[0] - (12*mm + 12*mm)

    # small util to add image if exists
    def add_img(path, width_mm=None, height_mm=None, align='CENTER', spacer=6):
        if path and os.path.exists(path):
            try:
                w = (width_mm*mm) if width_mm else None
                h = (height_mm*mm) if height_mm else None
                img = Image(path, width=w, height=h) if (w and h) else Image(path)
                img.hAlign = align
                story.append(img)
                if spacer: story.append(Spacer(1,spacer))
            except Exception:
                pass

    # Header: center logo + tagline
    add_img(COMPANY.get("logo_top"), width_mm=90, height_mm=27, align='CENTER', spacer=4)
    add_img(COMPANY.get("tagline"), width_mm=170, height_mm=6, align='CENTER', spacer=8)

    # Bordered INVOICE box with GST/PAN/Phone row
    invoice_title = Paragraph("<b>INVOICE</b>", ParagraphStyle("it", fontName=FONT_NAME, fontSize=14, alignment=1, leading=16))
    # Put invoice title inside a box row that spans width and contains GST/PAN/Phone
    gst_text = f"<b>GST IN :</b> {COMPANY.get('gstin','')}"
    pan_text = f"<b>PAN NO :</b> {COMPANY.get('pan','')}"
    phone_text = f"<b>Phone No. :</b> {COMPANY.get('phone','')}"
    # Create inner table: invoice title centered in a row, below a row with GST/PAN/Phone across full width
    inv_tbl = Table([
        [invoice_title],
        [Paragraph(gst_text + " &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" + pan_text + " &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" + phone_text, BODY)]
    ], colWidths=[page_width])
    inv_tbl.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.8,colors.black),
        ('ALIGN',(0,0),(-1,0),'CENTER'),
        ('ALIGN',(0,1),(-1,1),'LEFT'),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('BOTTOMPADDING',(0,0),(-1,0),6),
        ('TOPPADDING',(0,0),(-1,0),6),
        ('LEFTPADDING',(0,1),(-1,1),6),
        ('RIGHTPADDING',(0,1),(-1,1),6),
    ]))
    story.append(inv_tbl); story.append(Spacer(1,8))

    # Client left / Invoice right box (two columns)
    client = invoice_meta.get("client",{}) or {}
    left_lines=[]
    left_lines.append("<b>Service Location</b>")
    if client.get("name"): left_lines.append(f"To M/s: {client.get('name')}")
    if client.get("address"): left_lines.append(str(client.get("address")).replace("\n","<br/>"))
    if client.get("gstin"): left_lines.append(f"<b>GSTIN NO:</b> {client.get('gstin')}")
    if client.get("purchase_order"): left_lines.append(f"<b>Purchase Order:</b> {client.get('purchase_order')}")
    left_html = "<br/>".join(left_lines)

    right_lines=[]
    right_lines.append(f"<b>INVOICE NO. :</b> {invoice_meta.get('invoice_no','')}")
    right_lines.append(f"<b>DATE :</b> {invoice_meta.get('invoice_date','')}")
    right_lines.append("<br/>")
    right_lines.append("<b>Vendor Electronic Remittance</b>")
    right_lines.append(f"Bank Name : {COMPANY.get('bank_name','')}")
    right_lines.append(f"A/C No : {COMPANY.get('bank_account','')}")
    right_lines.append(f"IFS Code : {COMPANY.get('ifsc','')}")
    right_lines.append(f"Swift Code : {COMPANY.get('swift','')}")
    right_lines.append(f"MICR No : {COMPANY.get('micr','')}")
    right_lines.append(f"Branch : {COMPANY.get('branch','')}")
    right_html = "<br/>".join(right_lines)

    box = Table([[Paragraph(left_html,BODY), Paragraph(right_html,BODY)]], colWidths=[page_width*0.58, page_width*0.42])
    box.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.6,colors.black),
        ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),
        ('BOTTOMPADDING',(0,0),(-1,-1),6)
    ]))
    story.append(box); story.append(Spacer(1,8))

    # Items table header and data
    headers = ["SL. NO","PARTICULARS","DESCRIPTION of SAC CODE","SAC CODE","QTY","RATE","TAXABLE AMOUNT"]
    # tuned widths
    col_w = [12*mm, 45*mm, (page_width - (12*mm + 45*mm + 22*mm + 14*mm + 22*mm + 26*mm)), 22*mm, 14*mm, 22*mm, 26*mm]
    total_w = sum(col_w)
    if total_w > page_width:
        scale = page_width/total_w
        col_w = [w*scale for w in col_w]

    table_data = [[Paragraph(x, ParagraphStyle("hdr", fontName=FONT_NAME, fontSize=11, alignment=1)) for x in headers]]
    for r in prepared:
        sl = str(r["slno"])
        part = r["particulars"]
        desc = r["description"]
        sac = r["sac_code"]
        qty_display = "" if r["qty"] is None or r["qty"]==0 else (str(int(r["qty"])) if float(r["qty"]).is_integer() else str(r["qty"]))
        rate_display = "" if r["rate"] is None or float(r["rate"]) == 0 else f"{r['rate']:,.2f}"
        tax_display = "" if (r["qty"] is None or r["rate"] is None or r["taxable"]==Decimal("0.00")) else f"{r['taxable']:,.2f}"
        row = [
            Paragraph(sl,BODY),
            Paragraph(part,BODY),
            Paragraph(desc, DESC),
            Paragraph(sac,BODY),
            Paragraph(qty_display, RIGHT),
            Paragraph(rate_display, RIGHT),
            Paragraph(tax_display, RIGHT)
        ]
        table_data.append(row)

    items_tbl = Table(table_data, colWidths=col_w, repeatRows=1)
    items_tbl.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.35,colors.black),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),6),
        ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (4,1), (-1,-1), 'RIGHT')
    ]))
    story.append(items_tbl); story.append(Spacer(1,8))

    # Totals / taxes
    subtotal = sum([r["taxable"] for r in prepared]) if prepared else Decimal("0.00")
    adv = Decimal(str(invoice_meta.get("advance_received",0) or 0)).quantize(Decimal("0.01"))
    comp_state = gst_state_code(COMPANY.get("gstin",""))
    cli_state = gst_state_code(client.get("gstin","")) if client.get("gstin") else ""
    use_igst = invoice_meta.get("use_igst", False)
    if comp_state and cli_state and comp_state != cli_state: use_igst = True

    if use_igst:
        igst = (subtotal * Decimal('0.18')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        sgst = cgst = Decimal("0.00")
    else:
        sgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cgst = (subtotal * Decimal('0.09')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        igst = Decimal("0.00")

    total = subtotal + sgst + cgst + igst
    net = (total - adv).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    tot_rows = []
    tot_rows.append([Paragraph("Sub Total", TOTAL_LABEL), Paragraph(f"Rs. {subtotal:,.2f}", TOTAL_VALUE)])
    if use_igst:
        tot_rows.append([Paragraph("IGST (18%)", TOTAL_LABEL), Paragraph(f"Rs. {igst:,.2f}", TOTAL_VALUE)])
    else:
        tot_rows.append([Paragraph("SGST (9%)", TOTAL_LABEL), Paragraph(f"Rs. {sgst:,.2f}", TOTAL_VALUE)])
        tot_rows.append([Paragraph("CGST (9%)", TOTAL_LABEL), Paragraph(f"Rs. {cgst:,.2f}", TOTAL_VALUE)])
    if adv > 0:
        tot_rows.append([Paragraph("Less Advance Received", TOTAL_LABEL), Paragraph(f"Rs. {adv:,.2f}", TOTAL_VALUE)])
    tot_rows.append([Paragraph("<b>TOTAL</b>", ParagraphStyle("tbold", fontName=FONT_NAME, fontSize=11)), Paragraph(f"<b>Rs. {net:,.2f}</b>", ParagraphStyle("tboldv", fontName=FONT_NAME, fontSize=11, alignment=2))])

    tot_tbl = Table(tot_rows, colWidths=[page_width*0.65, page_width*0.35], hAlign='RIGHT')
    tot_tbl.setStyle(TableStyle([
        ('LINEABOVE', (0,-1), (-1,-1), 0.7, colors.black),
        ('BACKGROUND',(0,-1),(-1,-1), colors.whitesmoke),
        ('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('LEFTPADDING',(0,0),(-1,-1),6), ('RIGHTPADDING',(0,0),(-1,-1),6)
    ]))
    story.append(tot_tbl); story.append(Spacer(1,8))

    story.append(Paragraph(f"In Words : ( {rupees_in_words(net)} )", BODY)); story.append(Spacer(1,8))

    # Signature block
    story.append(Spacer(1,12))
    if os.path.exists(COMPANY.get("signature")):
        try:
            sig = Image(COMPANY["signature"], width=44*mm, height=31*mm)
            sig.hAlign = "LEFT"
            story.append(sig)
        except:
            pass
    story.append(Paragraph("For " + COMPANY.get("name",""), BODY))
    story.append(Paragraph("Authorised Signatory", BODY))
    story.append(Spacer(1,8))

    # Footer company_text image placed at bottom of invoice page (center)
    add_img(COMPANY.get("company_text"), width_mm=170, height_mm=28, align='CENTER', spacer=4)

    # Supporting doc pages (optional)
    if supporting_df is not None and not supporting_df.empty:
        try:
            df = supporting_df.fillna("").astype(str)
            story.append(PageBreak())
            story.append(Paragraph("Supporting Documents / Excel data", TITLE))
            story.append(Spacer(1,6))

            cols = list(df.columns)
            max_cols = 10
            for start in range(0,len(cols),max_cols):
                subset = cols[start:start+max_cols]
                subdf = df[subset]
                header = [Paragraph(str(c), ParagraphStyle("sh", fontName=FONT_NAME, fontSize=9, alignment=1)) for c in subdf.columns]
                rows=[header]
                for _,row in subdf.iterrows():
                    rows.append([Paragraph(" ".join(str(row[c]).split()), ParagraphStyle("cell", fontName=FONT_NAME, fontSize=7)) for c in subdf.columns])
                colw = [page_width/len(subset) for _ in subset]
                t = Table(rows, colWidths=colw, repeatRows=1)
                t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke), ('VALIGN',(0,0),(-1,-1),'TOP')]))
                story.append(t); story.append(Spacer(1,8))

            # stamp bottom-right on supporting pages too
            if os.path.exists(COMPANY.get("signature")):
                try:
                    stamp = Image(COMPANY["signature"], width=44*mm, height=31*mm)
                    stamp.hAlign = "RIGHT"
                    story.append(stamp)
                except:
                    pass
        except Exception as e:
            story.append(Paragraph("Error rendering supporting sheet: " + str(e), BODY))

    doc.build(story)
    return path

# ---------------- UI & other helpers ----------------
def normalize_uploaded_df(df):
    df = df.copy(); df.columns = [str(c).strip() for c in df.columns]
    lower = {c.lower(): c for c in df.columns}
    mapping = {}
    for k in ("gstin","gst","gst_no","gst number"):
        if k in lower: mapping['gstin']=lower[k]; break
    for k in ("name","company","company_name","trade_name"):
        if k in lower: mapping['name']=lower[k]; break
    for k in ("address","addr","company_address"):
        if k in lower: mapping['address']=lower[k]; break
    for k in ("pan","panno"):
        if k in lower: mapping['pan']=lower[k]; break
    if 'gstin' not in mapping and len(df.columns)>0: mapping['gstin']=df.columns[0]
    out=[]
    for _,row in df.iterrows():
        out.append({
            "gstin": str(row.get(mapping.get('gstin')) or "").strip(),
            "name": str(row.get(mapping.get('name')) or "").strip(),
            "address": str(row.get(mapping.get('address')) or "").strip(),
            "pan": str(row.get(mapping.get('pan')) or "").strip()
        })
    return pd.DataFrame(out)

# --- Authentication
def check_password():
    if "authenticated" not in st.session_state: st.session_state.authenticated=False
    if st.session_state.authenticated:
        val = st.sidebar.select_slider("Session", options=["Stay Logged In","Logout"], value="Stay Logged In")
        if val=="Logout":
            st.session_state.authenticated=False; safe_rerun()
        st.sidebar.markdown("**Logged in**")
        return True
    st.write("**Enter password to continue**")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        password=None
        try: password=st.secrets["app"]["password"]
        except: password=os.getenv("APP_PASSWORD")
        if password is None:
            st.warning("Set APP_PASSWORD env or app.password secret.")
            return False
        if pwd==password:
            st.session_state.authenticated=True; st.success("Logged in"); safe_rerun(); return True
        else:
            st.error("Incorrect password"); return False
    return False

# ---------------- Streamlit app ----------------
def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE); st.caption(APP_BUILT_BY)
    init_db()

    if not check_password(): return

    mode = st.sidebar.selectbox("Mode", ["Manage Clients","Create Invoice","History"])

    # Manage Clients
    if mode=="Manage Clients":
        st.header("Manage Clients")
        clients = get_clients()
        if clients:
            dfc = pd.DataFrame(clients, columns=['id','name','gstin','pan','address','email','purchase_order','state_code'])
            st.dataframe(dfc[['name','gstin','state_code','purchase_order']])
        st.subheader("Add Client")
        with st.form("add_client"):
            gstin = st.text_input("GSTIN", max_chars=15)
            name = st.text_input("Company Name")
            pan = st.text_input("PAN (optional)")
            address = st.text_area("Address")
            purchase_order = st.text_input("Purchase Order (optional)")
            submit = st.form_submit_button("Save Client")
            if submit:
                if not name: st.error("Name required")
                else:
                    sc = gst_state_code(gstin) or ""
                    ok,err = add_client(name,gstin,pan,address,email="",purchase_order=purchase_order,state_code=sc)
                    if ok: st.success("Client saved"); safe_rerun()
                    else: st.error(f"Save error: {err}")

        st.subheader("Bulk Upload (CSV/XLSX)")
        uploaded = st.file_uploader("Upload", type=["csv","xlsx"])
        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"): df_raw = pd.read_csv(uploaded, dtype=str, keep_default_na=False)
                else: df_raw = pd.read_excel(uploaded, dtype=str)
                st.success(f"Loaded {uploaded.name} rows:{len(df_raw)}"); st.dataframe(df_raw.head())
                st.session_state._bulk_df = normalize_uploaded_df(df_raw)
            except Exception as e:
                st.error(f"File read error: {e}"); st.session_state._bulk_df=None

        bulk_df = st.session_state.get("_bulk_df")
        if bulk_df is not None:
            st.dataframe(bulk_df.head(20))
            verify_api = st.checkbox("Verify via GST API (appyflow)", value=False)
            if st.button("Add all (no verify)"):
                added=0
                for _,r in bulk_df.iterrows():
                    ok,err = add_client(r.get("name",""), r.get("gstin",""), r.get("pan",""), r.get("address",""), email="", purchase_order="", state_code=gst_state_code(r.get("gstin","")))
                    if ok: added+=1
                st.success(f"Added {added}"); safe_rerun()

    # Create Invoice
    elif mode=="Create Invoice":
        st.header("Create Invoice")
        clients = get_clients()
        client_map = {}
        for c in clients:
            cid,name,gstin,_,addr,_,po,stc = c
            label = f"{name} | {gstin} - {state_label_from_gst(gstin)}"
            client_map[label]=cid
        options = ["--select--"] + list(client_map.keys())
        sel = st.selectbox("Select Client", options)
        client_info=None
        if sel!="--select--":
            cid = client_map[sel]
            rec = get_client_by_id(cid)
            if rec:
                cid,name,gstin,pan,address,email,purchase_order,state_code = rec
                client_info={"id":cid,"name":name,"gstin":gstin,"pan":pan,"address":address,"purchase_order":purchase_order}

        col1,col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No", value=f"INV{int(datetime.now().timestamp())}")
            invoice_date = st.date_input("Invoice Date", value=date.today())
        with col2:
            payment_mode = st.selectbox("Payment Mode", ["Bank","UPI","Cash"])
            training_dates = st.text_input("Training/Exam Dates (optional)")

        st.subheader("Line Items (defaults)")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1,"particulars":"DEGREE","description":"Commercial Training and Coaching Services","sac_code":"999293","qty":"","rate":""},
                {"slno":2,"particulars":"UNDER GRADUATE","description":"Commercial Training and Coaching Services","sac_code":"999293","qty":"","rate":""},
                {"slno":3,"particulars":"NO OF CANDIDATES","description":"Commercial Training and Coaching Services","sac_code":"999293","qty":"","rate":""},
                {"slno":4,"particulars":"EXAM FEE","description":"Commercial Training and Coaching Services","sac_code":"999293","qty":"","rate":""},
                {"slno":5,"particulars":"HAND BOOKS","description":"Commercial Training and Coaching Services","sac_code":"999293","qty":"","rate":""},
                {"slno":6,"particulars":"Advance Received","description":"","sac_code":"","qty":"","rate":""},
            ]
        if st.button("Add Blank Row"):
            st.session_state.rows.append({"slno":len(st.session_state.rows)+1,"particulars":"","description":"","sac_code":"","qty":"","rate":""}); safe_rerun()

        for idx in range(len(st.session_state.rows)):
            r=st.session_state.rows[idx]
            with st.expander(f"Row {r.get('slno', idx+1)}", expanded=False):
                c1,c2,c3,c4,c5,c6,c7 = st.columns([1,3,4,1.2,1,1,1])
                new_sl = c1.number_input("S.No", value=int(r.get('slno',idx+1)), min_value=1, step=1, key=f"sl_{idx}")
                new_part = c2.text_input("Particulars", value=r.get("particulars",""), key=f"part_{idx}")
                new_desc = c3.text_input("Description", value=r.get("description",""), key=f"desc_{idx}")
                new_sac = c4.text_input("SAC", value=r.get("sac_code",""), key=f"sac_{idx}")
                new_qty = c5.text_input("Qty (blank if NA)", value=str(r.get("qty","")), key=f"qty_{idx}")
                new_rate = c6.text_input("Rate (blank if NA)", value=str(r.get("rate","")), key=f"rate_{idx}")
                try:
                    qv = float(new_qty.replace(",","")) if (new_qty and str(new_qty).strip()!="") else None
                except: qv=None
                try:
                    rv = float(new_rate.replace(",","")) if (new_rate and str(new_rate).strip()!="") else None
                except: rv=None
                taxable = (qv*rv) if (qv is not None and rv is not None) else 0.0
                c7.write(f"Taxable: Rs. {taxable:,.2f}" if (qv is not None and rv is not None) else "Taxable: -")
                st.session_state.rows[idx].update({"slno":new_sl,"particulars":new_part,"description":new_desc,"sac_code":new_sac,"qty":new_qty,"rate":new_rate})
                b1,b2,b3,b4 = st.columns([1,1,1,1])
                with b1:
                    if st.button("Remove", key=f"rm_{idx}"): st.session_state.rows.pop(idx); safe_rerun()
                with b2:
                    if st.button("Dup", key=f"dup_{idx}"): st.session_state.rows.insert(idx+1, st.session_state.rows[idx].copy()); safe_rerun()
                with b3:
                    if st.button("Up", key=f"up_{idx}") and idx>0:
                        st.session_state.rows[idx-1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx-1]; safe_rerun()
                with b4:
                    if st.button("Down", key=f"down_{idx}") and idx < len(st.session_state.rows)-1:
                        st.session_state.rows[idx+1], st.session_state.rows[idx] = st.session_state.rows[idx], st.session_state.rows[idx+1]; safe_rerun()

        force_igst = st.checkbox("Force IGST (18%)", value=False)
        advance_received = st.number_input("Advance Received (if any)", min_value=0.0, value=0.0)
        uploaded_file = st.file_uploader("Upload Supporting Excel (.xlsx/.csv)", type=["xlsx","csv"])
        supporting_df=None
        if uploaded_file:
            try:
                if uploaded_file.name.lower().endswith(".csv"): supporting_df = pd.read_csv(uploaded_file)
                else: supporting_df = pd.read_excel(uploaded_file)
                st.dataframe(supporting_df.head())
            except Exception as e:
                st.error(f"Read error: {e}")

        # compute subtotal
        subtotal=0.0
        for r in st.session_state.rows:
            try:
                qv = float(str(r.get("qty","")).replace(",","")) if (r.get("qty") and str(r.get("qty")).strip()!="") else None
            except: qv=None
            try:
                rv = float(str(r.get("rate","")).replace(",","")) if (r.get("rate") and str(r.get("rate")).strip()!="") else None
            except: rv=None
            if qv is not None and rv is not None: subtotal += qv*rv
        st.metric("Subtotal", f"Rs. {subtotal:,.2f}")

        if st.button("Generate PDF Invoice"):
            if not client_info:
                st.error("Select client first"); st.stop()
            meta = {"invoice_no": invoice_no, "invoice_date": invoice_date.strftime("%d-%m-%Y"), "client": client_info, "use_igst": force_igst, "advance_received": float(advance_received)}
            try:
                pdf_path = generate_invoice_pdf(meta, st.session_state.rows, supporting_df)
                # save to DB
                comp_state = gst_state_code(COMPANY.get("gstin",""))
                cli_state = gst_state_code(client_info.get("gstin",""))
                auto_igst=False
                if comp_state and cli_state and comp_state!=cli_state: auto_igst=True
                use_igst = force_igst or auto_igst
                if use_igst: igst = subtotal * 0.18; sgst = cgst = 0.0
                else: sgst = cgst = subtotal*0.09; igst=0.0
                total = subtotal + sgst + cgst + igst - float(advance_received)
                conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
                cur.execute("INSERT INTO invoices (invoice_no,invoice_date,client_id,subtotal,sgst,cgst,igst,total,pdf_path) VALUES (?,?,?,?,?,?,?,?,?)",
                            (meta["invoice_no"], invoice_date.strftime("%Y-%m-%d"), client_info["id"], subtotal, sgst, cgst, igst, total, pdf_path))
                conn.commit(); conn.close()
                st.success(f"PDF generated: {pdf_path}")
                with open(pdf_path,"rb") as f: st.download_button("Download PDF", f, file_name=os.path.basename(pdf_path), mime="application/pdf")
            except Exception:
                st.error("Error generating PDF"); st.text(traceback.format_exc())

    # History
    else:
        st.header("Invoice History")
        conn = sqlite3.connect(DB_PATH)
        col1,col2,col3 = st.columns(3)
        with col1: start_date = st.date_input("From", value=date.today()-timedelta(days=30))
        with col2: end_date = st.date_input("To", value=date.today())
        with col3: refresh = st.button("Refresh")
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
        if dfhist.empty: st.info("No invoices in range.")
        else: st.dataframe(dfhist)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        st.error("App crashed. See traceback:")
        st.text(traceback.format_exc())
