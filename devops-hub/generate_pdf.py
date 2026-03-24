#!/usr/bin/env python3
"""
generate_pdf.py  — called by server.js to produce a PDF resume
Usage: python3 generate_pdf.py <input_json_path> <output_pdf_path>
"""
import sys, json
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

def build_pdf(data: dict, out_path: str):
    name     = data.get("name", "Candidate")
    contact  = data.get("contact", "")
    sections = data.get("sections", [])

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=16*mm
    )

    INK   = colors.HexColor("#0e0d0b")
    MID   = colors.HexColor("#5a5850")
    LIGHT = colors.HexColor("#9c9890")
    RULE  = colors.HexColor("#d4d2cc")

    name_style = ParagraphStyle("Name",
        fontName="Helvetica-Bold", fontSize=20,
        textColor=INK, spaceAfter=2, alignment=TA_LEFT)

    contact_style = ParagraphStyle("Contact",
        fontName="Helvetica", fontSize=9,
        textColor=MID, spaceAfter=6, alignment=TA_LEFT)

    section_style = ParagraphStyle("Section",
        fontName="Helvetica-Bold", fontSize=9,
        textColor=INK, spaceBefore=10, spaceAfter=3,
        textTransform="uppercase", letterSpacing=0.8)

    body_style = ParagraphStyle("Body",
        fontName="Helvetica", fontSize=10,
        textColor=INK, spaceAfter=4, leading=14)

    bullet_style = ParagraphStyle("Bullet",
        fontName="Helvetica", fontSize=10,
        textColor=INK, spaceAfter=3, leading=14,
        leftIndent=12, bulletIndent=0)

    story = []

    story.append(Paragraph(name, name_style))
    if contact:
        story.append(Paragraph(contact, contact_style))
    story.append(HRFlowable(width="100%", thickness=1, color=INK, spaceAfter=6))

    for sec in sections:
        title   = sec.get("title", "")
        content = sec.get("content", [])

        story.append(Paragraph(title, section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=4))

        for item in content:
            if isinstance(item, dict):
                role    = item.get("role", "")
                company = item.get("company", "")
                period  = item.get("period", "")
                bullets = item.get("bullets", [])
                if role or company:
                    hdr = f"<b>{role}</b>  <font color='#5a5850'>{company}</font>"
                    if period:
                        hdr += f"  <font color='#9c9890' size=9>{period}</font>"
                    story.append(Paragraph(hdr, body_style))
                for b in bullets:
                    story.append(Paragraph(f"• {b}", bullet_style))
                story.append(Spacer(1, 3))
            else:
                # plain string
                story.append(Paragraph(str(item), body_style))

    doc.build(story)
    print("PDF written:", out_path)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: generate_pdf.py <json_path> <pdf_path>"); sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    build_pdf(data, sys.argv[2])
