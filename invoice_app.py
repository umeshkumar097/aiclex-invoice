# invoice_app.py
import streamlit as st
import sqlite3
from datetime import date, datetime
import pandas as pd
from num2words import num2words
import os
import traceback

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image, PageBreak, Flowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ---------- Styles ----------
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Right', alignment=2))
styles.add(ParagraphStyle(name='Center', alignment=1))
styles.add(ParagraphStyle(name='Small', fontSize=8))

# ---------- Config ----------
DB_PATH = "invoices.db"
PDF_DIR = "generated_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

# Fixed company details (CRUX template) with asset paths
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
    "address": "# 403, 4th Floor, Diamond Block, Lumbini Rockdale, Somajiguda, Hyderabad - 500082, Telangana",
    "email": "mailadmin@cruxmanagement.com",
    "logo_top": "assets/logo_top.jpeg",
    "tagline": "assets/tagline.jpeg",
    "company_text": "assets/company_text.jpeg",
    "signature": "assets/signature_stamp.jpeg"
}

# ---------- Helpers ----------
def rupees_in_words(amount):
    """Convert float (e.g. 1817.20) to words including paise."""
    try:
        amount = float(amount)
    except:
        return ""
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    parts = []
    if rupees > 0:
        rwords = num2words(rupees, lang='en_IN').replace('-', ' ').title()
        parts.append(f"{rwords} Rupees")
    if paise > 0:
        pwords = num2words(paise, lang='en_IN').replace('-', ' ').title()
        parts.append(f"{pwords} Paise")
    if not parts:
        parts = ["Zero Rupees"]
    return " and ".join(parts) + " Only"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        gstin TEXT,
        pan TEXT,
        address TEXT,
        email TEXT
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

