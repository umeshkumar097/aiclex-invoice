# invoice_app.py
import streamlit as st
import sqlite3
from datetime import date, datetime
import pandas as pd
from num2words import num2words
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, Flowable
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

# Fixed company details (CRUX template) with asset paths (ensure assets/*.jpeg exist)
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
    try:
        n = int(round(amount))
        s = num2words(n, lang='en_IN').replace('-', ' ')
        return s.title() + " Only"
    except Exception:
        return ""

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
    filename = f"Invoice_{invoice_meta['invoice_no']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)
    story = []

    # Top logo (left)
    try:
        if os.path.exists(COMPANY['logo_top']):
            img = Image(COMPANY['logo_top'], width=70*mm, height=25*mm)
            img.hAlign = 'LEFT'
            story.append(img)
    except Exception:
        pass

    # Tagline (center)
    try:
        if os.path.exists(COMPANY['tagline']):
            img2 = Image(COMPANY['tagline'], width=180*mm, height=8*mm)
            img2.hAlign = 'CENTER'
            story.append(img2)
    except Exception:
        pass

    story.append(Spacer(1,4))
    story.append(Paragraph("<b>CRUX MANAGEMENT SERVICES</b>", ParagraphStyle('h1', fontSize=14, alignment=1)))
    right_block = COMPANY['address'].replace("\n", "<br/>") + "<br/>Phone: " + COMPANY['phone'] + "<br/>email:" + COMPANY['email']
    top_table = Table([[Paragraph("", styles['Normal']), Paragraph(right_block, styles['Normal'])]], colWidths=[100*mm, 70*mm])
    top_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(top_table)
    story.append(Spacer(1,6))
    story.append(HR(170*mm, thickness=1, color=colors.black))
    story.append(Spacer(1,6))

    # Invoice header: client left, invoice+bank right
    client = invoice_meta['client'] or {}
    left_lines = [
        f"To: {client.get('name','')}",
        client.get('address',''),
        f"GSTIN NO: {client.get('gstin','')}"
    ]
    left_html = "<br/>".join([l for l in left_lines if l])

    right_lines = [
        f"INVOICE NO.: {invoice_meta['invoice_no']}",
        f"DATE: {invoice_meta['invoice_date']}",
        "Vendor Electronic Remittance",
        f"Bank Name: {COMPANY['bank_name']}",
        f"A/C No : {COMPANY['bank_account']}",
        f"IFS Code : {COMPANY['ifsc']}",
        f"Swift Code : {COMPANY['swift']}",
        f"MICR No : {COMPANY['micr']}",
        f"Branch : {COMPANY['branch']}"
    ]
    right_html = "<br/>".join(right_lines)

    inv_table = Table([[Paragraph(left_html, styles['Normal']), Paragraph(right_html, styles['Normal'])]], colWidths=[100*mm, 70*mm])
    inv_table.setStyle(TableStyle([('BOX',(0,0),(-1,-1),0.5,colors.grey), ('VALIGN',(0,0),(-1,-1),'TOP'), ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey)]))
    story.append(inv_table)
    story.append(Spacer(1,8))

    # Line items table
    header = ["S.NO", "PARTICULARS", "DESCRIPTION of SAC CODE", "SAC CODE", "QTY", "RATE", "TAXABLE AMOUNT"]
    table_data = [header]
    for li in line_items:
        row = [
            li.get('slno',''),
            li.get('particulars',''),
            li.get('description',''),
            li.get('sac_code',''),
            str(li.get('qty','')),
            "{:.2f}".format(li.get('rate',0)),
            "{:.2f}".format(li.get('taxable_amount',0))
        ]
        table_data.append(row)

    col_widths = [12*mm, 42*mm, 68*mm, 22*mm, 12*mm, 20*mm, 28*mm]
    t_items = Table(table_data, colWidths=col_widths, repeatRows=1)
    t_items.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.3,colors.black),
        ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN',(0,0),(0,-1),'CENTER'),
        ('ALIGN',(-3,1),(-1,-1),'RIGHT'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
    ]))
    story.append(t_items)
    story.append(Spacer(1,6))

    # Totals
    subtotal = sum([li.get('taxable_amount',0) for li in line_items])
    if invoice_meta.get('use_igst'):
        igst = subtotal * invoice_meta.get('tax_rate',0.18)
        sgst = cgst = 0
    else:
        sgst = subtotal * 0.09
        cgst = subtotal * 0.09
        igst = 0
    total = subtotal + sgst + cgst + igst

    totals_data = [
        ["Sub Total", "{:.2f}".format(subtotal)],
        ["SGST (9%)", "{:.2f}".format(sgst)],
        ["CGST (9%)", "{:.2f}".format(cgst)],
    ]
    if igst:
        totals_data.append(["IGST (18%)", "{:.2f}".format(igst)])
    totals_data.append(["TOTAL", "{:.2f}".format(total)])

    t_tot = Table(totals_data, colWidths=[130*mm, 50*mm], hAlign='RIGHT')
    t_tot.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('ALIGN',(1,0),(1,-1),'RIGHT'), ('BACKGROUND',(0,-1),(-1,-1),colors.whitesmoke)]))
    story.append(t_tot)
    story.append(Spacer(1,6))

    story.append(Paragraph(f"In Words : ( {rupees_in_words(total)} )", styles['Normal']))
    story.append(Spacer(1,18))

    # Signature area
    sig_parts = []
    try:
        if os.path.exists(COMPANY['signature']):
            sig_img = Image(COMPANY['signature'], width=40*mm, height=40*mm)
            sig_img.hAlign = 'LEFT'
            sig_parts.append(sig_img)
    except Exception:
        pass
    sig_parts.append(Paragraph("For Crux Management Services (P) Ltd<br/><br/>Authorised Signatory", styles['Normal']))
    sig_table = Table([[sig_parts[0] if len(sig_parts)>0 else "", sig_parts[1]]], colWidths=[50*mm, 120*mm])
    sig_table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.append(sig_table)
    story.append(Spacer(1,12))

    story.append(HR(170*mm, thickness=0.5, color=colors.grey))
    footer = COMPANY['address'] + " | Phone: " + COMPANY['phone'] + " | email: " + COMPANY['email']
    story.append(Paragraph(footer, ParagraphStyle('foot', fontSize=8, alignment=1)))
    story.append(Spacer(1,6))

    # Supporting data as extra page
    if supporting_df is not None and not supporting_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("Supporting Documents / Excel data", styles['Heading2']))
        df = supporting_df.fillna("").astype(str)
        data = [list(df.columns)]
        for _, r in df.iterrows():
            data.append(list(r.values))
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.25,colors.grey), ('BACKGROUND',(0,0),(-1,0),colors.whitesmoke)]))
        story.append(tbl)

    doc.build(story)
    return path

