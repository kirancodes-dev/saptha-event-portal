#!/usr/bin/env python3
"""
generate_hrd_proposal.py — Generates a formal, professional, monochrome (no-color)
institutional project proposal, official covering letter, server requisition,
and strategic documentation for Sapthagiri NPS University (SNPSU).

Structure:
- Page 1: Official Covering Letter (Transmittal & Requisition Letter: To, From, Subject,
          Legacy 2025 context, Team InnovEdge, Kiran M. Biradar & Karthik P., Server Space Requisition)
- Page 2: Formal Cover Page (SNPSU, CSE Dept, Team InnovEdge, Updated Approval Matrix: Director, Dean, Registrar)
- Page 3: Section 1 (Executive Summary) & Section 2 (The Problem: Why We Built It & Legacy Evolution)
- Page 4: Section 3 (System Architecture & 7-Phase End-to-End Lifecycle Blueprint)
- Page 5: Section 4 (Core Functional Modules & Stakeholder Privilege Matrix)
- Page 6: Section 5 (Technical Specifications & Security) & Section 6 (SNPSU-Specific Server & Hosting Cost Feasibility)
- Page 7: Section 7 (Phased Implementation Roadmap) & Section 8 (Specific Requisitions & Clearances)
- Page 8: Section 9 (Institutional Undertaking) & Section 10 (Formal 4-Stage Approval & Sanction Matrix)

Output: reports/SapthaEvent_HRD_Permission_Proposal.pdf
"""

import os
import datetime

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image
)
from reportlab.pdfgen import canvas

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION & MONOCHROME PALETTE
# ═══════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(REPORT_DIR, "SapthaEvent_HRD_Permission_Proposal.pdf")

ORIG_LOGO_PATH = os.path.join(BASE_DIR, "static", "snpsu-logo.png")
BW_LOGO_PATH = os.path.join(REPORT_DIR, "snpsu-logo-bw.png")

# Ensure clean grayscale monochrome logo exists
if os.path.exists(ORIG_LOGO_PATH):
    try:
        im = PILImage.open(ORIG_LOGO_PATH).convert('L')
        im.save(BW_LOGO_PATH)
    except Exception:
        BW_LOGO_PATH = ORIG_LOGO_PATH

PAGE_WIDTH, PAGE_HEIGHT = A4  # 595.27 x 841.89 pt
MARGIN = 42  # Printable width = 595.27 - 84 = 511.27 pt
PRINTABLE_WIDTH = PAGE_WIDTH - (2 * MARGIN)

# Strict Monochrome Palette (Zero Color)
COLOR_BLACK = colors.black
COLOR_DARK_GRAY = colors.HexColor("#222222")
COLOR_MID_GRAY = colors.HexColor("#555555")
COLOR_BORDER_GRAY = colors.HexColor("#888888")
COLOR_LIGHT_LINE = colors.HexColor("#cccccc")
COLOR_HEADER_BG = colors.HexColor("#eeeeee")
COLOR_ROW_ALT = colors.HexColor("#f8f8f8")
COLOR_WHITE = colors.white

DATE_STR = datetime.datetime.now().strftime("%d %B %Y")
ACADEMIC_YEAR = "2026 – 2027"


