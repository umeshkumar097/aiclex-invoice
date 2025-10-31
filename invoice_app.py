# invoice_app.py
import streamlit as st
import sqlite3
from datetime import date, datetime
import pandas as pd
from num2words import num2words
import os
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
import smtplib
from email.message import EmailMessage

# ---------- CONFIG ----------
DB_PATH = "invoices.db"
PDF_DIR = "generated_pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

# Default email (used to send invoices). You can make this configurable in UI.
DEFAULT_FROM_EMAIL = "you@example.com"
SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587
SMTP_USER = "you@example.com"
SMTP_PASS = "YOUR_SMTP_PASSWORD"

# ---------- DB helpers ----------
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
        email TEXT,
        meta TEXT
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

# ---------- PDF generation ----------
styles = getSampleStyleSheet()

def rupees_in_words(amount):
    try:
        n = int(round(amount))
        s = num2words(n, lang='en_IN').replace('-', ' ')
        return s.title() + " Only"
    except Exception:
        return ""

def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None, signature_image_path=None):
    """
    invoice_meta: dict with keys:
        invoice_no, invoice_date, client (dict: name,gstin,pan,address,email), payment_mode, bank_details, training_dates, notes
    line_items: list of dicts with keys: slno, particulars, description, sac_code, qty, rate, taxable_amount
    supporting_df: pandas DataFrame (optional) to append as supporting pages
    """
    filename = f"Invoice_{invoice_meta['invoice_no']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)

    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm)
    story = []

    # Header - company details (use placeholders or real)
    company_title = "CRUX MANAGEMENT SERVICES (P) LTD"
    story.append(Paragraph(company_title, styles['Title']))
    story.append(Paragraph("HR SOLUTIONS  •  BPO SOLUTIONS  •  BUSINESS CONSULTANCY  •  TRAINING SOLUTIONS", styles['Normal']))
    story.append(Spacer(1, 6))

    # Invoice and client details table
    client = invoice_meta['client']
    left = [
        ["GSTIN NO :", client.get('gstin','')],
        ["PAN NO :", client.get('pan','')],
        ["Client Name :", client.get('name','')],
        ["Address :", client.get('address','')],
    ]
    right = [
        ["Invoice No :", invoice_meta['invoice_no']],
        ["Date :", invoice_meta['invoice_date']],
        ["Payment Mode :", invoice_meta.get('payment_mode','')],
    ]
    # Compose a table with two columns (left/right info)
    tbl_data = [
        [Paragraph("<b>Client Details</b>", styles['Normal']), Paragraph("<b>Invoice Details</b>", styles['Normal'])],
        [Paragraph("<br/>".join([f"{r[0]} {r[1]}" for r in left]), styles['Normal']), Paragraph("<br/>".join([f"{r[0]} {r[1]}" for r in right]), styles['Normal'])]
    ]
    t = Table(tbl_data, colWidths=[100*mm, 70*mm])
    t.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BOX',(0,0),(-1,-1),0.5,colors.grey),
        ('INNERGRID',(0,0),(-1,-1),0.25,colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1,8))

    # Line items header table
    header = ["SL.NO", "PARTICULARS", "DESCRIPTION of SAC CODE", "SAC CODE", "QTY", "RATE", "TAXABLE AMOUNT"]
    table_data = [header]
    for li in line_items:
        row = [
            li.get('slno',''),
            li.get('particulars',''),
            li.get('description',''),
            li.get('sac_code',''),
            str(li.get('qty','')),
            str(li.get('rate','')),
            "{:.2f}".format(li.get('taxable_amount',0))
        ]
        table_data.append(row)

    # Subtotal & totals placeholder rows will be appended after
    t_items = Table(table_data, colWidths=[12*mm, 40*mm, 58*mm, 25*mm, 15*mm, 18*mm, 28*mm])
    t_items.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.grey),
        ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ALIGN',(-2,1),(-1,-1),'RIGHT'),
    ]))
    story.append(t_items)
    story.append(Spacer(1,6))

    # Totals calculation
    subtotal = sum([li.get('taxable_amount',0) for li in line_items])
    # For simplicity determine IGST vs SGST/CGST based on a meta flag
    if invoice_meta.get('use_igst'):
        igst = subtotal * invoice_meta.get('tax_rate',0.18)
        sgst = cgst = 0
    else:
        sgst = subtotal * 0.09
        cgst = subtotal * 0.09
        igst = 0
    total = subtotal + sgst + cgst + igst

    # Totals table
    totals_data = [
        ["Sub Total", "{:.2f}".format(subtotal)],
        ["SGST (9%)", "{:.2f}".format(sgst)],
        ["CGST (9%)", "{:.2f}".format(cgst)],
    ]
    if igst:
        totals_data.append(["IGST (18%)", "{:.2f}".format(igst)])
    totals_data.append(["TOTAL", "{:.2f}".format(total)])

    t_tot = Table(totals_data, colWidths=[140*mm, 40*mm], hAlign='RIGHT')
    t_tot.setStyle(TableStyle([
        ('GRID',(0,0),(-1,-1),0.25,colors.grey),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey),
    ]))
    story.append(t_tot)
    story.append(Spacer(1,6))

    # Amount in words
    story.append(Paragraph(f"In Words: ( {rupees_in_words(total)} )", styles['Normal']))
    story.append(Spacer(1,12))

    # Signature placeholder and bank details if present
    story.append(Paragraph("For Crux Management Services (P) Ltd", styles['Normal']))
    story.append(Spacer(1,36))
    story.append(Paragraph("Authorised Signatory", styles['Normal']))
    story.append(Spacer(1,12))

    # If supporting df provided, add a page break and append as table(s)
    if supporting_df is not None and not supporting_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("Supporting Documents / Excel data", styles['Heading2']))
        # Convert DataFrame to table chunks if large
        df = supporting_df.fillna("").astype(str)
        data = [list(df.columns)]
        for _, r in df.iterrows():
            data.append(list(r.values))
        tbl = Table(data, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('GRID',(0,0),(-1,-1),0.25,colors.grey),
            ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
        ]))
        story.append(tbl)

    doc.build(story)
    return path

