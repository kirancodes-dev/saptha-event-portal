#!/usr/bin/env python3
"""
generate_snpsu_proposal_docx.py
Generates a formal, professional Microsoft Word (.docx) proposal and requisition document
for Sapthagiri NPS University (SNPSU) - Department of Computer Science & Engineering (CSE).

Fully editable by the user in Microsoft Word, Google Docs, Apple Pages, or LibreOffice.
"""

import os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
DOCX_PATH = os.path.join(REPORT_DIR, "SapthaEvent_SNPSU_CSE_Proposal.docx")
LOGO_PATH = os.path.join(BASE_DIR, "static", "images", "logo.png")


def set_cell_background(cell, fill_hex):
    """Set the background color of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set internal cell margins (padding) in dxa."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)


def set_table_borders(table, color="CCCCCC", sz="4", val="single"):
    """Apply subtle borders to a table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def format_table_header(row, col_widths=None):
    """Format the header row of a table."""
    for i, cell in enumerate(row.cells):
        set_cell_background(cell, "EAEAEA")
        set_cell_margins(cell, top=120, bottom=120, left=160, right=160)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        if col_widths and i < len(col_widths):
            cell.width = col_widths[i]
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            for r in p.runs:
                r.bold = True
                r.font.name = "Calibri"
                r.font.size = Pt(9.5)
                r.font.color.rgb = RGBColor(17, 17, 17)


def format_table_rows(table, col_widths=None):
    """Format data rows in a table with alternating fills and clean padding."""
    for r_idx, row in enumerate(table.rows[1:], start=1):
        bg = "FBFBFB" if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, cell in enumerate(row.cells):
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=100, bottom=100, left=150, right=150)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if col_widths and c_idx < len(col_widths):
                cell.width = col_widths[c_idx]
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                for r in p.runs:
                    r.font.name = "Calibri"
                    r.font.size = Pt(9.5)
                    r.font.color.rgb = RGBColor(34, 34, 34)


def add_section_heading(doc, text):
    """Add a professional section heading with an underline/rule."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.name = "Calibri"
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(17, 17, 17)


def add_body_p(doc, text, bold_prefix=None, space_after=6):
    """Add standard body paragraph."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.bold = True
        r_pre.font.name = "Calibri"
        r_pre.font.size = Pt(10)
        r_pre.font.color.rgb = RGBColor(20, 20, 20)
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(34, 34, 34)
    return p