# ═══════════════════════════════════════════════════════════════
# NUMBERED CANVAS (Monochrome Running Headers & Footers)
# ═══════════════════════════════════════════════════════════════
class FormalMonochromeCanvas(canvas.Canvas):
    """
    Two-pass canvas to calculate total page count and render
    clean, non-overlapping monochrome institutional headers and footers.
    Page 1 (Covering Letter) and Page 2 (Cover Page) are kept clean.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, total_pages):
        # Suppress running header & footer on Letter (Page 1) and Cover (Page 2)
        if self._pageNumber in (1, 2):
            if self._pageNumber == 2:
                # Draw formal outer page border on cover page
                self.saveState()
                self.setStrokeColor(COLOR_BLACK)
                self.setLineWidth(1.5)
                self.rect(26, 26, PAGE_WIDTH - 52, PAGE_HEIGHT - 52)
                self.setLineWidth(0.5)
                self.rect(29, 29, PAGE_WIDTH - 58, PAGE_HEIGHT - 58)
                self.restoreState()
            return

        self.saveState()
        # Header line & text (Department of CSE & SNPSU)
        self.setStrokeColor(COLOR_BLACK)
        self.setLineWidth(0.8)
        self.line(MARGIN, PAGE_HEIGHT - 38, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 38)

        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(COLOR_BLACK)
        self.drawString(MARGIN, PAGE_HEIGHT - 32, "SAPTHAGIRI NPS UNIVERSITY  |  DEPT. OF COMPUTER SCIENCE & ENGINEERING")
        self.setFont("Helvetica", 7.5)
        self.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 32, "PROJECT PROPOSAL & SERVER REQUISITION")

        # Footer line & text
        self.setStrokeColor(COLOR_BLACK)
        self.setLineWidth(0.8)
        self.line(MARGIN, 40, PAGE_WIDTH - MARGIN, 40)

        self.setFont("Helvetica", 7.5)
        self.drawString(MARGIN, 28, f"TEAM INNOVEDGE  |  ACADEMIC SESSION {ACADEMIC_YEAR}  |  SNPSU")
        self.drawRightString(PAGE_WIDTH - MARGIN, 28, f"Page {self._pageNumber} of {total_pages}")
        self.restoreState()


# ═══════════════════════════════════════════════════════════════
# TYPOGRAPHY & STYLES
# ═══════════════════════════════════════════════════════════════
styles = getSampleStyleSheet()

styles.add(ParagraphStyle("LetterDeptHeader", fontName="Helvetica-Bold", fontSize=12, leading=15,
                          textColor=COLOR_BLACK, alignment=TA_CENTER))
styles.add(ParagraphStyle("LetterUnivSub", fontName="Helvetica", fontSize=9, leading=12.5,
                          textColor=COLOR_DARK_GRAY, alignment=TA_CENTER))

styles.add(ParagraphStyle("CoverUnivTitle", fontName="Helvetica-Bold", fontSize=15, leading=19,
                          textColor=COLOR_BLACK, alignment=TA_CENTER))
styles.add(ParagraphStyle("CoverDeptTitle", fontName="Helvetica", fontSize=9.5, leading=13.5,
                          textColor=COLOR_MID_GRAY, alignment=TA_CENTER))
styles.add(ParagraphStyle("CoverMainTitle", fontName="Helvetica-Bold", fontSize=19, leading=24,
                          textColor=COLOR_BLACK, alignment=TA_CENTER, spaceBefore=12, spaceAfter=8))
styles.add(ParagraphStyle("CoverSubtitle", fontName="Helvetica-Oblique", fontSize=9.5, leading=13.5,
                          textColor=COLOR_DARK_GRAY, alignment=TA_CENTER, spaceAfter=14))

styles.add(ParagraphStyle("DocH1", fontName="Helvetica-Bold", fontSize=11.5, leading=15.5,
                          textColor=COLOR_BLACK, spaceBefore=10, spaceAfter=5, keepWithNext=True))
styles.add(ParagraphStyle("DocH2", fontName="Helvetica-Bold", fontSize=9.5, leading=13,
                          textColor=COLOR_DARK_GRAY, spaceBefore=7, spaceAfter=3, keepWithNext=True))
styles.add(ParagraphStyle("DocH3", fontName="Helvetica-Bold", fontSize=8.5, leading=11.5,
                          textColor=COLOR_DARK_GRAY, spaceBefore=5, spaceAfter=2.5, keepWithNext=True))

styles.add(ParagraphStyle("DocBody", fontName="Helvetica", fontSize=8.5, leading=12,
                          textColor=COLOR_BLACK, alignment=TA_JUSTIFY, spaceAfter=4.5))
styles.add(ParagraphStyle("DocBodyItalic", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
                          textColor=COLOR_DARK_GRAY, alignment=TA_JUSTIFY, spaceAfter=4.5))
styles.add(ParagraphStyle("DocBullet", fontName="Helvetica", fontSize=8.5, leading=12,
                          textColor=COLOR_BLACK, leftIndent=14, bulletIndent=6, spaceAfter=2.5))
styles.add(ParagraphStyle("DocNumbered", fontName="Helvetica", fontSize=8.5, leading=12,
                          textColor=COLOR_BLACK, leftIndent=16, bulletIndent=6, spaceAfter=3))

styles.add(ParagraphStyle("TableHead", fontName="Helvetica-Bold", fontSize=8, leading=10.5,
                          textColor=COLOR_BLACK, alignment=TA_LEFT))
styles.add(ParagraphStyle("TableHeadCenter", fontName="Helvetica-Bold", fontSize=8, leading=10.5,
                          textColor=COLOR_BLACK, alignment=TA_CENTER))
styles.add(ParagraphStyle("TableCell", fontName="Helvetica", fontSize=7.5, leading=10,
                          textColor=COLOR_BLACK, alignment=TA_LEFT))
styles.add(ParagraphStyle("TableCellCenter", fontName="Helvetica", fontSize=7.5, leading=10,
                          textColor=COLOR_BLACK, alignment=TA_CENTER))
styles.add(ParagraphStyle("TableCellBold", fontName="Helvetica-Bold", fontSize=7.5, leading=10,
                          textColor=COLOR_BLACK, alignment=TA_LEFT))

styles.add(ParagraphStyle("LetterToFrom", fontName="Helvetica", fontSize=8.5, leading=12,
                          textColor=COLOR_BLACK))
styles.add(ParagraphStyle("LetterSubject", fontName="Helvetica-Bold", fontSize=9, leading=13,
                          textColor=COLOR_BLACK, spaceBefore=6, spaceAfter=7))


# ═══════════════════════════════════════════════════════════════
# TABLE HELPERS
# ═══════════════════════════════════════════════════════════════
def make_table(data, col_widths, has_header=True):
    """Generates a clean monochrome table with crisp borders and subtle header shading."""
    formatted = []
    for r_idx, row in enumerate(data):
        row_cells = []
        for c_idx, cell in enumerate(row):
            if isinstance(cell, Paragraph):
                row_cells.append(cell)
            else:
                text = str(cell)
                if r_idx == 0 and has_header:
                    p = Paragraph(text, styles["TableHead"])
                else:
                    p = Paragraph(text, styles["TableCell"])
                row_cells.append(p)
        formatted.append(row_cells)

    t = Table(formatted, colWidths=col_widths)
    t_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, COLOR_BLACK),
    ]
    if has_header:
        t_style.append(("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG))
        t_style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_ROW_ALT]))
    else:
        t_style.append(("ROWBACKGROUNDS", (0, 0), (-1, -1), [COLOR_WHITE, COLOR_ROW_ALT]))

    t.setStyle(TableStyle(t_style))
    return t


# ═══════════════════════════════════════════════════════════════
# DOCUMENT STORY BUILDER
# ═══════════════════════════════════════════════════════════════
def build_proposal_story():
    story = []

    # ─────────────────────────────────────────────────────────────
    # PAGE 1: OFFICIAL COVERING LETTER / REQUISITION LETTER
    # (Covering letter is 1st page, NO big title, starts with TO then FROM)
    # ─────────────────────────────────────────────────────────────
    target_logo = BW_LOGO_PATH if os.path.exists(BW_LOGO_PATH) else ORIG_LOGO_PATH
    if os.path.exists(target_logo):
        logo_w = 145
        logo_h = logo_w / (2048 / 703)
        story.append(Image(target_logo, width=logo_w, height=logo_h))
        story.append(Spacer(1, 4))

    story.append(Paragraph("SAPTHAGIRI NPS UNIVERSITY", styles["LetterDeptHeader"]))
    story.append(Paragraph("DEPARTMENT OF COMPUTER SCIENCE &amp; ENGINEERING (CSE) &bull; TEAM INNOVEDGE", styles["LetterUnivSub"]))
    story.append(Paragraph("Chikkasandra, Hesaraghatta Main Road, Bengaluru, Karnataka 560057", styles["LetterUnivSub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_BLACK, spaceBefore=4, spaceAfter=8))

    # Date
    story.append(Paragraph(f"<b>Date:</b> {DATE_STR}", styles["LetterToFrom"]))
    story.append(Spacer(1, 4))

    # TO block first
    to_block = (
        "<b>TO:</b><br/>"
        "The Dean &amp; University Administration,<br/>"
        "Through: The Director &amp; Faculty Mentor,<br/>"
        "Department of Computer Science &amp; Engineering (CSE),<br/>"
        "Sapthagiri NPS University (SNPSU), Bengaluru &ndash; 560057"
    )

    # FROM block second
    from_block = (
        "<b>FROM:</b><br/>"
        "<b>Team InnovEdge</b> (Dept. of Computer Science &amp; Engineering):<br/>"
        "&bull; <b>Kiran M. Biradar</b> (USN: <b>24SUUBECS0937</b>) &ndash; Lead Developer &amp; Architect<br/>"
        "&bull; <b>Karthik P.</b> (USN: <b>24SUUBECS0890</b>) &ndash; Co-Lead &amp; Technical Coordinator<br/>"
        "Under the Guidance of: <b>Faculty Mentor</b>, Dept. of CSE, SNPSU"
    )

    to_from_table = Table([[Paragraph(to_block, styles["LetterToFrom"]), Paragraph(from_block, styles["LetterToFrom"])]],
                          colWidths=[255, PRINTABLE_WIDTH - 255])
    to_from_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(to_from_table)
    story.append(Spacer(1, 6))

    # Subject
    story.append(Paragraph(
        "<b>SUBJECT: Requisition for Dedicated Server Space, Sub-Domain Provisioning, and Institutional Deployment Clearance for the 'SapthaEvent' University Management Platform.</b>",
        styles["LetterSubject"]
    ))

    story.append(Paragraph("Respected Dignitaries and Respected Faculty Authorities,", styles["DocBody"]))

    story.append(Paragraph(
        "We, the student engineering leads of <b>Team InnovEdge</b> from the Department of Computer Science &amp; Engineering, respectfully submit this official covering letter and requisition dossier for your review and administrative sanction.",
        styles["DocBody"]
    ))

    story.append(Paragraph(
        "<b>Context &amp; Reflection on Legacy 2025:</b> As the university dignitaries will recall, an initial prototype of the campus event portal was launched during the <b>Legacy 2025</b> university festival. While the initiative demonstrated the strong campus need for a digital system, our team acknowledges with utmost professional humility and regret the operational friction encountered during that event&mdash;including server latency under concurrent loads, gate roll-call delays, and synchronization bottlenecks. We took those challenges as a profound learning mandate.",
        styles["DocBody"]
    ))

    story.append(Paragraph(
        "<b>Complete Architectural Overhaul &amp; Current State:</b> Over the past months, under the guidance of our Faculty Mentor in the Department of CSE, Team InnovEdge has completely rebuilt, re-engineered, and hardened the entire codebase from the foundation up. We are proud to report that <b>SapthaEvent is now fully done, hardened, and 100% operational</b>, having passed <b>145/145 industrial automated test suites</b>. All past bottlenecks have been decisively solved: sub-second QR code ticket scanning with offline redundancy, dynamic department form builder, ACID-compliant database integrity, zero data loss, tamper-proof cryptographic certificates, and automatic NAAC/NIRF reporting.",
        styles["DocBody"]
    ))

    story.append(Paragraph(
        "<b>Specific Requisitions Submitted for Administrative Approval:</b>",
        styles["DocBody"]
    ))

    req_points = [
        "<b>1. Requisition for Dedicated Server Space:</b> We request allocation of dedicated server space (on-premise university server or lightweight cloud container compute) to host the production instance with zero downtime.",
        "<b>2. Official Sub-Domain Allocation:</b> Authorization to configure the official institutional sub-domain (<code>events.snpsu.edu.in</code>) with SSL intranet/internet routing for official branding.",
        "<b>3. Departmental Pilot Clearance:</b> Formal sanction to pilot the upgraded platform for upcoming events across the Department of CSE and all academic faculties of Sapthagiri NPS University.",
        "<b>4. Faculty Mentor &amp; Departmental Endorsement:</b> Direction and backing from our Faculty Mentor and Director of CSE to onboard departmental coordinators and student volunteers.",
    ]
    for rp in req_points:
        story.append(Paragraph(rp, styles["DocBullet"]))

    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "The software entails <b>zero commercial software licensing cost</b> for Sapthagiri NPS University and is ready for immediate deployment. We humbly request the Director, Dean, and Registrar to grant favorable sanction.",
        styles["DocBody"]
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Yours faithfully,", styles["DocBody"]))
    story.append(Spacer(1, 8))

    sign_box = [
        [
            Paragraph("____________________________<br/><b>Kiran M. Biradar</b><br/>Lead Developer &bull; USN: <b>24SUUBECS0937</b><br/>Team InnovEdge, Dept. of CSE", styles["TableCell"]),
            Paragraph("____________________________<br/><b>Karthik P.</b><br/>Co-Lead &bull; USN: <b>24SUUBECS0890</b><br/>Team InnovEdge, Dept. of CSE", styles["TableCell"]),
            Paragraph("____________________________<br/><b>Faculty Mentor</b><br/>Dept. of Computer Science &amp; Engg.<br/>Sapthagiri NPS University", styles["TableCell"]),
        ]
    ]
    t_sign_box = Table(sign_box, colWidths=[170, 170, PRINTABLE_WIDTH - 340])
    story.append(t_sign_box)

    # ─────────────────────────────────────────────────────────────
    # PAGE 2: FORMAL COVER PAGE
    # (Metadata table has NO security level, NO ref id, NO submission date)
    # (Approval Matrix: Submitted By, Director, Dean, Registrar)
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(Spacer(1, 14))

    if os.path.exists(target_logo):
        story.append(Image(target_logo, width=170, height=170 / (2048 / 703)))
        story.append(Spacer(1, 10))

    story.append(Paragraph("SAPTHAGIRI NPS UNIVERSITY", styles["CoverUnivTitle"]))
    story.append(Paragraph("Chikkasandra, Hesaraghatta Main Road, Bengaluru, Karnataka 560057", styles["CoverDeptTitle"]))
    story.append(Spacer(1, 3))
    story.append(Paragraph("DEPARTMENT OF COMPUTER SCIENCE &amp; ENGINEERING (CSE)", styles["CoverDeptTitle"]))
    story.append(Paragraph("Team InnovEdge &bull; Student Technical &amp; Software Development Council", styles["CoverDeptTitle"]))
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_BLACK, spaceBefore=2, spaceAfter=10))

    story.append(Paragraph("OFFICIAL PROJECT PROPOSAL &amp; INSTITUTIONAL REQUISITION", styles["CoverMainTitle"]))
    story.append(Paragraph(
        "Comprehensive Strategic Blueprint, Architecture, and Operational Documentation for Deployment of the <b>SapthaEvent</b> Campus Event Intelligence &amp; Orchestration Platform",
        styles["CoverSubtitle"]
    ))

    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=2, spaceAfter=12))

    # Metadata Grid (NO security level, NO ref id, NO submission date as requested)
    meta_table_data = [
        ["DOCUMENT TITLE", "Institutional Project Proposal & Server Space Requisition"],
        ["PROJECT NAME", "SapthaEvent &mdash; Enterprise Event Intelligence Platform"],
        ["ACADEMIC SESSION", f"Academic Year {ACADEMIC_YEAR}"],
        ["TARGET INSTITUTION", "Sapthagiri NPS University (SNPSU), Bengaluru"],
        ["DEVELOPED BY", "Team InnovEdge &bull; Dept. of Computer Science &amp; Engineering (CSE)"],
        ["PROJECT LEADS", "Kiran M. Biradar (USN: 24SUUBECS0937) &bull; Lead Developer &amp; Architect<br/>Karthik P. (USN: 24SUUBECS0890) &bull; Co-Lead &amp; Technical Coordinator"],
        ["FACULTY MENTOR", "Faculty Coordinator &bull; Dept. of Computer Science &amp; Engineering"],
        ["SUBMITTED TO", "The Director (CSE), Dean (Engineering), and Registrar, SNPSU"],
        ["PROJECT STATUS", "Production Ready &bull; 145/145 Automated Tests Passing &bull; Fully Functional"],
    ]
    meta_table = make_table(meta_table_data, [135, PRINTABLE_WIDTH - 135], has_header=False)
    story.append(meta_table)

    story.append(Spacer(1, 12))

    # Institutional Approval Matrix: Submitted By, Director, Dean, Registrar
    story.append(Paragraph("<b>INSTITUTIONAL ENDORSEMENT &amp; APPROVAL MATRIX</b>", styles["DocH3"]))
    sign_headers = [
        Paragraph("<b>SUBMITTED BY</b><br/><font size=6.5>Team InnovEdge Leads</font>", styles["TableCellCenter"]),
        Paragraph("<b>RECOMMENDED BY</b><br/><font size=6.5>Director, School of CSE</font>", styles["TableCellCenter"]),
        Paragraph("<b>ENDORSED BY</b><br/><font size=6.5>Dean, Academic Affairs / Engg.</font>", styles["TableCellCenter"]),
        Paragraph("<b>FINAL SANCTION</b><br/><font size=6.5>Registrar, SNPSU</font>", styles["TableCellCenter"]),
    ]
    sign_rows = [
        sign_headers,
        [
            Paragraph("<br/><br/><br/>_______________________<br/><b>Kiran M. Biradar</b><br/><b>Karthik P.</b><br/>Team InnovEdge (CSE)", styles["TableCellCenter"]),
            Paragraph("<br/><br/><br/>_______________________<br/><b>Director</b><br/>Dept. of Computer Science &amp; Engg.<br/>Sapthagiri NPS University", styles["TableCellCenter"]),
            Paragraph("<br/><br/><br/>_______________________<br/><b>Dean</b><br/>Faculty of Engineering &amp; Tech.<br/>Sapthagiri NPS University", styles["TableCellCenter"]),
            Paragraph("<br/><br/><br/>_______________________<br/><b>Registrar</b><br/>University Administration<br/>Sapthagiri NPS University", styles["TableCellCenter"]),
        ]
    ]
    sign_table = Table(sign_rows, colWidths=[PRINTABLE_WIDTH / 4.0] * 4)
    sign_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GRAY),
        ("BOX", (0, 0), (-1, -1), 1, COLOR_BLACK),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))
    story.append(sign_table)

    # ─────────────────────────────────────────────────────────────
    # PAGE 3: EXECUTIVE SUMMARY & PROBLEM STATEMENT (WHY BUILD IT)
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("1. EXECUTIVE SUMMARY &amp; PROJECT GENESIS", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "<b>SapthaEvent</b> is an enterprise-grade, institutional event management and intelligence portal engineered specifically for <b>Sapthagiri NPS University (SNPSU)</b>. Conceived and engineered indigenously by <b>Team InnovEdge</b> within the Department of Computer Science &amp; Engineering, the portal provides a unified digital operational backbone for all technical, cultural, sporting, management, and academic events hosted across SNPSU.",
        styles["DocBody"]
    ))
    story.append(Paragraph(
        "Built on Python, Flask, and an ACID-compliant relational database, SapthaEvent replaces disjointed, insecure manual procedures with an automated, audit-ready platform. Following the real-world trials and operational feedback gathered during <b>Legacy 2025</b>, the software has been completely rebuilt to deliver high-speed QR check-in, real-time venue conflict detection, verifiable cryptographic certificates, competition evaluation leaderboards, and instant report generation for NAAC and NIRF accreditation.",
        styles["DocBody"]
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("2. THE PROBLEM STATEMENT: WHY WE BUILT SAPTHAEVENT", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "Sapthagiri NPS University hosts dozens of high-value technical symposia, national conferences, hackathons, sports meets, cultural fests, and workshops every academic year. However, campus event operations have historically suffered from severe administrative bottlenecks:",
        styles["DocBody"]
    ))

    problem_table_data = [
        ["OPERATIONAL AREA", "LEGACY / AD-HOC METHOD", "SYSTEMIC RISK & INEFFICIENCY", "SAPTHAEVENT SOLUTION"],
        [
            "Student Registration",
            "Unlinked Google Forms shared across WhatsApp groups.",
            "Duplicate entries, lack of payment verification, spreadsheet row overwrites, and zero identity validation.",
            "Centralized portal with SNPSU student email verification, duplicate-prevention rules, and instant database records."
        ],
        [
            "Gate Access & Attendance",
            "Physical paper clipboard registers & roll-calls at auditorium gates.",
            "Massive entrance bottlenecks (30&ndash;45 min queues), proxy attendance, unauthorized outsider entry, safety hazards.",
            "Sub-second digital QR code ticketing scanned via smartphone cameras with offline redundancy and duplicate detection."
        ],
        [
            "Venue & Asset Booking",
            "Informal verbal requests or written paper chits to department heads.",
            "Severe venue clashes (auditoriums double-booked), sound system equipment contention, delayed event schedules.",
            "Live institutional venue master catalog with real-time slot conflict alerts and automated administrative approval workflows."
        ],
        [
            "Certificates & Validation",
            "Static PNG/PDF templates exported manually via Canva/Photoshop.",
            "Rampant certificate forgery, non-verifiable credentials, lack of permanent repository for student achievements.",
            "Automated PDF certificates with unique cryptographic verification codes and public QR scan verification endpoints."
        ],
        [
            "Competition Judging",
            "Handwritten score-sheets calculated on paper during live fests.",
            "Calculation discrepancies, accusations of bias, delayed prize distributions, lack of audit trail for jury scores.",
            "Dedicated Judge Portal with multi-criteria rubric scoring (0&ndash;100), real-time leaderboards, and automatic tie-breaking."
        ],
        [
            "Accreditation & Auditing",
            "Faculty coordinators spending 2&ndash;3 weeks gathering data for NAAC/NIRF.",
            "Missing participant demographics, unverified attendance records, loss of past event data upon student graduation.",
            "One-click generation of comprehensive PDF/Excel reports formatted precisely to NAAC Criteria 3 &amp; 5 and NIRF requirements."
        ],
    ]
    t_prob = make_table(problem_table_data, [85, 110, 155, 161])
    story.append(t_prob)

    # ─────────────────────────────────────────────────────────────
    # PAGE 4: THE SOLUTION ARCHITECTURE & 7-PHASE LIFECYCLE
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("3. THE SOLUTION: SYSTEM ARCHITECTURE &amp; STRATEGIC VISION", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "SapthaEvent was engineered by Team InnovEdge to solve institutional pain points by providing an end-to-end, unified lifecycle for every event hosted at SNPSU. The architecture bridges the entire operational workflow across seven key phases:",
        styles["DocBody"]
    ))

    lifecycle_data = [
        ["PHASE", "STAGE NAME", "ACTORS INVOLVED", "KEY AUTOMATION & VALUE DELIVERED"],
        ["1", "Event Proposal & Approval", "Faculty SPOC, Director, Dean", "Digital submission of event proposal, budget estimation, and venue reservation with multi-tier administrative approval."],
        ["2", "Publishing & Publicity", "Event Organizers, Students", "Public responsive portal listing with banner, schedule, speaker bios, team size rules, and registration deadlines."],
        ["3", "Registration & Ticketing", "Student / External Delegate", "Automated form validation, team matchmaking, coupon handling, and instant generation of cryptographic QR passes."],
        ["4", "Fast Gate Ingestion", "Volunteers, Security Staff", "Sub-second camera scanning at entry gates. Detects duplicate scans, flags invalid tickets, and logs exact timestamp."],
        ["5", "Live Competition Judging", "Jury, External Evaluators", "Real-time evaluation interface on tablets/phones. Multi-round rubric scoring with live leaderboard generation."],
        ["6", "Credential Issuance", "All Verified Attendees", "System releases high-definition verifiable PDF certificates with live validation URLs only to confirmed checked-in attendees."],
        ["7", "Institutional Archival", "Director, IQAC, Accreditation", "Automated export of attendance figures, gender ratios, participant feedback, and expense summaries for permanent archival."],
    ]
    t_life = make_table(lifecycle_data, [40, 110, 110, 251])
    story.append(t_life)

    story.append(Spacer(1, 10))
    story.append(Paragraph("KEY ARCHITECTURAL PILLARS &amp; DESIGN PRINCIPLES", styles["DocH2"]))

    pillars_data = [
        ["PILLAR", "ARCHITECTURAL PRINCIPLE", "INSTITUTIONAL VALUE FOR SAPTHAGIRI NPS UNIVERSITY"],
        [
            "1. Zero-Trust Security",
            "Role-based privilege isolation & strict session validation.",
            "Prevents unauthorized student edits, protects confidential staff data, and maintains an unalterable audit log of all gate check-ins."
        ],
        [
            "2. Offline Gate Continuity",
            "Client-side caching with local synchronization queues.",
            "Ensures check-in desks continue operating seamlessly even if campus Wi-Fi or mobile networks experience congestion during mega-fests."
        ],
        [
            "3. Cryptographic Authenticity",
            "SHA-256 digital certificate signing with public QR resolver.",
            "Positions SNPSU as a pioneering institution with tamper-proof student credentials verifiable by global corporate recruiters."
        ],
        [
            "4. Institutional Sovereignty",
            "100% in-house software development & local database ownership.",
            "Eliminates dependency on expensive SaaS vendors; guarantees full data privacy without third-party vendor lock-in."
        ],
    ]
    t_pillars = make_table(pillars_data, [95, 150, 266])
    story.append(t_pillars)

    # ─────────────────────────────────────────────────────────────
    # PAGE 5: CORE FUNCTIONAL MODULES & STAKEHOLDER MATRIX
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("4. CORE FUNCTIONAL MODULES &amp; STRATEGIC USE CASES", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "The platform comprises eight purpose-built functional modules engineered by Team InnovEdge to serve the operational needs of university stakeholders:",
        styles["DocBody"]
    ))

    modules_table_data = [
        ["CODE", "MODULE NAME", "CORE WORKFLOW & CAPABILITIES", "INSTITUTIONAL BENEFIT"],
        [
            "MOD-A",
            "Multi-Tier RBAC & Governance",
            "Role isolation across 6 personas: SuperAdmin (Director/Dean), Faculty SPOC, Organizer, Gate Staff, Judge, and Participant.",
            "Eliminates unauthorized data tampering; ensures faculty retain administrative oversight of all student activities."
        ],
        [
            "MOD-B",
            "Anti-Fraud QR Ticketing",
            "Instant dynamic QR passes sent via email/web. Camera scan check-in with duplicate detection and offline fallback.",
            "Reduces gate entry wait times from 40 mins to 1.5 seconds per student; eliminates proxy attendance entirely."
        ],
        [
            "MOD-C",
            "Venue & Asset Booking",
            "Institutional venue directory with slot conflict detection, capacity checks, and approval routing.",
            "Prevents auditorium and lab scheduling clashes; optimizes utilization of university physical infrastructure."
        ],
        [
            "MOD-D",
            "Cryptographic Certificates",
            "On-demand vector PDF certificates with unique verification hash and public scan validation URL.",
            "Protects university brand reputation against forgery; saves over INR 50,000 annually in certificate printing costs."
        ],
        [
            "MOD-E",
            "Finance & Ledger Tracking",
            "Tracks paid tickets, sponsor contributions, student coupons, and automated payment receipts.",
            "Guarantees financial audit compliance; provides transparent revenue reports directly to college management."
        ],
        [
            "MOD-F",
            "Hackathon & Jury Portal",
            "Team registration, project submissions, multi-criteria rubric scoring (0&ndash;100), and real-time leaderboards.",
            "Ensures unbiased judging in flagship technical competitions with a fully transparent numerical audit trail."
        ],
        [
            "MOD-G",
            "Omnichannel Notifications",
            "Transactional notifications via university SMTP / Brevo and WhatsApp API for reminders and schedule alerts.",
            "Replaces chaotic WhatsApp group broadcasts with professional, official university communication."
        ],
        [
            "MOD-H",
            "Accreditation Reporting",
            "One-click generation of structured reports formatted for NAAC Criteria 3.3.2 / 5.3.3 and NIRF submissions.",
            "Saves weeks of manual administrative labor during annual inspections by maintaining real-time digital event records."
        ],
    ]
    t_mod = make_table(modules_table_data, [45, 110, 205, 151])
    story.append(t_mod)

    story.append(Spacer(1, 8))
    story.append(Paragraph("STAKEHOLDER PERSONAS &amp; PRIVILEGE ACCESS MATRIX", styles["DocH2"]))

    roles_data = [
        ["USER ROLE", "TARGET STAKEHOLDER", "PERMITTED PORTAL PRIVILEGES", "SECURITY GUARDRAIL"],
        ["Super Admin", "Director (CSE) / Dean / Registrar", "Full platform control, departmental oversight, system audit logs, global configuration.", "Master Secret Key authentication."],
        ["Department SPOC", "Designated Faculty Coordinator", "Approve departmental events, assign organizers, monitor venue bookings, audit budgets.", "Restricted to assigned academic department."],
        ["Event Organizer", "Student Council / Club Lead", "Create event drafts, manage schedules, monitor registrations, allocate gate volunteers.", "Requires faculty SPOC digital clearance."],
        ["Gate Volunteer", "Student Event Staff", "High-speed camera QR code ticket scanner, check-in dashboard, attendance logs.", "Cannot view student contact PII or modify events."],
        ["Evaluator / Judge", "Faculty & External Industry Jury", "Access assigned team submissions, enter rubric scores, submit official rankings.", "Blind scoring mode; cannot alter team rosters."],
        ["Participant", "SNPSU Students & Delegates", "Browse events, register, form teams, download QR passes, download verified certificates.", "Self-service portal; strict data isolation."],
    ]
    t_roles = make_table(roles_data, [75, 110, 215, 111])
    story.append(t_roles)

    # ─────────────────────────────────────────────────────────────
    # PAGE 6: TECHNICAL ARCHITECTURE & SNPSU-SPECIFIC COST FEASIBILITY
    # (Tailored strictly to handle data and details for only SNPSU)
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("5. TECHNICAL ARCHITECTURE, SECURITY &amp; DATA GOVERNANCE", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "SapthaEvent is engineered as a robust, production-ready enterprise application compliant with industry software engineering standards, data privacy laws, and academic institutional security requirements.",
        styles["DocBody"]
    ))

    tech_specs = [
        ["ARCHITECTURAL LAYER", "TECHNOLOGY SELECTION", "SPECIFICATIONS & INSTITUTIONAL ADVANTAGE"],
        ["Backend Core", "Python 3.11 / Flask 3.x", "Lightweight WSGI framework, microservices-ready, minimal server memory footprint (< 150 MB)."],
        ["Database Layer", "PostgreSQL (SQLAlchemy ORM)", "ACID-compliant relational storage. Includes local zero-config SQLite fallback for disaster recovery and offline continuity."],
        ["Document Engine", "ReportLab High-Speed Generator", "Vector-grade PDF rendering engine capable of compiling thousands of certificates and reports in seconds."],
        ["Security & CSRF", "Flask-WTF & Talisman Middleware", "Enforces strict CSRF token validation on all mutating POST requests, secure HTTP headers (CSP, HSTS, X-Frame-Options)."],
        ["Authentication", "PBKDF2-SHA256 & Session Guard", "Cryptographic password hashing, secure HttpOnly/SameSite cookies, brute-force rate-limiting on login endpoints."],
        ["Data Privacy", "Role-Isolated PII Protection", "Participant phone numbers and personal data are strictly masked from unauthorized volunteers and external attendees."],
        ["Quality Assurance", "Automated Pytest Suite", "145 comprehensive automated tests passing with 100% verification across security, payments, ticketing, and scheduling."],
    ]
    t_tech = make_table(tech_specs, [95, 130, 286])
    story.append(t_tech)

    story.append(Spacer(1, 8))
    story.append(Paragraph("6. INFRASTRUCTURE &amp; HOSTING COST FEASIBILITY FOR SNPSU", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "Because SapthaEvent is an <b>indigenous asset engineered by Team InnovEdge</b>, there are <b>zero commercial software licensing fees</b>. The financial requirements are strictly limited to the minimal server space and compute required to store and handle the data and event operations for <b>Sapthagiri NPS University (SNPSU)</b> alone (~5,000&ndash;8,000 students across all departments).",
        styles["DocBody"]
    ))

    cost_comparison = [
        ["OPERATIONAL RESOURCE", "COMMERCIAL SAAS (EVENTBRITE/VFAIRS)", "SAPTHAEVENT FOR SNPSU", "INSTITUTIONAL SAVINGS"],
        ["Platform Software License", "INR 2,50,000 &ndash; INR 5,00,000 / year", "INR 0 (Developed In-House by InnovEdge)", "100% Software License Saved"],
        ["Per-Registration Commission", "3% to 7% cut on all paid registrations", "INR 0 (Zero platform cut for SNPSU)", "100% Event Funds Retained"],
        ["Server Space & Compute", "Billed as part of costly enterprise tiers", "Minimal Campus Server / Cloud (~INR 400/mo)", "Negligible Operational Expense"],
        ["Database Storage (SNPSU Data)", "Hosted externally on vendor clouds", "Local / Managed SQL (~300MB for SNPSU)", "100% Student Privacy & Sovereignty"],
        ["Certificate Generation", "Third-party add-on (INR 5 &ndash; 10 / cert)", "Unlimited Vector PDF Engine Included", "INR 50,000+ saved on certificate printing"],
    ]
    t_cost = make_table(cost_comparison, [110, 135, 135, 131])
    story.append(t_cost)

    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>Summary for SNPSU Administration:</b> Deploying SapthaEvent saves the university an estimated <b>INR 2,50,000 to INR 5,00,000 annually</b> compared to external event platforms. The total infrastructure cost to run the system across all departments of SNPSU is negligible (under INR 5,000 annually or INR 0 if hosted on internal campus servers).",
        styles["DocBody"]
    ))

    # ─────────────────────────────────────────────────────────────
    # PAGE 7: PHASED IMPLEMENTATION ROADMAP & REQUISITIONS
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("7. PHASED IMPLEMENTATION &amp; ROLLOUT ROADMAP", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "To ensure a seamless, non-disruptive onboarding across all academic faculties, the deployment of SapthaEvent will follow a structured 3-phase rollout plan over 6 weeks:",
        styles["DocBody"]
    ))

    roadmap_data = [
        ["PHASE & TIMELINE", "OBJECTIVE", "ACTIVITIES & MILESTONES", "DELIVERABLES / SIGNOFF"],
        [
            "Phase 1: Weeks 1 &ndash; 2\n(Sandbox & IT Integration)",
            "Administrative Validation & Server Provisioning",
            "• Demonstration to Director (CSE) and Dean of Engineering.\n• University IT mapping for sub-domain (events.snpsu.edu.in).\n• Provisioning of dedicated server space / container runtime.\n• Creation of administrative credentials for CSE faculty SPOC.",
            "Server Space Allocation & Pilot Clearance."
        ],
        [
            "Phase 2: Weeks 3 &ndash; 4\n(Pilot Fest Deployment)",
            "Departmental Pilot & Stress Testing",
            "• Deployment for upcoming CSE departmental symposium/hackathon.\n• Volunteer gate check-in training (15-minute briefing).\n• Verification of QR ticketing flow, live judging, and certificates.\n• Collection of faculty and student usability feedback.",
            "Pilot Evaluation Report & Performance Audit."
        ],
        [
            "Phase 3: Weeks 5 &ndash; 6\n(University-Wide Rollout)",
            "Full Campus Institutionalization",
            "• Onboarding of all departmental SPOCs and student clubs.\n• Integration into the official university academic calendar.\n• Centralized dashboard handoff to Dean and Campus Authorities.\n• Archival of all event reports for NAAC/NIRF accreditation.",
            "Complete Institutional Operational Handoff."
        ],
    ]
    t_road = make_table(roadmap_data, [95, 110, 180, 126])
    story.append(t_road)

    story.append(Spacer(1, 8))
    story.append(Paragraph("8. SPECIFIC REQUISITIONS &amp; SANCTIONS REQUESTED", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "For the successful deployment and institutionalization of this platform, Team InnovEdge respectfully requests formal sanction for the following items:",
        styles["DocBody"]
    ))

    sanctions = [
        "<b>Requisition 1 &mdash; Allocation of Dedicated Server Space:</b> Sanction for server compute and storage on the university data center / cloud infrastructure to host the production backend and database for SNPSU.",
        "<b>Requisition 2 &mdash; IT Sub-Domain &amp; DNS Binding:</b> Authorization for the University Systems Administrator to point <code>events.snpsu.edu.in</code> to the deployment server with valid SSL certificates.",
        "<b>Requisition 3 &mdash; Departmental Pilot Authorization:</b> Formal permission from the Director of CSE and Dean to execute the pilot deployment for upcoming engineering symposiums and hackathons.",
        "<b>Requisition 4 &mdash; Notification Relay Configuration:</b> Approval to route transactional event emails and ticket deliveries through the university's official notification relay / SMTP.",
        "<b>Requisition 5 &mdash; Accreditation Data Recognition:</b> Formal recognition that event registers, verified attendance logs, and participant feedback generated by SapthaEvent constitute official institutional records for NAAC and NIRF audits.",
    ]
    for s in sanctions:
        story.append(Paragraph(s, styles["DocNumbered"]))

    # ─────────────────────────────────────────────────────────────
    # PAGE 8: UNDERTAKING & OFFICIAL APPROVAL MATRIX
    # (Stage 1: Team InnovEdge, Stage 2: Director, Stage 3: Dean, Stage 4: Registrar)
    # ─────────────────────────────────────────────────────────────
    story.append(PageBreak())

    story.append(Paragraph("9. INSTITUTIONAL UNDERTAKING &amp; COMPLIANCE DECLARATION", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "We, the student engineering leads of <b>Team InnovEdge</b>, hereby declare and undertake the following institutional commitments regarding the maintenance and operation of the <b>SapthaEvent</b> platform:",
        styles["DocBody"]
    ))

    undertakings = [
        "<b>1. Exclusive University Ownership:</b> All software codebases, database schemas, documentation, and digital assets of SapthaEvent shall remain the exclusive intellectual property of Sapthagiri NPS University (SNPSU).",
        "<b>2. Strict Data Ethics &amp; Confidentiality:</b> No student, faculty, or institutional data will ever be monetized, shared, or transferred outside the university. All records will be securely maintained strictly within SNPSU infrastructure.",
        "<b>3. Dedicated Student Maintenance &amp; Support:</b> Team InnovEdge undertakes to provide continuous technical support, server monitoring, bug fixes, and volunteer training for all events without disrupting academic schedules.",
        "<b>4. Zero Commercial Liability:</b> The platform entails no licensing or acquisition cost to the university. Any infrastructure expansions will be submitted for prior administrative review.",
    ]
    for u in undertakings:
        story.append(Paragraph(u, styles["DocBullet"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph("10. OFFICIAL SIGN-OFF, RECOMMENDATION &amp; APPROVAL MATRIX", styles["DocH1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=COLOR_BLACK, spaceBefore=1, spaceAfter=6))

    story.append(Paragraph(
        "This project proposal and server requisition dossier has been scrutinized and is respectfully submitted for formal recommendation and executive sanction:",
        styles["DocBody"]
    ))
    story.append(Spacer(1, 4))

    # Detailed 4-Stage Approval Matrix: Team InnovEdge -> Director -> Dean -> Registrar
    approval_table_data = [
        [
            Paragraph("<b>STAGE 1: PROJECT SUBMISSION</b><br/><font size=6.5>Team InnovEdge Leads &bull; Dept. of CSE</font>", styles["TableCellBold"]),
            Paragraph("<b>STAGE 2: DEPARTMENTAL SCRUTINY &amp; RECOMMENDATION</b><br/><font size=6.5>Director, School of Computer Science &amp; Engineering</font>", styles["TableCellBold"])
        ],
        [
            Paragraph(
                "<i>We confirm that the software is 100% complete, fully tested (145/145 passing), and ready for university deployment.</i><br/><br/>"
                "Signature 1: ___________________________<br/>"
                "Name: <b>Kiran M. Biradar</b> (USN: <b>24SUUBECS0937</b>)<br/>"
                "Designation: Lead Developer &amp; Architect<br/><br/>"
                "Signature 2: ___________________________<br/>"
                "Name: <b>Karthik P.</b> (USN: <b>24SUUBECS0890</b>)<br/>"
                "Designation: Co-Lead &amp; Technical Coordinator<br/>"
                f"Date: {DATE_STR}",
                styles["TableCell"]
            ),
            Paragraph(
                "<i>I have reviewed the technical architecture, verified the resolution of legacy bottlenecks, and recommend this requisition for institutional approval.</i><br/><br/>"
                "Signature: ___________________________<br/>"
                "Name: ___________________________<br/>"
                "Designation: <b>Director, School of CSE</b><br/>"
                "Department Seal: [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]<br/>"
                "Date: ____ / ____ / 2026",
                styles["TableCell"]
            )
        ],
        [
            Paragraph("<b>STAGE 3: ACADEMIC &amp; INFRASTRUCTURE ENDORSEMENT</b><br/><font size=6.5>Dean, Faculty of Engineering &amp; Technology / Academics</font>", styles["TableCellBold"]),
            Paragraph("<b>STAGE 4: FINAL EXECUTIVE SANCTION &amp; APPROVAL</b><br/><font size=6.5>Registrar, Sapthagiri NPS University</font>", styles["TableCellBold"])
        ],
        [
            Paragraph(
                "<i>Endorsed for server space allocation, sub-domain binding, and campus-wide pilot deployment.</i><br/><br/>"
                "Signature: ___________________________<br/>"
                "Name: ___________________________<br/>"
                "Designation: <b>Dean, Faculty of Engineering</b><br/>"
                "Dean Office Seal: [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]<br/>"
                "Date: ____ / ____ / 2026",
                styles["TableCell"]
            ),
            Paragraph(
                "<b>[ &nbsp; ] APPROVED &amp; SANCTIONED</b><br/>"
                "<b>[ &nbsp; ] APPROVED WITH CONDITIONS</b><br/>"
                "<b>[ &nbsp; ] REQUIRES REVISION</b><br/><br/>"
                "Remarks: _____________________________________<br/>"
                "Signature: ___________________________<br/>"
                "Designation: <b>Registrar, Sapthagiri NPS University</b><br/>"
                "University Seal: [ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ]<br/>"
                "Date: ____ / ____ / 2026",
                styles["TableCell"]
            )
        ]
    ]

    t_appr = Table(approval_table_data, colWidths=[PRINTABLE_WIDTH / 2.0, PRINTABLE_WIDTH / 2.0])
    t_appr.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER_GRAY),
        ("BOX", (0, 0), (-1, -1), 1.2, COLOR_BLACK),
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
        ("BACKGROUND", (0, 2), (-1, 2), COLOR_HEADER_BG),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_appr)

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<font size=7 color='#666666'>* Official Institutional Requisition &bull; Prepared by Team InnovEdge &bull; Dept. of Computer Science &amp; Engineering &bull; Sapthagiri NPS University.</font>",
        styles["TableCellCenter"]
    ))

    return story


def generate_pdf():
    print(f"Generating Formal Proposal & Requisition PDF: {OUTPUT_PATH}")
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=48,
        bottomMargin=48,
    )

    story = build_proposal_story()
    doc.build(story, canvasmaker=FormalMonochromeCanvas)
    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"SUCCESS: PDF Generated at {OUTPUT_PATH} ({size_kb:.1f} KB)")
    return OUTPUT_PATH


if __name__ == "__main__":
    generate_pdf()