def get_clients():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, gstin, address, email FROM clients ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_client_by_id(cid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, gstin, pan, address, email FROM clients WHERE id=?", (cid,))
    row = cur.fetchone()
    conn.close()
    return row

def add_client(name, gstin, pan, address, email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO clients (name,gstin,pan,address,email) VALUES (?,?,?,?,?)", (name,gstin,pan,address,email))
    conn.commit()
    conn.close()

def update_client(cid, name, gstin, pan, address, email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE clients SET name=?, gstin=?, pan=?, address=?, email=? WHERE id=?", (name,gstin,pan,address,email,cid))
    conn.commit()
    conn.close()

def delete_client(cid):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM clients WHERE id=?", (cid,))
    conn.commit()
    conn.close()

# Small horizontal rule flowable
class HR(Flowable):
    def __init__(self, width, thickness=1, color=colors.black):
        Flowable.__init__(self)
        self.width = width
        self.thickness = thickness
        self.color = color
    def draw(self):
        self.canv.setLineWidth(self.thickness)
        self.canv.setStrokeColor(self.color)
        self.canv.line(0, 0, self.width, 0)

# ---------- PDF generation ----------
def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    """
    invoice_meta: dict {
        invoice_no, invoice_date, client (dict with name,gstin,pan,address,email),
        use_igst (bool), tax_rate (float), advance_received (float, optional)
    }
    line_items: list of dicts {slno, particulars, description, sac_code, qty, rate, taxable_amount}
    supporting_df: pandas.DataFrame (optional)
    """
    filename = f"Invoice_{invoice_meta.get('invoice_no','NA')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)

    # Document setup
    doc = SimpleDocTemplate(path,
                            pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    story = []

    # styles
    wrap_style = ParagraphStyle('wrap', fontSize=8, leading=10)
    footer_style = ParagraphStyle('footer', fontSize=7, alignment=1, leading=9)

    page_width = A4[0] - (15*mm + 15*mm)  # effective width after margins

    # Header: Logo centered top
    try:
        logo_path = COMPANY.get('logo_top', '')
        if logo_path and os.path.exists(logo_path):
            logo = Image(logo_path, width=90*mm, height=30*mm)
            logo.hAlign = 'CENTER'
            story.append(logo)
    except Exception as e:
        # show warning only if running inside Streamlit
        try:
            st.warning(f"Logo load warning: {e}")
        except:
            pass

    story.append(Spacer(1, 6))

    # optional company_text image below logo
    try:
        cpath = COMPANY.get('company_text', '')
        if cpath and os.path.exists(cpath):
            cimg = Image(cpath, width=page_width*0.9, height=12*mm)
            cimg.hAlign = 'CENTER'
            story.append(cimg)
    except Exception:
        pass

    # Tagline (optional) under logo/company_text
    try:
        tagpath = COMPANY.get('tagline', '')
        if tagpath and os.path.exists(tagpath):
            tag = Image(tagpath, width=page_width*0.95, height=10*mm)
            tag.hAlign = 'CENTER'
            story.append(tag)
    except Exception:
        pass

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>CRUX MANAGEMENT SERVICES</b>", ParagraphStyle('title', fontSize=14, alignment=1)))
    story.append(Spacer(1, 6))

    # Right aligned address block in a two-column row
    right_block = COMPANY['address'].replace("\n", "<br/>") + "<br/>Phone: " + COMPANY['phone'] + "<br/>email: " + COMPANY['email']
    top_table = Table([[Paragraph("", wrap_style), Paragraph(right_block, wrap_style)]], colWidths=[page_width*0.55, page_width*0.45])
    top_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(top_table)
    story.append(Spacer(1, 6))
    story.append(HR(page_width, thickness=1, color=colors.black))
    story.append(Spacer(1, 8))

    # Invoice header: left=client, right=invoice+bank details
    client = invoice_meta.get('client') or {}
    client_name = client.get('name', '')
    client_address = client.get('address', '')
    client_gstin = str(client.get('gstin', '')).upper()

    left_lines = [f"<b>To:</b> {client_name}", client_address, f"<b>GSTIN NO:</b> {client_gstin}"]
    left_html = "<br/>".join([l for l in left_lines if l.strip()])

    right_lines = [
        f"<b>INVOICE NO.:</b> {invoice_meta.get('invoice_no','')}",
        f"<b>DATE:</b> {invoice_meta.get('invoice_date','')}",
        "<b>Vendor Electronic Remittance</b>",
        f"Bank Name: {COMPANY['bank_name']}",
        f"A/C No : {COMPANY['bank_account']}",
        f"IFS Code : {COMPANY['ifsc']}",
        f"Swift Code : {COMPANY['swift']}",
        f"MICR No : {COMPANY['micr']}",
        f"Branch : {COMPANY['branch']}"
    ]
    right_html = "<br/>".join(right_lines)

    inv_table = Table([[Paragraph(left_html, wrap_style), Paragraph(right_html, wrap_style)]],
                      colWidths=[page_width*0.55, page_width*0.45])
    inv_table.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1),0.5,colors.grey),
        ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey),
        ('VALIGN',(0,0),(-1,-1),'TOP')
    ]))
    story.append(inv_table)
    story.append(Spacer(1, 10))

    # Line items table (wrapped cells)
    header = ["S.NO", "PARTICULARS", "DESCRIPTION of SAC CODE", "SAC CODE", "QTY", "RATE", "TAXABLE AMOUNT"]
    table_data = [header]

    for li in line_items:
        qty = li.get('qty', 0) or 0
        rate = li.get('rate', 0) or 0
        taxable = li.get('taxable_amount', qty * rate)
        row = [
            Paragraph(str(li.get('slno','')), wrap_style),
            Paragraph(str(li.get('particulars','')), wrap_style),
            Paragraph(str(li.get('description','')), wrap_style),
            Paragraph(str(li.get('sac_code','')), wrap_style),
            Paragraph(str(qty), wrap_style),
            Paragraph("₹ {:,.2f}".format(rate), wrap_style),
            Paragraph("₹ {:,.2f}".format(taxable), wrap_style)
        ]
        table_data.append(row)

    col_widths = [14*mm, 48*mm, page_width*0.40, 22*mm, 14*mm, 22*mm, 30*mm]
    t_items = Table(table_data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
    t_items.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.black),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (-3,1), (-1,-1), 'RIGHT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('LEFTPADDING',(0,0),(-1,-1),3),
        ('RIGHTPADDING',(0,0),(-1,-1),3),
    ]))
    story.append(t_items)
    story.append(Spacer(1, 8))

    # Totals & advance
    subtotal = sum([float(li.get('taxable_amount', 0) or 0) for li in line_items])
    advance = float(invoice_meta.get('advance_received', 0.0) or 0.0)
    if invoice_meta.get('use_igst'):
        igst = subtotal * invoice_meta.get('tax_rate', 0.18)
        sgst = cgst = 0.0
    else:
        sgst = subtotal * 0.09
        cgst = subtotal * 0.09
        igst = 0.0
    total = subtotal + sgst + cgst + igst
    net_payable = total - advance

    totals_data = [
        ["Sub Total", Paragraph("₹ {:,.2f}".format(subtotal), wrap_style)],
        ["SGST (9%)", Paragraph("₹ {:,.2f}".format(sgst), wrap_style)],
        ["CGST (9%)", Paragraph("₹ {:,.2f}".format(cgst), wrap_style)],
    ]
    if igst:
        totals_data.append(["IGST (18%)", Paragraph("₹ {:,.2f}".format(igst), wrap_style)])
    if advance > 0:
        totals_data.append(["Less: Advance Received", Paragraph("₹ {:,.2f}".format(advance), wrap_style)])
    totals_data.append(["NET PAYABLE", Paragraph("₹ {:,.2f}".format(net_payable), wrap_style)])

    t_tot = Table(totals_data, colWidths=[page_width*0.65, page_width*0.35], hAlign='RIGHT')
    t_tot.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.grey),
        ('ALIGN',(1,0),(1,-1),'RIGHT'),
        ('BACKGROUND',(0,-1),(-1,-1),colors.whitesmoke),
        ('FONTNAME',(-1,-1),(-1,-1),'Helvetica-Bold'),
    ]))
    story.append(t_tot)
    story.append(Spacer(1, 8))

    # Amount in words
    story.append(Paragraph(f"In Words : ( {rupees_in_words(net_payable)} )", wrap_style))
    story.append(Spacer(1, 12))

    # Signature area (with fallback)
    sig_img = None
    sigpath = COMPANY.get('signature', '')
    try:
        if sigpath and os.path.exists(sigpath):
            sig_img = Image(sigpath, width=50*mm, height=40*mm)
            sig_img.hAlign = 'LEFT'
    except Exception as e:
        try:
            st.warning(f"Signature image warning: {e}")
        except:
            pass

    sig_par = Paragraph("For Crux Management Services (P) Ltd<br/><br/>Authorised Signatory", styles['Normal'])
    if sig_img:
        story.append(KeepTogether([sig_img, Spacer(1,4), sig_par]))
    else:
        story.append(sig_par)

    # Tagline under signature if present
    try:
        tag2path = COMPANY.get('tagline', '')
        if tag2path and os.path.exists(tag2path):
            story.append(Spacer(1,6))
            tag2 = Image(tag2path, width=page_width*0.6, height=9*mm)
            tag2.hAlign = 'CENTER'
            story.append(tag2)
    except Exception:
        pass

    story.append(Spacer(1, 12))
    story.append(HR(page_width, thickness=0.5, color=colors.grey))
    footer = COMPANY['address'] + " | Phone: " + COMPANY['phone'] + " | email: " + COMPANY['email']
    story.append(Paragraph(footer, footer_style))
    story.append(Spacer(1, 6))

    # Supporting DataFrame page
    if supporting_df is not None and not supporting_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("Supporting Documents / Excel data", styles['Heading2']))
        df = supporting_df.fillna("").astype(str)
        data = [list(df.columns)]
        for _, r in df.iterrows():
            data.append(list(r.values))
        sup_tbl = Table(data, repeatRows=1, colWidths=None)
        sup_tbl.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.25,colors.grey),
            ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
            ('FONTSIZE',(0,0),(-1,-1),8)
        ]))
        story.append(sup_tbl)

    # Build PDF
    doc.build(story)
    return path

