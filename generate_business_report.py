#!/usr/bin/env python3
"""
generate_business_report.py — Generates a professional PDF business and monetization report
for SapthaEvent commercial deployment.

Output: reports/SapthaEvent_Business_Monetization_Report.pdf
"""
import os
import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Rect

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(REPORT_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(REPORT_DIR, "SapthaEvent_Business_Monetization_Report.pdf")

NAVY    = colors.HexColor("#1a2557")
GOLD    = colors.HexColor("#c9a45e")
GREEN   = colors.HexColor("#10b981")
RED     = colors.HexColor("#ef4444")
BLUE    = colors.HexColor("#3b82f6")
ORANGE  = colors.HexColor("#f97316")
GRAY    = colors.HexColor("#64748b")
LIGHT   = colors.HexColor("#f8fafc")
WHITE   = colors.white
BLACK   = colors.black

NOW = datetime.datetime.now()
DATE_STR = NOW.strftime("%d %B %Y")

# ═══════════════════════════════════════════════════════════════
# STYLES
# ═══════════════════════════════════════════════════════════════
styles = getSampleStyleSheet()

styles.add(ParagraphStyle("CoverTitle", fontName="Helvetica-Bold", fontSize=24, leading=30,
    textColor=NAVY, alignment=TA_CENTER, spaceAfter=10))
styles.add(ParagraphStyle("CoverSub", fontName="Helvetica", fontSize=12, leading=16,
    textColor=GRAY, alignment=TA_CENTER, spaceAfter=6))
styles.add(ParagraphStyle("SectionHead", fontName="Helvetica-Bold", fontSize=14, leading=18,
    textColor=NAVY, spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle("SubHead", fontName="Helvetica-Bold", fontSize=11, leading=14,
    textColor=NAVY, spaceBefore=12, spaceAfter=5))
styles.add(ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5, leading=13.5,
    textColor=BLACK, alignment=TA_JUSTIFY, spaceAfter=6))
styles.add(ParagraphStyle("BodyItalic", fontName="Helvetica-Oblique", fontSize=9.5, leading=13.5,
    textColor=BLACK, alignment=TA_JUSTIFY, spaceAfter=6))
styles.add(ParagraphStyle("BulletCustom", fontName="Helvetica", fontSize=9.5, leading=13.5,
    textColor=BLACK, leftIndent=20, bulletIndent=10, spaceAfter=3))
styles.add(ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=9, leading=12,
    textColor=WHITE, alignment=TA_CENTER))
styles.add(ParagraphStyle("TC", fontName="Helvetica", fontSize=8.5, leading=11.5,
    textColor=BLACK))
styles.add(ParagraphStyle("TCC", fontName="Helvetica", fontSize=8.5, leading=11.5,
    textColor=BLACK, alignment=TA_CENTER))

# ═══════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════
def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(2)
    canvas.line(40, A4[1]-40, A4[0]-40, A4[1]-40)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(40, A4[1]-35, "SAPTHAEVENT — BUSINESS & MONETIZATION STRATEGY")
    canvas.drawRightString(A4[0]-40, A4[1]-35, f"COMMERCIAL PLAYBOOK — {DATE_STR}")
    canvas.setLineWidth(1)
    canvas.line(40, 45, A4[0]-40, 45)
    canvas.drawString(40, 32, "SapthaEvent Commercial Deployment Plan & Pitch Deck Support")
    canvas.drawRightString(A4[0]-40, 32, f"Page {doc.page}")
    canvas.restoreState()


def section_table(data, col_widths, header_bg=NAVY):
    t = Table(data, colWidths=col_widths)
    base_style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("BOX", (0, 0), (-1, -1), 1, header_bg),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
    ]
    t.setStyle(TableStyle(base_style))
    return t