# ---------- Email helper ----------
def send_mail_with_attachment(to_email, subject, body, attachment_path, from_email=DEFAULT_FROM_EMAIL):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content(body)

    with open(attachment_path, 'rb') as f:
        data = f.read()
    maintype = 'application'
    subtype = 'pdf'
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(attachment_path))

    # SMTP send
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)

# ---------- Streamlit UI ----------
def main():
    st.set_page_config(page_title="Invoice System", layout="wide")
    st.title("Invoice System — Client DB + Invoice PDF + Excel supporting pages")

    init_db()

    st.sidebar.header("Client Management")
    mode = st.sidebar.selectbox("Mode", ["Manage Clients", "Create Invoice", "Sent Invoices / History"])
    if mode == "Manage Clients":
        st.header("Manage Clients")
        # list clients
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

        st.write("---")
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

        st.subheader("Invoice Line Items (use + to add rows)")
        # We'll manage dynamic rows using session state
        if "rows" not in st.session_state:
            # default rows as per your sample
            st.session_state.rows = [
                {"slno":1,"particulars":"DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":1,"rate":100,"taxable_amount":100},
                {"slno":2,"particulars":"NON DEGREE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":2,"rate":101,"taxable_amount":202},
                {"slno":3,"particulars":"NO OF CANDIDATES","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":3,"rate":102,"taxable_amount":306},
                {"slno":4,"particulars":"EXAM FEE","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":4,"rate":103,"taxable_amount":412},
                {"slno":5,"particulars":"HAND BOOKS","description":"Commercial Training And Coaching Services","sac_code":"999293","qty":5,"rate":104,"taxable_amount":520},
            ]

        # operations: add row / remove
        add_row = st.button("Add Row")
        if add_row:
            new_sl = len(st.session_state.rows) + 1
            st.session_state.rows.append({"slno":new_sl,"particulars":"","description":"","sac_code":"","qty":0,"rate":0,"taxable_amount":0})

        # display inputs for rows
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
            # remove button
            if cols[6].button("Remove", key=f"rm{idx}"):
                st.session_state.rows.pop(idx)
                st.experimental_rerun()

        # Advanced Received row (optional)
        advance_received = st.number_input("Advance Received (if any)", min_value=0.0, value=0.0)

        # Decide IGST or SGST/CGST
        use_igst = st.checkbox("Use IGST (18%) instead of SGST+CGST", value=False)

        # Supporting Excel upload
        st.subheader("Upload Supporting Excel (will be appended to PDF)")
        uploaded_file = st.file_uploader("Upload Excel (.xlsx/.xls)", type=["xlsx","xls","csv"])

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

        # Summary & generate
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
                # prepare line_items as dict list
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
                # store invoice summary in DB (basic)
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("INSERT INTO invoices (invoice_no, invoice_date, client_id, subtotal, sgst, cgst, igst, total, pdf_path) VALUES (?,?,?,?,?,?,?,?,?)",
                            (invoice_no, invoice_date.strftime("%Y-%m-%d"), client_info['id'], subtotal, sgst, cgst, igst, total, pdf_path))
                conn.commit()
                conn.close()
                st.success(f"PDF generated: {pdf_path}")
                st.markdown(f"[Download PDF]({pdf_path})")

                # Send to client default email?
                if client_info.get('email'):
                    if st.confirm("Do you want to email this invoice to client default email?"):
                        try:
                            subject = f"Invoice {invoice_no} from CRUX"
                            body = f"Dear {client_info.get('name')},\n\nPlease find attached invoice {invoice_no}.\n\nRegards"
                            send_mail_with_attachment(client_info.get('email'), subject, body, pdf_path)
                            st.success("Email sent to client default email.")
                        except Exception as e:
                            st.error("Email sending failed: " + str(e))
                else:
                    st.info("No default email set for client. You can set it in Manage Clients.")

    else:  # Sent Invoices / History (simple)
        st.header("Invoices (History)")
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT id, invoice_no, invoice_date, client_id, total, pdf_path FROM invoices ORDER BY id DESC", conn)
        # attach client names
        clients = {c[0]:c[1] for c in get_clients()}
        df['client'] = df['client_id'].apply(lambda x: clients.get(x, "Unknown"))
        st.dataframe(df[['invoice_no','invoice_date','client','total']])
        # download links
        for idx, row in df.iterrows():
            st.markdown(f"- {row['invoice_no']} | {row['invoice_date']} | {row['client']} | ₹{row['total']}  -  [Download]({row['pdf_path']})")

if __name__ == "__main__":
    main()