# ---------- Streamlit UI ----------
def main():
    st.set_page_config(page_title="Invoice System - CRUX Template (v2)", layout="wide")
    st.title("Invoice System — CRUX Template (v2)")

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
        client_sel = st.selectbox("Select Client (choose or add in sidebar)", options=["--select--"] + list(clients_map.keys()))
        client_info = None
        if client_sel != "--select--":
            cid = clients_map[client_sel]
            rec = get_client_by_id(cid)
            if rec:
                c = {"id": rec[0], "name": rec[1], "gstin": rec[2], "pan": rec[3], "address": rec[4], "email": rec[5]}
                client_info = c

        st.subheader("Invoice Header")
        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice No", value=f"INV{int(datetime.now().timestamp())}")
            invoice_date = st.date_input("Invoice Date", value=date.today())
            payment_mode = st.selectbox("Payment Mode", ["Bank","UPI","Cash"])
        with col2:
            bank_details = st.text_area("Bank / Remittance Details (optional)")
            training_dates = st.text_input("Training/Exam Dates (optional)")

        st.subheader("Invoice Line Items (template rows)")
        if "rows" not in st.session_state:
            st.session_state.rows = [
                {"slno":1,"particulars":"DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":1,"rate":100,"taxable_amount":100},
                {"slno":2,"particulars":"NON DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":2,"rate":101,"taxable_amount":202},
                {"slno":3,"particulars":"NO OF CANDIDATES","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":3,"rate":102,"taxable_amount":306},
                {"slno":4,"particulars":"EXAM FEE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":4,"rate":103,"taxable_amount":412},
                {"slno":5,"particulars":"HAND BOOKS","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":5,"rate":104,"taxable_amount":520},
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
            if cols[6].button("Remove", key=f"rm{idx}"):
                st.session_state.rows.pop(idx)
                st.experimental_rerun()

        advance_received = st.number_input("Advance Received (if any)", min_value=0.0, value=0.0)
        use_igst = st.checkbox("Use IGST (18%) instead of SGST+CGST", value=False)

        st.subheader("Upload Supporting Excel (will be appended to PDF)")
        uploaded_file = st.file_uploader("Upload Excel (.xlsx/.xls/.csv)", type=["xlsx","xls","csv"])
        supporting_df = None
        if uploaded_file is not None:
            try:
                if uploaded_file.name.lower().endswith(".csv"):
                    supporting_df = pd.read_csv(uploaded_file)
                else:
                    supporting_df = pd.read_excel(uploaded_file)
                st.write("Preview of supporting data:")
                st.dataframe(supporting_df.head())
            except Exception as e:
                st.error("Error reading file: " + str(e))
                supporting_df = None

        st.write("---")
        subtotal = sum([r['taxable_amount'] for r in st.session_state.rows]) - advance_received
        if subtotal < 0:
            subtotal = 0
        if use_igst:
            igst = subtotal * 0.18
            sgst = cgst = 0
        else:
            sgst = subtotal * 0.09
            cgst = subtotal * 0.09
            igst = 0
        total = subtotal + sgst + cgst + igst

        st.metric("Subtotal", f"₹{subtotal:.2f}")
        st.metric("SGST", f"₹{sgst:.2f}")
        st.metric("CGST", f"₹{cgst:.2f}")
        if igst:
            st.metric("IGST", f"₹{igst:.2f}")
        st.metric("Total", f"₹{total:.2f}")
        st.write("In words:", rupees_in_words(total))

        if st.button("Generate PDF Invoice"):
            if client_info is None:
                st.error("Select a client first (or add one in Manage Clients).")
            else:
                invoice_meta = {
                    "invoice_no": invoice_no,
                    "invoice_date": invoice_date.strftime("%d-%m-%Y"),
                    "client": client_info,
                    "payment_mode": payment_mode,
                    "bank_details": bank_details,
                    "training_dates": training_dates,
                    "use_igst": use_igst,
                    "tax_rate": 0.18
                }
                line_items = []
                for r in st.session_state.rows:
                    line_items.append({
                        "slno": r.get('slno'),
                        "particulars": r.get('particulars'),
                        "description": r.get('description'),
                        "sac_code": r.get('sac_code'),
                        "qty": r.get('qty'),
                        "rate": r.get('rate'),
                        "taxable_amount": r.get('taxable_amount')
                    })
                pdf_path = generate_invoice_pdf(invoice_meta, line_items, supporting_df=supporting_df)
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("INSERT INTO invoices (invoice_no, invoice_date, client_id, subtotal, sgst, cgst, igst, total, pdf_path) VALUES (?,?,?,?,?,?,?,?,?)",
                            (invoice_no, invoice_date.strftime("%Y-%m-%d"), client_info['id'], subtotal, sgst, cgst, igst, total, pdf_path))
                conn.commit()
                conn.close()
                st.success(f"PDF generated: {pdf_path}")
                with open(pdf_path, "rb") as f:
                    st.download_button("Download PDF", data=f, file_name=os.path.basename(pdf_path), mime="application/pdf")
    else:
        st.header("Invoices (History)")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, invoice_no, invoice_date, client_id, total, pdf_path FROM invoices ORDER BY id DESC", conn)
        clients = {c[0]:c[1] for c in get_clients()}
        df['client'] = df['client_id'].apply(lambda x: clients.get(x, "Unknown"))
        st.dataframe(df[['invoice_no','invoice_date','client','total']])

if __name__ == "__main__":
    main()
