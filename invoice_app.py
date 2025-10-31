from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepTogether

# -----------------------
# Replace / add this:
# rupees_in_words -> includes paise
# -----------------------
def rupees_in_words(amount):
    """
    Convert a float amount (e.g. 1817.20) to 'One Thousand Eight Hundred Seventeen Rupees and Twenty Paise Only'
    """
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


# -----------------------
# Replace / add this:
# generate_invoice_pdf -> final improved version
# -----------------------
def generate_invoice_pdf(invoice_meta, line_items, supporting_df=None):
    """
    invoice_meta: dict {
        invoice_no, invoice_date, client (dict with name,gstin,pan,address,email),
        use_igst (bool), tax_rate (float), advance_received (float, optional)
    }
    line_items: list of dicts {slno, particulars, description, sac_code, qty, rate, taxable_amount}
    supporting_df: pandas.DataFrame (optional)
    """
    filename = f"Invoice_{invoice_meta['invoice_no']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    path = os.path.join(PDF_DIR, filename)

    # Document setup
    doc = SimpleDocTemplate(path,
                            pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)

    story = []

    # small paragraph style for wrapping table cells
    wrap_style = ParagraphStyle('wrap', fontSize=8, leading=10)
    small_center = ParagraphStyle('small_center', fontSize=8, alignment=1)
    footer_style = ParagraphStyle('footer', fontSize=7, alignment=1, leading=9)

    page_width = A4[0] - (15*mm + 15*mm)  # effective width after margins

    # -------------------
    # Header: CENTERED logo
    # -------------------
    try:
        if os.path.exists(COMPANY.get('logo_top', '')):
            logo = Image(COMPANY['logo_top'], width=90*mm, height=30*mm)
            logo.hAlign = 'CENTER'
            story.append(logo)
    except Exception as e:
        # Streamlit warning will show on UI
        try:
            st.warning(f"Logo load warning: {e}")
        except:
            pass

    # Small spacer and possibly company_text image (optional)
    story.append(Spacer(1, 6))
    # If you also have a company_text image (centered under logo), show it
    try:
        if os.path.exists(COMPANY.get('company_text', '')):
            cimg = Image(COMPANY['company_text'], width=page_width*0.9, height=12*mm)
            cimg.hAlign = 'CENTER'
            story.append(cimg)
    except Exception:
        pass

    # -------------------
    # Tagline: we will not place it at top again if you want tagline below signature,
    # but if you want tagline at top, ensure COMPANY['tagline'] exists and show it here:
    try:
        if os.path.exists(COMPANY.get('tagline', '')):
            tag = Image(COMPANY['tagline'], width=page_width*0.95, height=10*mm)
            tag.hAlign = 'CENTER'
            story.append(tag)
    except Exception:
        pass

    story.append(Spacer(1, 8))

    # Company title centered (if you prefer text)
    story.append(Paragraph("<b>CRUX MANAGEMENT SERVICES</b>", ParagraphStyle('title', fontSize=14, alignment=1)))
    story.append(Spacer(1, 6))

    # Right-aligned address block (kept on the same line area using a 2-col table)
    right_block = COMPANY['address'].replace("\n", "<br/>") + "<br/>Phone: " + COMPANY['phone'] + "<br/>email: " + COMPANY['email']
    top_table = Table([[Paragraph("", wrap_style), Paragraph(right_block, wrap_style)]], colWidths=[page_width*0.55, page_width*0.45])
    top_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN',(1,0),(1,0),'RIGHT')]))
    story.append(top_table)
    story.append(Spacer(1, 6))

    # Horizontal line
    story.append(HR(page_width, thickness=1, color=colors.black))
    story.append(Spacer(1, 8))

    # -------------------
    # Invoice header: left = client details, right = invoice + bank details
    # -------------------
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

    # -------------------
    # Line items table with Paragraph-wrapped cells so text wraps within column
    # -------------------
    header = ["S.NO", "PARTICULARS", "DESCRIPTION of SAC CODE", "SAC CODE", "QTY", "RATE", "TAXABLE AMOUNT"]
    table_data = [header]

    for li in line_items:
        # ensure proper types
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

    # Column widths tuned to allow wrapping; adjust if required
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

    # -------------------
    # Totals, Advance, Net Payable
    # -------------------
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

    # Amount in words (including paise)
    story.append(Paragraph(f"In Words : ( {rupees_in_words(net_payable)} )", wrap_style))
    story.append(Spacer(1, 12))

    # -------------------
    # Signature area with tagline under signature (as you requested)
    # -------------------
    sig_img = None
    try:
        if os.path.exists(COMPANY.get('signature', '')):
            sig_img = Image(COMPANY['signature'], width=50*mm, height=40*mm)
            sig_img.hAlign = 'LEFT'
    except Exception as e:
        try:
            st.warning(f"Signature image warning: {e}")
        except:
            pass

    sig_par = Paragraph("For Crux Management Services (P) Ltd<br/><br/>Authorised Signatory", styles['Normal'])

    if sig_img:
        # Keep signature + text together using KeepTogether so they don't split badly
        story.append(KeepTogether([sig_img, Spacer(1,4), sig_par]))
    else:
        story.append(sig_par)

    # Tagline under signature block (as requested to appear in sign area)
    try:
        if os.path.exists(COMPANY.get('tagline', '')):
            # If tagline image exists we will show it beneath signature area (centered)
            tag2 = Image(COMPANY['tagline'], width=page_width*0.6, height=9*mm)
            tag2.hAlign = 'CENTER'
            story.append(Spacer(1,6))
            story.append(tag2)
    except Exception:
        pass

    story.append(Spacer(1, 12))

    # Footer HR and details
    story.append(HR(page_width, thickness=0.5, color=colors.grey))
    footer = COMPANY['address'] + " | Phone: " + COMPANY['phone'] + " | email: " + COMPANY['email']
    story.append(Paragraph(footer, footer_style))
    story.append(Spacer(1, 6))

    # -------------------
    # Supporting DataFrame appended as new page (if any)
    # -------------------
    if supporting_df is not None and not supporting_df.empty:
        story.append(PageBreak())
        story.append(Paragraph("Supporting Documents / Excel data", styles['Heading2']))
        df = supporting_df.fillna("").astype(str)
        # convert DF to table safely in chunks if large
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

    # Build document
    doc.build(story)
    return path