# ---------- Streamlit UI ----------
def main():
    st.set_page_config(page_title="Invoice System - CRUX Template", layout="wide")
    st.title("Invoice System — CRUX Template (Debug-enabled)")

    init_db()

    st.sidebar.header("Client Management")
    mode = st.sidebar.selectbox("Mode", ["Manage Clients", "Create Invoice", "History"])
    if mode == "Manage Clients":
        st.header("Manage Clients")
        clients = get_clients()
        df_clients = pd.DataFrame(clients, columns=['id','name','gstin','address','email'])
        st.dataframe(df_clients[['name','gstin','address','email']])

        with st.expander("Add New Client"):
            name = st.text_input("Company Name")
            gstin = st.text_input("GSTIN")
            pan = st.text_input("PAN")
            address = st.text_area("Address")
            email = st.text_input("Default Email")
            if st.button("Add Client"):
                if not name:
                    st.error("Name required")
                else:
                    add_client(name, gstin, pan, address, email)
                    st.success("Client added — refresh to see list")

        with st.expander("Edit / Delete Client"):
            clients_map = {f"{c[1]} ({c[2]})": c[0] for c in clients}
            sel = st.selectbox("Select client", options=["--select--"] + list(clients_map.keys()))
            if sel != "--select--":
                cid = clients_map[sel]
                rec = get_client_by_id(cid)
                if rec:
                    cid, name, gstin, pan, address, email = rec
                    name2 = st.text_input("Company Name", value=name)
                    gstin2 = st.text_input("GSTIN", value=gstin)
                    pan2 = st.text_input("PAN", value=pan)
                    address2 = st.text_area("Address", value=address)
                    email2 = st.text_input("Default Email", value=email)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Update Client"):
                            update_client(cid, name2, gstin2, pan2, address2, email2)
                            st.success("Updated")
                    with col2:
                        if st.button("Delete Client"):
                            delete_client(cid)
                            st.success("Deleted")

    elif mode == "Create Invoice":
        st.header("Create Invoice")
        clients = get_clients()
        clients_map = {f"{c[1]} ({c[2]})": c[0] for c in clients}
        client_sel = st.selectbox("Select Client", options=["--select--"] + list(clients_map.keys()))
        client_info = None
        if client_sel != "--select--":
            cid = clients_map[client_sel]
            rec = get_client_by_id(cid)
            if rec:
                client_info = {"id": rec[0], "name": rec[1], "gstin": rec[2], "pan": rec[3], "address": rec[4], "email": rec[5]}

        st.subheader("Invoice Header")
        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No", value=f"INV{int(datetime.now().timestamp())}")
            invoice_date = st.date_input("Invoice Date", value=date.today())
        with col2:
            payment_mode = st.selectbox("Payment Mode", ["Bank","UPI","Cash"])
            training_dates = st.text_input("Training/Exam Dates (optional)")

        st.subheader("Line Items")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1,"particulars":"DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":1,"rate":100,"taxable_amount":100},
                {"slno":2,"particulars":"NON DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":2,"rate":101,"taxable_amount":202},
            ]

        if st.button("Add Row"):
            new_sl = len(st.session_state.rows) + 1
            st.session_state.rows.append({"slno":new_sl,"particulars":"","description":"","sac_code":"","qty":0,"rate":0,"taxable_amount":0})

        for idx, r in enumerate(st.session_state.rows):
            cols = st.columns([1,3,4,1,1,1,1])
            r['slno'] = cols[0].number_input("S.No", value=r.get('slno', idx+1), key=f"sl{idx}")
            r['particulars'] = cols[1].text_input("Particulars", value=r.get('particulars',''), key=f"p{idx}")
            r['description'] = cols[2].text_input("Description", value=r.get('description',''), key=f"d{idx}")
            r['sac_code'] = cols[3].text_input("SAC", value=r.get('sac_code',''), key=f"sac{idx}")
            r['qty'] = cols[4].number_input("Qty", value=int(r.get('qty',0)), min_value=0, key=f"q{idx}")
            r['rate'] = cols[5].number_input("Rate", value=float(r.get('rate',0)), min_value=0.0, key=f"r{idx}")
            r['taxable_amount'] = r['qty'] * r['rate']
            cols[6].write(f"Taxable: {r['taxable_amount']:.2f}")

        use_igst = st.checkbox("Use IGST (18%)", value=False)
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

        subtotal = sum([r['taxable_amount'] for r in st.session_state.rows]) - advance_received
        if subtotal < 0:
            subtotal = 0
        sgst = subtotal*0.09 if not use_igst else 0
        cgst = subtotal*0.09 if not use_igst else 0
        igst = subtotal*0.18 if use_igst else 0
        total = subtotal + sgst + cgst + igst

        st.metric("Total Amount", f"₹{total:.2f}")
        st.write("In words:", rupees_in_words(total))

        if st.button("Generate PDF Invoice"):
            if not client_info:
                st.error("Select a client first.")
            else:
                invoice_meta = {
                    "invoice_no": invoice_no,
                    "invoice_date": invoice_date.strftime("%d-%m-%Y"),
                    "client": client_info,
                    "use_igst": use_igst,
                    "tax_rate": 0.18,
                    "advance_received": advance_received
                }
                try:
                    pdf_path = generate_invoice_pdf(invoice_meta, st.session_state.rows, supporting_df)
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("INSERT INTO invoices (invoice_no, invoice_date, client_id, subtotal, sgst, cgst, igst, total, pdf_path) VALUES (?,?,?,?,?,?,?,?,?)",
                                (invoice_no, invoice_date.strftime("%Y-%m-%d"), client_info['id'], subtotal, sgst, cgst, igst, total, pdf_path))
                    conn.commit()
                    conn.close()
                    st.success(f"PDF generated: {pdf_path}")
                    with open(pdf_path, "rb") as f:
                        st.download_button("Download PDF", f, file_name=os.path.basename(pdf_path), mime="application/pdf")
                except Exception as e:
                    st.error("Error generating PDF. See details below.")
                    st.text(traceback.format_exc())

    else:
        st.header("Invoice History")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM invoices ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        # If main crashes before Streamlit finishes, show traceback in the UI
        st.error("App crashed during startup. See error details:")
        st.text(traceback.format_exc())