def build_docx():
    print(f"Creating Word Document (.docx): {DOCX_PATH}")
    doc = Document()

    # Page Margins (1 inch everywhere)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    # -------------------------------------------------------------
    # PAGE 1: COVERING LETTER (TRANSMITTAL LETTER)
    # -------------------------------------------------------------

    # Institution Letterhead Header
    p_header = doc.add_paragraph()
    p_header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_header.paragraph_format.space_after = Pt(2)

    if os.path.exists(LOGO_PATH):
        try:
            p_logo = doc.add_paragraph()
            p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_logo.paragraph_format.space_after = Pt(4)
            p_logo.add_run().add_picture(LOGO_PATH, width=Inches(2.5))
        except Exception:
            pass

    r_inst = p_header.add_run("SAPTHAGIRI NPS UNIVERSITY\n")
    r_inst.bold = True
    r_inst.font.name = "Calibri"
    r_inst.font.size = Pt(15)
    r_inst.font.color.rgb = RGBColor(17, 17, 17)

    r_sub = p_header.add_run("DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING (CSE) • TEAM INNOVEDGE\n")
    r_sub.bold = True
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(10)
    r_sub.font.color.rgb = RGBColor(50, 50, 50)

    r_addr = p_header.add_run("Chikkasandra, Hesaraghatta Main Road, Bengaluru, Karnataka 560057")
    r_addr.font.name = "Calibri"
    r_addr.font.size = Pt(9)
    r_addr.font.color.rgb = RGBColor(80, 80, 80)

    # Horizontal divider rule
    p_div = doc.add_paragraph()
    p_div.paragraph_format.space_before = Pt(4)
    p_div.paragraph_format.space_after = Pt(8)
    p_div_border = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="12" w:space="1" w:color="222222"/></w:pBdr>')
    p_div._p.get_or_add_pPr().append(p_div_border)

    # Date
    p_date = doc.add_paragraph()
    p_date.paragraph_format.space_after = Pt(8)
    r_date = p_date.add_run("Date: 08 October 2026")
    r_date.bold = True
    r_date.font.size = Pt(10)

    # TO and FROM Table (Two Columns)
    tbl_tofrom = doc.add_table(rows=1, cols=2)
    tbl_tofrom.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w = [Inches(3.3), Inches(3.6)]

    cell_to = tbl_tofrom.rows[0].cells[0]
    cell_from = tbl_tofrom.rows[0].cells[1]
    cell_to.width = col_w[0]
    cell_from.width = col_w[1]
    set_cell_margins(cell_to, top=60, bottom=60, left=60, right=60)
    set_cell_margins(cell_from, top=60, bottom=60, left=60, right=60)

    p_to = cell_to.paragraphs[0]
    p_to.paragraph_format.line_spacing = 1.15
    p_to.paragraph_format.space_after = Pt(0)
    r = p_to.add_run("TO:\n")
    r.bold = True
    r.font.size = Pt(10)
    p_to.add_run(
        "The Dean & University Administration,\n"
        "Through: The Director & Faculty Mentor,\n"
        "Department of Computer Science & Engineering (CSE),\n"
        "Sapthagiri NPS University (SNPSU), Bengaluru – 560057"
    ).font.size = Pt(9.5)

    p_from = cell_from.paragraphs[0]
    p_from.paragraph_format.line_spacing = 1.15
    p_from.paragraph_format.space_after = Pt(0)
    r = p_from.add_run("FROM:\n")
    r.bold = True
    r.font.size = Pt(10)
    p_from.add_run(
        "Team InnovEdge (Dept. of Computer Science & Engineering):\n"
        "• Kiran M. Biradar (USN: 24SUUBECS0937) – Lead Developer & Architect\n"
        "• Karthik P. (USN: 24SUUBECS0890) – Co-Lead & Technical Coordinator\n"
        "Under the Guidance of: Faculty Mentor, Dept. of CSE, SNPSU"
    ).font.size = Pt(9.5)

    # Subject Line
    p_subj = doc.add_paragraph()
    p_subj.paragraph_format.space_before = Pt(10)
    p_subj.paragraph_format.space_after = Pt(8)
    r_sub_lbl = p_subj.add_run("SUBJECT: ")
    r_sub_lbl.bold = True
    r_sub_lbl.font.size = Pt(10)
    r_sub_txt = p_subj.add_run(
        "Requisition for Dedicated Server Space, Sub-Domain Provisioning, "
        "and Institutional Deployment Clearance for the 'SapthaEvent' University Management Platform."
    )
    r_sub_txt.bold = True
    r_sub_txt.font.size = Pt(10)

    # Salutation
    p_sal = doc.add_paragraph()
    p_sal.paragraph_format.space_after = Pt(6)
    p_sal.add_run("Respected Dignitaries and Respected Faculty Authorities,").font.size = Pt(10)

    # Paragraphs of Covering Letter
    add_body_p(
        doc,
        "We, the student engineering leads of Team InnovEdge from the Department of Computer Science & Engineering, "
        "respectfully submit this official covering letter and requisition dossier for your review and administrative sanction."
    )

    add_body_p(
        doc,
        "As the university dignitaries will recall, an initial prototype of the campus event portal was launched during "
        "the Legacy 2025 university festival. While the initiative demonstrated the strong campus need for a digital system, "
        "our team acknowledges with utmost professional humility and regret the operational friction encountered during that event—including "
        "server latency under concurrent loads, gate roll-call delays, and synchronization bottlenecks. We took those challenges as a profound learning mandate.",
        bold_prefix="Context & Reflection on Legacy 2025: "
    )

    add_body_p(
        doc,
        "Over the past months, under the guidance of our Faculty Mentor in the Department of CSE, Team InnovEdge has completely "
        "rebuilt, re-engineered, and hardened the entire codebase from the foundation up. We are proud to report that SapthaEvent is now fully done, "
        "hardened, and 100% operational, having passed 145/145 industrial automated test suites. All past bottlenecks have been decisively solved: "
        "sub-second QR code ticket scanning with offline redundancy, dynamic department form builder, ACID-compliant database integrity, zero data loss, "
        "tamper-proof cryptographic certificates, and automatic NAAC/NIRF reporting.",
        bold_prefix="Complete Architectural Overhaul & Current State: "
    )

    add_body_p(doc, "Specific Requisitions Submitted for Administrative Approval:", bold_prefix=None, space_after=2)

    reqs = [
        ("1. Requisition for Dedicated Server Space: ", "We request allocation of dedicated server space (on-premise university server or lightweight cloud container compute) to host the production instance with zero downtime."),
        ("2. Official Sub-Domain Allocation: ", "Authorization to configure the official institutional sub-domain (events.snpsu.edu.in) with SSL intranet/internet routing for official branding."),
        ("3. Departmental Pilot Clearance: ", "Formal sanction to pilot the upgraded platform for upcoming events across the Department of CSE and all academic faculties of Sapthagiri NPS University."),
        ("4. Faculty Mentor & Departmental Endorsement: ", "Direction and backing from our Faculty Mentor and Director of CSE to onboard departmental coordinators and student volunteers.")
    ]
    for bold_txt, norm_txt in reqs:
        p_item = doc.add_paragraph()
        p_item.paragraph_format.left_indent = Inches(0.2)
        p_item.paragraph_format.space_after = Pt(3)
        r_b = p_item.add_run(bold_txt)
        r_b.bold = True
        r_b.font.size = Pt(9.5)
        r_n = p_item.add_run(norm_txt)
        r_n.font.size = Pt(9.5)

    add_body_p(
        doc,
        "The software entails zero commercial software licensing cost for Sapthagiri NPS University and is ready for immediate deployment. "
        "We humbly request the Director, Dean, and Registrar to grant favorable sanction."
    )

    p_yours = doc.add_paragraph()
    p_yours.paragraph_format.space_before = Pt(4)
    p_yours.paragraph_format.space_after = Pt(16)
    p_yours.add_run("Yours faithfully,").font.size = Pt(10)

    # Signatures Table
    tbl_sigs = doc.add_table(rows=1, cols=3)
    tbl_sigs.alignment = WD_TABLE_ALIGNMENT.CENTER
    sig_w = [Inches(2.3), Inches(2.3), Inches(2.3)]
    for i, c in enumerate(tbl_sigs.rows[0].cells):
        c.width = sig_w[i]
        set_cell_margins(c, top=40, bottom=40, left=40, right=40)

    p_sig1 = tbl_sigs.rows[0].cells[0].paragraphs[0]
    p_sig1.add_run("________________________\n").bold = True
    p_sig1.add_run("Kiran M. Biradar\n").bold = True
    p_sig1.add_run("Lead Developer • USN: 24SUUBECS0937\nTeam InnovEdge, Dept. of CSE").font.size = Pt(8.5)

    p_sig2 = tbl_sigs.rows[0].cells[1].paragraphs[0]
    p_sig2.add_run("________________________\n").bold = True
    p_sig2.add_run("Karthik P.\n").bold = True
    p_sig2.add_run("Co-Lead • USN: 24SUUBECS0890\nTeam InnovEdge, Dept. of CSE").font.size = Pt(8.5)

    p_sig3 = tbl_sigs.rows[0].cells[2].paragraphs[0]
    p_sig3.add_run("________________________\n").bold = True
    p_sig3.add_run("Faculty Mentor\n").bold = True
    p_sig3.add_run("Dept. of Computer Science & Engg.\nSapthagiri NPS University").font.size = Pt(8.5)

    # PAGE BREAK TO PAGE 2 (COVER PAGE)
    doc.add_page_break()

    # -------------------------------------------------------------
    # PAGE 2: OFFICIAL COVER PAGE & APPROVAL MATRIX
    # -------------------------------------------------------------
    p_cp_hdr = doc.add_paragraph()
    p_cp_hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cp_hdr.paragraph_format.space_before = Pt(12)
    p_cp_hdr.paragraph_format.space_after = Pt(2)

    if os.path.exists(LOGO_PATH):
        try:
            p_cp_logo = doc.add_paragraph()
            p_cp_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_cp_logo.paragraph_format.space_after = Pt(6)
            p_cp_logo.add_run().add_picture(LOGO_PATH, width=Inches(2.6))
        except Exception:
            pass

    r = p_cp_hdr.add_run("SAPTHAGIRI NPS UNIVERSITY\n")
    r.bold = True
    r.font.name = "Calibri"
    r.font.size = Pt(18)
    r.font.color.rgb = RGBColor(17, 17, 17)

    r = p_cp_hdr.add_run("Chikkasandra, Hesaraghatta Main Road, Bengaluru, Karnataka 560057\n")
    r.font.size = Pt(9.5)
    r.font.color.rgb = RGBColor(80, 80, 80)

    r = p_cp_hdr.add_run("DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING (CSE)\n")
    r.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(40, 40, 40)

    r = p_cp_hdr.add_run("Team InnovEdge • Student Technical & Software Development Council")
    r.font.size = Pt(9.5)
    r.font.color.rgb = RGBColor(60, 60, 60)

    # Horizontal divider rule
    p_cp_div = doc.add_paragraph()
    p_cp_div.paragraph_format.space_before = Pt(6)
    p_cp_div.paragraph_format.space_after = Pt(14)
    p_cp_border = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="16" w:space="1" w:color="111111"/></w:pBdr>')
    p_cp_div._p.get_or_add_pPr().append(p_cp_border)

    p_cp_title = doc.add_paragraph()
    p_cp_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cp_title.paragraph_format.space_after = Pt(6)
    r = p_cp_title.add_run("OFFICIAL PROJECT PROPOSAL & INSTITUTIONAL REQUISITION")
    r.bold = True
    r.font.size = Pt(17)
    r.font.color.rgb = RGBColor(17, 17, 17)

    p_cp_sub = doc.add_paragraph()
    p_cp_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cp_sub.paragraph_format.space_after = Pt(16)
    r = p_cp_sub.add_run(
        "Comprehensive Strategic Blueprint, Architecture, and Operational Documentation "
        "for Deployment of the SapthaEvent Campus Event Intelligence & Orchestration Platform"
    )
    r.font.size = Pt(10.5)
    r.font.color.rgb = RGBColor(70, 70, 70)

    # Metadata Table (No Security Level, No Reference ID, No Submission Date)
    meta_data = [
        ("DOCUMENT TITLE", "Institutional Project Proposal & Server Space Requisition"),
        ("PROJECT NAME", "SapthaEvent — Enterprise Event Intelligence Platform"),
        ("ACADEMIC SESSION", "Academic Year 2026 – 2027"),
        ("TARGET INSTITUTION", "Sapthagiri NPS University (SNPSU), Bengaluru"),
        ("DEVELOPED BY", "Team InnovEdge • Dept. of Computer Science & Engineering (CSE)"),
        ("PROJECT LEADS", "Kiran M. Biradar (USN: 24SUUBECS0937) • Lead Developer & Architect\nKarthik P. (USN: 24SUUBECS0890) • Co-Lead & Technical Coordinator"),
        ("FACULTY MENTOR", "Faculty Coordinator • Dept. of Computer Science & Engineering"),
        ("SUBMITTED TO", "The Director (CSE), Dean (Engineering), and Registrar, SNPSU"),
        ("PROJECT STATUS", "Production Ready • 145/145 Automated Tests Passing • Fully Functional"),
    ]

    tbl_meta = doc.add_table(rows=len(meta_data), cols=2)
    tbl_meta.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_meta, color="CCCCCC", sz="4")
    col_w_m = [Inches(2.4), Inches(4.5)]

    for row_idx, (k, v) in enumerate(meta_data):
        row = tbl_meta.rows[row_idx]
        row.cells[0].width = col_w_m[0]
        row.cells[1].width = col_w_m[1]
        set_cell_background(row.cells[0], "F5F5F5")
        set_cell_background(row.cells[1], "FFFFFF")
        set_cell_margins(row.cells[0], top=80, bottom=80, left=120, right=120)
        set_cell_margins(row.cells[1], top=80, bottom=80, left=120, right=120)

        p0 = row.cells[0].paragraphs[0]
        p0.paragraph_format.space_after = Pt(0)
        r0 = p0.add_run(k)
        r0.bold = True
        r0.font.size = Pt(8.5)
        r0.font.color.rgb = RGBColor(40, 40, 40)

        p1 = row.cells[1].paragraphs[0]
        p1.paragraph_format.space_after = Pt(0)
        p1.paragraph_format.line_spacing = 1.15
        r1 = p1.add_run(v)
        r1.font.size = Pt(9)
        r1.font.color.rgb = RGBColor(20, 20, 20)

    # Institutional Approval Matrix
    p_app_lbl = doc.add_paragraph()
    p_app_lbl.paragraph_format.space_before = Pt(14)
    p_app_lbl.paragraph_format.space_after = Pt(4)
    r = p_app_lbl.add_run("INSTITUTIONAL ENDORSEMENT & APPROVAL MATRIX")
    r.bold = True
    r.font.size = Pt(10)

    approval_headers = ["SUBMITTED BY", "RECOMMENDED BY", "ENDORSED BY", "FINAL SANCTION"]
    approval_subheaders = ["Team InnovEdge Leads", "Director, School of CSE", "Dean, Academic Affairs / Engg.", "Registrar, SNPSU"]
    approval_bodies = [
        "\n\n________________________\nKiran M. Biradar\nKarthik P.\nTeam InnovEdge (CSE)",
        "\n\n________________________\nDirector\nDept. of Computer Science & Engg.\nSapthagiri NPS University",
        "\n\n________________________\nDean\nFaculty of Engineering & Tech.\nSapthagiri NPS University",
        "\n\n________________________\nRegistrar\nUniversity Administration\nSapthagiri NPS University"
    ]

    tbl_app = doc.add_table(rows=2, cols=4)
    tbl_app.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_app, color="BBBBBB", sz="4")
    col_w_a = [Inches(1.725)] * 4

    # Header Row
    for i in range(4):
        c = tbl_app.rows[0].cells[i]
        c.width = col_w_a[i]
        set_cell_background(c, "EBEBEB")
        set_cell_margins(c, top=80, bottom=80, left=60, right=60)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(f"{approval_headers[i]}\n")
        r.bold = True
        r.font.size = Pt(8.5)
        r_sub = p.add_run(approval_subheaders[i])
        r_sub.font.size = Pt(7.5)
        r_sub.font.color.rgb = RGBColor(60, 60, 60)

    # Body Row
    for i in range(4):
        c = tbl_app.rows[1].cells[i]
        c.width = col_w_a[i]
        set_cell_background(c, "FFFFFF")
        set_cell_margins(c, top=100, bottom=100, left=60, right=60)
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.1
        r = p.add_run(approval_bodies[i])
        r.font.size = Pt(8)

    # PAGE BREAK TO PROPOSAL BODY
    doc.add_page_break()

    # -------------------------------------------------------------
    # SECTION 1: EXECUTIVE SUMMARY & PROJECT STATEMENT
    # -------------------------------------------------------------
    add_section_heading(doc, "1. EXECUTIVE SUMMARY & PROJECT STATEMENT")
    add_body_p(
        doc,
        "SapthaEvent is an enterprise-grade university event orchestration, ticketing, dynamic registration, "
        "and data intelligence platform developed indigenously by Team InnovEdge within the Department of Computer Science & Engineering (CSE) "
        "at Sapthagiri NPS University (SNPSU). The platform addresses the persistent administrative challenges of manual paper-based registrations, "
        "unreliable third-party Google Forms, gate crowd congestion, lost revenue tracking, and chaotic accreditation reporting."
    )
    add_body_p(
        doc,
        "Designed to serve as the unified institutional digital backbone for all collegiate cultural, technical, sports, and academic symposiums, "
        "SapthaEvent consolidates the complete event lifecycle into a single secure ecosystem—from role-isolated department form configuration, "
        "instant QR code ticket generation, and automated gate validation to cryptographic certificate issuance and instant NAAC/NIRF accreditation analytics."
    )

    # Metrics Table
    metrics_data = [
        ["METRIC / CAPABILITY", "SPECIFICATION / ACHIEVEMENT", "INSTITUTIONAL VALUE"],
        ["Test Suite Verification", "145 / 145 Passing Automated Tests", "100% regression and security resilience"],
        ["Gate Roll-Call Speed", "< 0.4 seconds per QR scan", "Eliminates gate queues during mega-fests"],
        ["Accreditation Turnaround", "Instant NAAC Criteria 5.3 Export", "Automates weeks of administrative data collation"],
        ["Commercial Software Cost", "INR 0 (Indigenous Asset)", "100% cost reduction vs commercial SaaS"],
        ["Offline Check-in Redundancy", "Offline-ready token verification", "Uninterrupted gate operations during Wi-Fi outages"]
    ]
    tbl_met = doc.add_table(rows=len(metrics_data), cols=3)
    tbl_met.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_met)
    col_w_m = [Inches(2.0), Inches(2.5), Inches(2.4)]
    format_table_header(tbl_met.rows[0], col_w_m)
    for row_idx, row_vals in enumerate(metrics_data):
        for col_idx, val in enumerate(row_vals):
            tbl_met.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_met.rows[0], col_w_m)
    format_table_rows(tbl_met, col_w_m)

    # -------------------------------------------------------------
    # SECTION 2: INSTITUTIONAL PROBLEM STATEMENT
    # -------------------------------------------------------------
    add_section_heading(doc, "2. INSTITUTIONAL PROBLEM STATEMENT & GROUND-REALITY ANALYSIS")
    add_body_p(
        doc,
        "Collegiate events at Sapthagiri NPS University are high-stakes operational environments involving thousands of students, external participants, "
        "faculty judges, and substantial financial transactions. Prior to SapthaEvent, campus event administration suffered from fragmented, ad-hoc workflows:"
    )

    problems = [
        ["OPERATIONAL AREA", "CURRENT CONVENTIONAL WORKFLOW", "SAPTHAEVENT OVERHAULED SOLUTION"],
        ["Registration & Intake", "Fragmented Google Forms per department; missing payment slips; fake UTRs.", "Integrated dynamic builder with field validation and automated payment slip hashing."],
        ["Gate Access & Check-In", "Manual paper printouts; slow name cross-referencing; gate bottlenecking.", "Sub-second camera QR scan with instant live roll-call and offline fallback."],
        ["Data Privacy & Security", "Student phone numbers and PII exposed on shared volunteer spreadsheets.", "Strict Role-Based Access Control (RBAC); hashed tokens; volunteer PII masking."],
        ["Accreditation Audit", "Months spent manually collecting attendee lists and photos for NAAC files.", "One-click NAAC Criteria 5.3 and NIRF audit reports generated in vector PDF/Excel."],
        ["Certificate Issuance", "Manual mail-merge certificate creation leading to misspelled names and fraud.", "Cryptographic tamper-proof digital certificates verifiable via permanent public QR."]
    ]
    tbl_prob = doc.add_table(rows=len(problems), cols=3)
    tbl_prob.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_prob)
    col_w_p = [Inches(1.8), Inches(2.5), Inches(2.6)]
    for row_idx, row_vals in enumerate(problems):
        for col_idx, val in enumerate(row_vals):
            tbl_prob.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_prob.rows[0], col_w_p)
    format_table_rows(tbl_prob, col_w_p)

    # -------------------------------------------------------------
    # SECTION 3: SOLUTION ARCHITECTURE & CORE MODULES
    # -------------------------------------------------------------
    add_section_heading(doc, "3. THE SAPTHAEVENT SOLUTION ARCHITECTURE")
    add_body_p(
        doc,
        "SapthaEvent is structured into five cohesive, high-performance software modules designed to cover the institutional event workflow end-to-end:"
    )

    modules = [
        ("Module 1: Dynamic Departmental Form Builder — ", "Allows faculty coordinators and student leads across any university department to construct tailored registration questionnaires without writing code. Supports custom text, dropdowns, file uploads, team member matrices, and conditional fields."),
        ("Module 2: Sub-Second QR Ticketing & Check-In — ", "Upon confirmed registration, participants instantly receive a cryptographic ticket embedded with a unique verification token and dynamic QR code. Gate volunteers scan tickets via smartphone camera with sub-second feedback."),
        ("Module 3: Role-Based Access Control (RBAC) & Multi-Tenant Isolation — ", "Implements strict security boundaries isolating Super Admin, Department Director, Faculty Coordinator, and Student Volunteer access levels."),
        ("Module 4: NAAC & NIRF Compliant Reporting Engine — ", "Automatically aggregates gender demographics, departmental participation percentages, geo-diversity, and verified attendance ratios into standardized accreditation reports."),
        ("Module 5: Tamper-Proof Cryptographic Certificate Studio — ", "Generates vector-grade participation and merit certificates in bulk with embedded public verification URLs and digital signatures.")
    ]
    for b_title, b_desc in modules:
        add_body_p(doc, b_desc, bold_prefix=b_title, space_after=4)

    # -------------------------------------------------------------
    # SECTION 4: OPERATIONAL WORKFLOW & LIFECYCLE
    # -------------------------------------------------------------
    add_section_heading(doc, "4. OPERATIONAL WORKFLOW & EVENT LIFECYCLE")

    workflow_steps = [
        ["PHASE", "PRIMARY ACTOR", "ACTIONS & PLATFORM BEHAVIOR", "SECURITY & INTEGRITY ASSURANCE"],
        ["1. Creation & Publishing", "Faculty Coordinator / Lead", "Configures event rules, team sizes, deadlines, custom forms, and pricing tiers.", "Requires departmental authorization; changes audit-logged."],
        ["2. Registration & Intake", "Student / External Attendee", "Fills validated form fields; uploads payment reference or executes checkout; receives digital ticket.", "Prevents duplicate submissions, verifies UTR formats, reserves seat locks."],
        ["3. Day-of-Event Check-in", "Gate Volunteer / Staff", "Scans attendee QR via camera; receives instant visual confirmation; marks attendee present.", "Detects re-used or counterfeit tickets; syncs with offline roll-call storage."],
        ["4. Post-Event & Reporting", "Director / IQAC Coordinator", "One-click generation of NAAC Criteria 5.3 PDF reports, attendance rosters, and merit certificates.", "Digitally signed certificates; tamper-proof public verification."]
    ]
    tbl_wf = doc.add_table(rows=len(workflow_steps), cols=4)
    tbl_wf.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_wf)
    col_w_wf = [Inches(1.4), Inches(1.5), Inches(2.5), Inches(1.5)]
    for row_idx, row_vals in enumerate(workflow_steps):
        for col_idx, val in enumerate(row_vals):
            tbl_wf.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_wf.rows[0], col_w_wf)
    format_table_rows(tbl_wf, col_w_wf)

    # -------------------------------------------------------------
    # SECTION 5: TECHNICAL ARCHITECTURE & SECURITY
    # -------------------------------------------------------------
    add_section_heading(doc, "5. TECHNICAL ARCHITECTURE, SECURITY & DATA GOVERNANCE")
    add_body_p(
        doc,
        "SapthaEvent is engineered as a robust, production-ready enterprise application compliant with industry software engineering standards, "
        "data privacy laws, and academic institutional security requirements."
    )

    tech_specs = [
        ["ARCHITECTURAL LAYER", "TECHNOLOGY SELECTION", "SPECIFICATIONS & INSTITUTIONAL ADVANTAGE"],
        ["Backend Core", "Python 3.11 / Flask 3.x", "Lightweight WSGI framework, microservices-ready, minimal server memory footprint (< 150 MB)."],
        ["Database Layer", "PostgreSQL (SQLAlchemy ORM)", "ACID-compliant relational storage. Includes local zero-config SQLite fallback for disaster recovery and offline continuity."],
        ["Document Engine", "ReportLab High-Speed Generator", "Vector-grade PDF rendering engine capable of compiling thousands of certificates and reports in seconds."],
        ["Security & CSRF", "Flask-WTF & Talisman Middleware", "Enforces strict CSRF token validation on all mutating POST requests, secure HTTP headers (CSP, HSTS, X-Frame-Options)."],
        ["Authentication", "PBKDF2-SHA256 & Session Guard", "Cryptographic password hashing, secure HttpOnly/SameSite cookies, brute-force rate-limiting on login endpoints."],
        ["Data Privacy", "Role-Isolated PII Protection", "Participant phone numbers and personal data are strictly masked from unauthorized volunteers and external attendees."],
        ["Quality Assurance", "Automated Pytest Suite", "145 comprehensive automated tests passing with 100% verification across security, payments, ticketing, and scheduling."]
    ]
    tbl_tech = doc.add_table(rows=len(tech_specs), cols=3)
    tbl_tech.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_tech)
    col_w_t = [Inches(1.8), Inches(2.2), Inches(2.9)]
    for row_idx, row_vals in enumerate(tech_specs):
        for col_idx, val in enumerate(row_vals):
            tbl_tech.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_tech.rows[0], col_w_t)
    format_table_rows(tbl_tech, col_w_t)

    # -------------------------------------------------------------
    # SECTION 6: INFRASTRUCTURE & HOSTING COST FEASIBILITY FOR SNPSU
    # -------------------------------------------------------------
    add_section_heading(doc, "6. INFRASTRUCTURE & HOSTING COST FEASIBILITY FOR SNPSU")
    add_body_p(
        doc,
        "Because SapthaEvent is an indigenous asset engineered by Team InnovEdge, there are zero commercial software licensing fees. "
        "The financial requirements are strictly limited to the minimal server space and compute required to store and handle the data "
        "and event operations for Sapthagiri NPS University (SNPSU) alone (~5,000–8,000 students across all departments)."
    )

    cost_data = [
        ["OPERATIONAL RESOURCE", "COMMERCIAL SAAS (EVENTBRITE/VFAIRS)", "SAPTHAEVENT FOR SNPSU", "INSTITUTIONAL SAVINGS"],
        ["Platform Software License", "INR 2,50,000 – INR 5,00,000 / year", "INR 0 (Developed In-House by InnovEdge)", "100% Software License Saved"],
        ["Per-Registration Commission", "3% to 7% cut on all paid registrations", "INR 0 (Zero platform cut for SNPSU)", "100% Event Funds Retained"],
        ["Server Space & Compute", "Billed as part of costly enterprise tiers", "Minimal Campus Server / Cloud (~INR 400/mo)", "Negligible Operational Expense"],
        ["Database Storage (SNPSU Data)", "Hosted externally on vendor clouds", "Local / Managed SQL (~300MB for SNPSU)", "100% Student Privacy & Sovereignty"],
        ["Certificate Generation", "Third-party add-on (INR 5 – 10 / cert)", "Unlimited Vector PDF Engine Included", "INR 50,000+ saved on certificate printing"]
    ]
    tbl_cost = doc.add_table(rows=len(cost_data), cols=4)
    tbl_cost.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_cost)
    col_w_c = [Inches(1.8), Inches(2.0), Inches(1.8), Inches(1.3)]
    for row_idx, row_vals in enumerate(cost_data):
        for col_idx, val in enumerate(row_vals):
            tbl_cost.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_cost.rows[0], col_w_c)
    format_table_rows(tbl_cost, col_w_c)

    add_body_p(
        doc,
        "Summary for SNPSU Administration: Deploying SapthaEvent saves the university an estimated INR 2,50,000 to INR 5,00,000 annually "
        "compared to external event platforms. The total infrastructure cost to run the system across all departments of SNPSU is negligible "
        "(under INR 5,000 annually or INR 0 if hosted on internal campus servers).",
        space_after=8
    )

    # -------------------------------------------------------------
    # SECTION 7: ROLLOUT ROADMAP & REQUISITION
    # -------------------------------------------------------------
    add_section_heading(doc, "7. ROLLOUT ROADMAP, DEPARTMENTAL PILOT & REQUISITION")
    add_body_p(
        doc,
        "To ensure a seamless, zero-friction transition, Team InnovEdge proposes a phased 4-stage implementation schedule for Sapthagiri NPS University:"
    )

    roadmap = [
        ["PHASE", "TIMELINE", "OPERATIONAL FOCUS & DELIVERABLES", "STAKEHOLDERS INVOLVED"],
        ["Phase I: Infrastructure", "Week 1", "Server provisioning, domain binding (events.snpsu.edu.in), SSL certification, and test deployment.", "InnovEdge Technical Leads & University IT / Server Admin"],
        ["Phase II: Department Pilot", "Weeks 2 – 3", "Pilot rollout for CSE department technical competitions and workshops; coordinator onboarding.", "Faculty Mentor, Dept. of CSE Faculty & Student Leads"],
        ["Phase III: Campus Rollout", "Weeks 4 – 5", "Expansion to all university academic faculties (Management, Commerce, Basic Sciences, Humanities).", "Director (CSE), Deans of Faculties, Institutional Coordinators"],
        ["Phase IV: Mega-Fest Scale", "Annual Fests", "Full concurrent scale operations for university inter-collegiate festivals with high-volume scanning.", "University Event Committees, Student Councils & Volunteers"]
    ]
    tbl_road = doc.add_table(rows=len(roadmap), cols=4)
    tbl_road.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_road)
    col_w_r = [Inches(1.4), Inches(1.0), Inches(2.8), Inches(1.7)]
    for row_idx, row_vals in enumerate(roadmap):
        for col_idx, val in enumerate(row_vals):
            tbl_road.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_road.rows[0], col_w_r)
    format_table_rows(tbl_road, col_w_r)

    # Requisition Details Table
    p_req_tbl_lbl = doc.add_paragraph()
    p_req_tbl_lbl.paragraph_format.space_before = Pt(8)
    p_req_tbl_lbl.paragraph_format.space_after = Pt(4)
    r = p_req_tbl_lbl.add_run("Actionable Administrative Requisitions for Immediate Sanction:")
    r.bold = True
    r.font.size = Pt(10)

    requisition_items = [
        ["REQUISITION ITEM", "SPECIFICATION / REQUIREMENT", "ADMINISTRATIVE ACTION REQUIRED"],
        ["1. Dedicated Server Space", "Allocation of 2 vCPU, 4GB RAM virtual machine or campus intranet server slot.", "Sanction by IT Administrator / Registrar"],
        ["2. Sub-Domain Mapping", "DNS mapping for events.snpsu.edu.in with SSL certificate binding.", "IT Network Division authorization"],
        ["3. Departmental Pilot Approval", "Clearance to conduct real-world student registrations for upcoming CSE department events.", "Sanction by Director (CSE) & Faculty Mentor"],
        ["4. IQAC / NAAC Endorsement", "Official authorization to standardize accreditation report formats with IQAC cell.", "Endorsement by Dean (Academic Affairs)"]
    ]
    tbl_req_act = doc.add_table(rows=len(requisition_items), cols=3)
    tbl_req_act.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(tbl_req_act)
    col_w_ra = [Inches(1.8), Inches(2.9), Inches(2.2)]
    for row_idx, row_vals in enumerate(requisition_items):
        for col_idx, val in enumerate(row_vals):
            tbl_req_act.rows[row_idx].cells[col_idx].paragraphs[0].text = val
    format_table_header(tbl_req_act.rows[0], col_w_ra)
    format_table_rows(tbl_req_act, col_w_ra)

    # -------------------------------------------------------------
    # SECTION 8: INSTITUTIONAL DECLARATION & ENDORSEMENTS
    # -------------------------------------------------------------
    add_section_heading(doc, "8. INSTITUTIONAL DECLARATION & ENDORSEMENT SIGNATURES")
    add_body_p(
        doc,
        "We hereby declare that the SapthaEvent platform has been architected and developed with adherence to academic integrity, "
        "strict data privacy standards, and robust software engineering best practices. We affirm that all functional components "
        "have passed automated regression testing and that the system is fully operational and production-ready for deployment at Sapthagiri NPS University.",
        space_after=14
    )

    # Endorsement Signatures Table
    tbl_endors = doc.add_table(rows=1, cols=4)
    tbl_endors.alignment = WD_TABLE_ALIGNMENT.CENTER
    col_w_e = [Inches(1.725)] * 4
    for i, c in enumerate(tbl_endors.rows[0].cells):
        c.width = col_w_e[i]
        set_cell_margins(c, top=60, bottom=60, left=40, right=40)

    p_e1 = tbl_endors.rows[0].cells[0].paragraphs[0]
    p_e1.add_run("________________________\n").bold = True
    p_e1.add_run("Kiran M. Biradar\n").bold = True
    p_e1.add_run("Lead Developer & Architect\nUSN: 24SUUBECS0937\nTeam InnovEdge (CSE)").font.size = Pt(8)

    p_e2 = tbl_endors.rows[0].cells[1].paragraphs[0]
    p_e2.add_run("________________________\n").bold = True
    p_e2.add_run("Karthik P.\n").bold = True
    p_e2.add_run("Co-Lead & Tech Coordinator\nUSN: 24SUUBECS0890\nTeam InnovEdge (CSE)").font.size = Pt(8)

    p_e3 = tbl_endors.rows[0].cells[2].paragraphs[0]
    p_e3.add_run("________________________\n").bold = True
    p_e3.add_run("Director\n").bold = True
    p_e3.add_run("Dept. of Computer Science & Engg.\nSapthagiri NPS University").font.size = Pt(8)

    p_e4 = tbl_endors.rows[0].cells[3].paragraphs[0]
    p_e4.add_run("________________________\n").bold = True
    p_e4.add_run("Dean / Registrar\n").bold = True
    p_e4.add_run("University Administration\nSapthagiri NPS University").font.size = Pt(8)

    # Save document
    doc.save(DOCX_PATH)
    print(f"SUCCESS: Word Document created successfully at: {DOCX_PATH}")


if __name__ == "__main__":
    build_docx()
