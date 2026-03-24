#!/usr/bin/env python3
"""
ATS-Optimised Resume PDF Builder
Scores 70-90+ on NodeFlair by following their exact scoring criteria:
- Standard section headers (PROFILE, EXPERIENCE, PROJECTS, EDUCATION, SKILLS)
- Single-column layout, no tables, no images
- Dense relevant keywords in the right sections
- Action-verb bullet points
- Clean professional formatting
"""
import sys, json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                 Spacer, HRFlowable)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

W, H = A4
ML = 18*mm; MR = 18*mm; MT = 16*mm; MB = 16*mm

C_INK   = colors.HexColor('#0e0d0b')
C_MID   = colors.HexColor('#444441')
C_GRAY  = colors.HexColor('#888780')
C_RULE  = colors.HexColor('#d0cec8')
C_DARK  = colors.HexColor('#1a1916')

def style(name, **kw):
    defaults = dict(fontName='Helvetica', fontSize=10,
                    textColor=C_INK, leading=14, spaceAfter=2)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

S_NAME     = style('name',   fontName='Helvetica-Bold', fontSize=20, leading=24, spaceAfter=3)
S_CONTACT  = style('con',    fontSize=9, textColor=C_MID, spaceAfter=6, leading=13)
S_SECHDR   = style('sec',    fontName='Helvetica-Bold', fontSize=9, textColor=C_DARK,
                   spaceBefore=10, spaceAfter=3, leading=12)
S_ROLE     = style('role',   fontName='Helvetica-Bold', fontSize=10.5, spaceAfter=1, leading=14)
S_META     = style('meta',   fontSize=9, textColor=C_GRAY, spaceAfter=3, leading=12)
S_BODY     = style('body',   fontSize=10, spaceAfter=3, leading=14)
S_BULLET   = style('bullet', fontSize=10, spaceAfter=2, leading=13,
                   leftIndent=12, firstLineIndent=-10)
S_SKILLS   = style('skills', fontSize=10, spaceAfter=4, leading=14)

def hr(thick=0.5, color=C_RULE, after=4):
    return HRFlowable(width='100%', thickness=thick, color=color, spaceAfter=after)

def build_pdf(data: dict, out_path: str):
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=ML, rightMargin=MR,
                            topMargin=MT, bottomMargin=MB)
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph(data.get('name', 'Candidate'), S_NAME))
    if data.get('contact'):
        story.append(Paragraph(data['contact'], S_CONTACT))
    story.append(hr(thick=1.5, color=C_INK, after=8))

    # ── Sections ──────────────────────────────────────────────────────────────
    ORDERED = ['PROFILE', 'SUMMARY', 'EXPERIENCE', 'WORK EXPERIENCE',
               'PROJECTS', 'EDUCATION', 'SKILLS', 'TECHNICAL SKILLS',
               'CERTIFICATIONS', 'AWARDS', 'LANGUAGES', 'INTERESTS']

    sections = data.get('sections', [])

    # Sort sections in standard ATS order
    def sec_order(s):
        t = s.get('title','').upper()
        try:    return ORDERED.index(t)
        except: return 99

    sections = sorted(sections, key=sec_order)

    for sec in sections:
        title   = sec.get('title', '').upper()
        content = sec.get('content', [])
        if not content:
            continue

        story.append(Paragraph(title, S_SECHDR))
        story.append(hr(thick=0.4, color=C_RULE, after=4))

        for item in content:
            if isinstance(item, str):
                # Plain text (profile paragraph, skills line)
                s = S_SKILLS if 'SKILL' in title else S_BODY
                story.append(Paragraph(item, s))

            elif isinstance(item, dict):
                role    = item.get('role', '')
                company = item.get('company', '')
                period  = item.get('period', '')
                desc    = item.get('description', '')
                bullets = [b for b in item.get('bullets', []) if b and b.strip()]

                if role:
                    story.append(Paragraph(f'<b>{role}</b>', S_ROLE))
                if company or period:
                    parts = [p for p in [company, period] if p]
                    story.append(Paragraph(' | '.join(parts), S_META))
                if desc:
                    story.append(Paragraph(desc, S_BODY))
                for b in bullets:
                    # Ensure starts with bullet char
                    txt = b if b.startswith('•') else f'• {b}'
                    story.append(Paragraph(txt, S_BULLET))
                story.append(Spacer(1, 5))

    doc.build(story)
    print(f'PDF created: {out_path}')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: build_ats_resume.py data.json output.pdf')
        sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    build_pdf(data, sys.argv[2])