# ═══════════════════════════════════════════════════════════════
# BUILD PDF
# ═══════════════════════════════════════════════════════════════
def build_report():
    doc = SimpleDocTemplate(
        OUTPUT_PATH, pagesize=A4,
        topMargin=55, bottomMargin=55, leftMargin=40, rightMargin=40,
        title="SapthaEvent Commercial Deployment Strategy & Financial Models",
        author="SapthaEvent Tech & Business Team"
    )
    story = []
    W = A4[0] - 80

    # ════════════════════ COVER PAGE ════════════════════
    story.append(Spacer(1, 40))
    d = Drawing(W, 5)
    d.add(Rect(0, 0, W, 5, fillColor=NAVY, strokeColor=None))
    story.append(d)
    story.append(Spacer(1, 15))

    story.append(Paragraph("SAPTHAEVENT PLATFORM", styles["CoverSub"]))
    story.append(Paragraph("University Event Management Infrastructure", styles["CoverSub"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("BUSINESS MODEL &<br/>FINANCIAL PLANS", styles["CoverTitle"]))
    story.append(Spacer(1, 5))
    story.append(Paragraph("Scale & Costing Analysis, Tiered Pricing, Upsell Strategy, and Pitch Decks", styles["CoverSub"]))

    d2 = Drawing(W, 3)
    d2.add(Rect(W/2-60, 0, 120, 3, fillColor=GOLD, strokeColor=None))
    story.append(d2)
    story.append(Spacer(1, 20))

    # Business Metrics Overview Table
    info_data = [
        ["Product Type", "White-Labeled Multi-Instance SaaS (Relational Database)"],
        ["Target Capacity", "Minimum 25,000 active student records per college instance"],
        ["Primary Pricing Plan", "Subscription Model (Flat ARR) — Model A"],
        ["Secondary Pricing Plan", "Setup + Annual Maintenance (CapEx) — Model B"],
        ["Average Profit Margin", "80% - 85% Net Profit Margin per college deployment"],
        ["Infrastructure Tiers", "Basic / Optimal (Standard Cloud) / High-Availability"],
        ["Upsell Matrix", "Three Structured Feature Upgrade Packages (Scope Lock)"],
        ["Target Revenue/College", "₹60,000 - ₹1,20,000 initial year depending on model"],
    ]
    story.append(section_table(
        [["Financial Aspect", "Strategic Configuration"]] + info_data,
        [150, 310]
    ))

    story.append(Spacer(1, 35))
    sig_data = [
        ["Prepared By:", "Approved By:", "Commercial Lead:"],
        ["", "", ""],
        ["________________", "________________", "________________"],
        ["Tech Lead", "Advisor / Sponsor", "Business Architect"],
        ["Date:", "Date:", "Date:"],
    ]
    st = Table(sig_data, colWidths=[W/3]*3)
    st.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), NAVY),
        ("ALIGNMENT", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 1), (-1, 1), 35),
    ]))
    story.append(st)
    story.append(PageBreak())

    # ════════════════════ SECTION 1: EXECUTIVE SUMMARY ════════════════════
    story.append(Paragraph("1. ARCHITECTURAL MISSION: MULTI-INSTANCE SCALE", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "A critical commercial decision for the <b>SapthaEvent Platform</b> is the deployment model. "
        "Instead of forcing all institutions into a single multi-tenant shared database, we offer a "
        "<b>multi-instance isolated deployment model</b> (each college gets its own cloud container and database). "
        "This architectural choice is crucial for college administrators and handles at least <b>25,000 records</b> "
        "per college without sweat.",
        styles["Body"]
    ))

    story.append(Paragraph("<b>Key Strategic Drivers:</b>", styles["SubHead"]))
    drivers = [
        "<b>Data Privacy & Legal Compliance:</b> Colleges are highly sensitive to their student details (grades, records, USNs) mixing with competitors. Dedicated instances ensure absolute data isolation.",
        "<b>Performance Security (No Noisy Neighbors):</b> If College A runs a massive registration or exports 25,000 Excel rows on a results day, it will not consume resources or cause lag for College B.",
        "<b>Customizability:</b> Isolated instances let us apply minor college-level custom configurations (like specific custom templates, payment gateways, or category setups) without rewrite to a global schema.",
        "<b>Scale Safeguard:</b> Supabase/PostgreSQL easily handles 25,000 records on low-cost hardware. Isolated instances prevent databases from swelling into millions of rows across colleges, keeping database search speeds fast."
    ]
    for d in drivers:
        story.append(Paragraph(f"• {d}", styles["BulletCustom"]))

    # ════════════════════ SECTION 2: COST MATRIX ════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("2. HOSTING & INFRASTRUCTURE COST MATRIX", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "To run isolated instances profitably, we evaluate infrastructure across three distinct scaling tiers, "
        "balancing cost against high traffic spikes during admissions or result announcements.",
        styles["Body"]
    ))

    infra_data = [
        ["Tier", "Configuration", "Cost / Month", "Capacity Limit", "Recommended For"],
        ["Basic (Cheap)", "Shared Compute (512MB RAM) + Shared Starter DB Instance", "~$10 USD (₹800)", "Up to 5,000 active student records", "Small institutes / trial periods"],
        ["Optimal (Best Val)", "Dedicated Compute (1GB RAM) + Dedicated PostgreSQL DB", "~$45 USD (₹3,600)", "Easily handles 25,000+ student records", "Standard deployment (Recommended)"],
        ["Premium (High)", "Dedicated 2 CPU / 4GB RAM + Pooler (PgBouncer) + Cold Backup", "~$120 USD (₹9,600)", "100,000+ student records, high traffic", "Large universities / peak registration seasons"],
    ]
    story.append(section_table(
        [["Tier Description", "Spec Details", "Monthly Cost", "Capacity Limit", "Best Fit"]] + infra_data,
        [80, 120, 80, 100, 80]
    ))

    # ════════════════════ SECTION 3: PRICING MODELS ════════════════════
    story.append(PageBreak())
    story.append(Paragraph("3. COMMERCIAL MODELS & PROFIT MATRIX", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "We offer colleges two distinct pricing strategies depending on their financial preference. "
        "Both models are built to ensure high profit margins while providing low cost barrier entries.",
        styles["Body"]
    ))

    pricing_data = [
        ["Model", "Upfront Cost", "Recurring Fee", "Our Internal Cost", "Net Profit Margin", "Commercial Advantage"],
        ["Model A: Subscription (OpEx)", "₹0 (Zero Setup)", "₹60,000 - ₹80,000 / year ($750 - $1,000 USD)", "~$600 / year (Standard Tier + maintenance)", "80% - 85% Profit Margin", "Predictable Annual Recurring Revenue (ARR); absorbs infrastructure costs."],
        ["Model B: Setup + AMC (CapEx)", "₹1,20,000 ($1,500 USD) (Includes white-label & setup)", "₹25,000 / year ($300 USD) (AMC covers servers + minor bugs)", "Setup: ₹0 AMC: ~$300 / year", "Setup: 100% AMC: 50% Profit", "Pulls immediate cash upfront to fund development; covers server costs via AMC."],
    ]
    story.append(section_table(
        [["Pricing Model", "Initial Setup", "Annual AMC/Sub", "Internal Cost", "Margin", "Strategic Advantage"]] + pricing_data,
        [100, 60, 60, 60, 60, 120]
    ))

    # ════════════════════ SECTION 4: UPSELL PACKAGES ════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("4. SCOPE LOCK: CURATED UPGRADE & UPSELL PACKAGES", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "To prevent scope creep (where colleges request infinite small custom changes for free), the platform "
        "core is locked from day one. All post-deployment feature upgrades must be purchased as structured packages. "
        "<b>No individual, piece-meal custom requests are accepted.</b>",
        styles["Body"]
    ))

    pkg_data = [
        ["Package", "Key Features Included", "One-Time Cost", "Monthly Maintenance Overhead"],
        ["Pkg 1: Comm & Alerts", "WhatsApp/SMS Integration, Automated Report Card Emails, Parent Alert Logs", "₹15,000 ($200)", "+₹1,000 / month (API usage costs passed directly to client)"],
        ["Pkg 2: Analytics & Exams", "Batch Stats, CGPA Generation Engine, Visual Analytics Charts, PDF Transcripts", "₹25,000 ($300)", "₹0 (Handled by existing compute resource)"],
        ["Pkg 3: Audit & Security", "Advanced RBAC, IP-Whitelisting, Activity Logs, Secure Cold Storage Backups", "₹20,000 ($250)", "+₹500 / month (Storage expansion costs)"],
    ]
    story.append(section_table(
        [["Upsell Package Name", "Features Included", "Implementation Fee", "Ongoing Cost"]] + pkg_data,
        [100, 190, 85, 90]
    ))

    # ════════════════════ SECTION 5: PITCH SCRIPT ════════════════════
    story.append(PageBreak())
    story.append(Paragraph("5. CLIENT PITCH & EXPLAINER SCRIPT", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "Use this verbal framework when presenting the business model to college principals, trustees, "
        "or tech directors. It translates technical hosting jargon into plain commercial value.",
        styles["Body"]
    ))

    pitch_style = ParagraphStyle("PitchBox", parent=styles["BodyItalic"], textColor=colors.HexColor("#1e293b"))
    
    pitch_text = (
        "<b>\"Good morning team,</b><br/><br/>"
        "When we built this portal, we prioritized two core pillars: <b>absolute data isolation</b> and "
        "<b>predictable scaling</b>. Your college handles over 25,000 active student and academic records. "
        "Storing that on a shared, cheap server risks massive downtime during exam registrations or "
        "result announcements.<br/><br/>"
        "Therefore, we deploy your system on its own <b>dedicated cloud container</b>. Your data never mixes with "
        "any other institution, ensuring absolute compliance and security.<br/><br/>"
        "We offer this under a completely transparent billing model. For a flat annual subscription, "
        "we handle the server costs, the database indexing, maintenance, and regular security updates. "
        "You don’t need an internal IT team to maintain servers; we handle it all seamlessly in the background.<br/><br/>"
        "Furthermore, to ensure the absolute stability of the platform, our core system is fully complete from day one. "
        "If your institution grows and requires advanced features like automated WhatsApp engines or audit logging, "
        "we offer these via curated <b>Upgrade Packages</b>. This guarantees that your platform scales smoothly "
        "without unexpected, messy development delays.<b>\"</b>"
    )

    approval = [[Paragraph(pitch_text, pitch_style)]]
    at = Table(approval, colWidths=[W-10])
    at.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, GOLD),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
    ]))
    story.append(at)

    # ════════════════════ SECTION 6: JUDGE Q&A ════════════════════
    story.append(Spacer(1, 10))
    story.append(Paragraph("6. HACKATHON DEFENSE & JUDGE'S Q&A", styles["SectionHead"]))
    story.append(HRFlowable(width="100%", thickness=1, color=NAVY))
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "Anticipate these technical and commercial questions from hackathon judges, and use the precise "
        "defense scripts to validate your decisions.",
        styles["Body"]
    ))

    qa_list = [
        ("Why choose separate deployments instead of a shared database? Isn't multi-tenancy cheaper?",
         "While a shared multi-tenant database reduces initial infrastructure costs, it introduces significant risks for educational institutions. First, data privacy: colleges are highly sensitive about student data records mixing with competitors. Second, noisy neighbor issues: if College A runs a massive query or data import of 25,000 rows, it won't degrade performance for College B. Third, customization: isolated deployments allow us to easily apply specific college-level configurations without rewriting global database schemas."),
        ("25,000 records per college can slow down a database tier during peak traffic. How does your stack handle spikes?",
         "Our Standard Tier architecture utilizes optimized relational indexing on fields like student_id and academic_year. For heavy read operations—like checking results—we decouple the web server from the database using connection pooling (like PgBouncer). If traffic spikes excessively, our architecture allows us to scale up compute instances vertically within minutes without touching or breaking the database."),
        ("What happens if a college insists on a minor custom feature not in your packages?",
         "To maintain product profitability and a clean codebase, we explicitly do not support one-off custom code modification. If a college requests an unlisted feature, we evaluate its utility. If it benefits other colleges, we roadmap it into a new feature package. If it is highly specific to them, we offer them a dedicated 'Enterprise Customization' tier billed at premium development hours, ensuring our engineering time is fully compensated."),
        ("If hosting is ~$45/mo and you charge ₹65,000/year, what happens if data volume doubles?",
         "Our database selection (Supabase/PostgreSQL) can scale efficiently way past 25,000 rows into millions of rows before requiring significantly higher storage tiers. If data volume doubles, our hosting expense might increase by $5–$10/month for storage blocks, but our pricing models already include an 80%+ profit margin buffer to absorb these incremental operational scaling costs easily.")
    ]

    for q, a in qa_list:
        story.append(Paragraph(f"<b>Q: {q}</b>", styles["SubHead"]))
        story.append(Paragraph(f"<b>Answer:</b> {a}", styles["Body"]))
        story.append(Spacer(1, 4))

    # Build
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"✅ Business Report generated: {OUTPUT_PATH}")
    return OUTPUT_PATH


if __name__ == "__main__":
    build_report()
