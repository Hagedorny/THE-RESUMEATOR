"""
PDF Resume Generator
Generates a clean resume PDF from structured JSON data.
Uses reportlab for precise control over fonts, spacing, and positioning.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, KeepTogether
)
from reportlab.lib.colors import black, HexColor
from io import BytesIO


FONT_NAME = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

STYLES = {
    "name": ParagraphStyle(
        "name",
        fontName=FONT_BOLD,
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=2,
    ),
    "contact": ParagraphStyle(
        "contact",
        fontName=FONT_NAME,
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        spaceAfter=6,
    ),
    "section_header": ParagraphStyle(
        "section_header",
        fontName=FONT_BOLD,
        fontSize=11,
        leading=14,
        spaceBefore=8,
        spaceAfter=3,
        textColor=black,
    ),
    "job_title": ParagraphStyle(
        "job_title",
        fontName=FONT_BOLD,
        fontSize=10,
        leading=13,
        spaceBefore=4,
        spaceAfter=1,
    ),
    "body": ParagraphStyle(
        "body",
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        spaceAfter=2,
    ),
    "bullet": ParagraphStyle(
        "bullet",
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        leftIndent=18,
        firstLineIndent=-12,
        spaceAfter=1,
    ),
    "skills": ParagraphStyle(
        "skills",
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        spaceAfter=2,
    ),
}


def _section_line():
    return HRFlowable(
        width="100%", thickness=0.5, color=HexColor("#999999"),
        spaceBefore=0, spaceAfter=4
    )


def generate_resume_pdf(resume_data: dict) -> bytes:
    """Generate a PDF matching the Google Docs resume layout. Returns PDF bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    story = []

    # Name
    story.append(Paragraph(resume_data["name"], STYLES["name"]))

    # Contact line
    contact = resume_data.get("contact", {})
    contact_parts = []
    if contact.get("email"):
        contact_parts.append(contact["email"])
    if contact.get("website"):
        contact_parts.append(contact["website"])
    if contact.get("portfolio"):
        contact_parts.append(contact["portfolio"])
    if contact.get("phone"):
        contact_parts.append(contact["phone"])
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), STYLES["contact"]))

    # Professional Summary
    story.append(Paragraph("Professional Summary", STYLES["section_header"]))
    story.append(_section_line())
    summary = resume_data.get("professional_summary", "")
    story.append(Paragraph(summary, STYLES["body"]))

    # Core Skills
    story.append(Paragraph("Core Skills", STYLES["section_header"]))
    story.append(_section_line())
    skills = resume_data.get("core_skills", [])
    if skills:
        skills_text = " &#8226; ".join(skills)
        story.append(Paragraph(skills_text, STYLES["skills"]))

    # Professional Experience
    story.append(Paragraph("Professional Experience", STYLES["section_header"]))
    story.append(_section_line())
    for exp in resume_data.get("experience", []):
        exp_block = []
        title_line = f"<b>{exp['title']}</b>"
        if exp.get("company"):
            title_line += f" | {exp['company']}"
        title_line += f" | {exp['dates']}"
        exp_block.append(Paragraph(title_line, STYLES["job_title"]))
        for bullet in exp.get("bullets", []):
            exp_block.append(Paragraph(f"&#8226; {_clean(bullet)}", STYLES["bullet"]))
        story.append(KeepTogether(exp_block))
        story.append(Spacer(1, 2))

    # Certifications
    cert_block = []
    cert_block.append(Paragraph("Certifications", STYLES["section_header"]))
    cert_block.append(_section_line())
    for cert in resume_data.get("certifications", []):
        cert_block.append(Paragraph(cert, STYLES["body"]))
    story.append(KeepTogether(cert_block))

    # Education
    edu_block = []
    edu_block.append(Paragraph("Education", STYLES["section_header"]))
    edu_block.append(_section_line())
    for edu in resume_data.get("education", []):
        edu_line = f"<b>{edu['degree']}</b> | {edu['school']}"
        edu_block.append(Paragraph(edu_line, STYLES["body"]))
    story.append(KeepTogether(edu_block))

    # Technical Projects
    proj_section_block = []
    proj_section_block.append(Paragraph("Technical Projects", STYLES["section_header"]))
    proj_section_block.append(_section_line())
    for proj in resume_data.get("technical_projects", []):
        proj_section_block.append(Paragraph(f"<b>{proj['name']}</b>", STYLES["job_title"]))
        for bullet in proj.get("bullets", []):
            proj_section_block.append(Paragraph(f"&#8226; {_clean(bullet)}", STYLES["bullet"]))
        proj_section_block.append(Spacer(1, 2))
    story.append(KeepTogether(proj_section_block))

    doc.build(story)
    return buf.getvalue()


def generate_cover_letter_pdf(
    cover_letter_text: str,
    resume_data: dict,
    hiring_manager: str = "",
    closing_phrase: str = "Sincerely,",
    closing_name: str = "",
    closing_contact_lines: list | None = None,
) -> bytes:
    """Generate a clean cover letter PDF. Returns PDF bytes."""
    from datetime import date as _date

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=1.0 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=1.0 * inch,
        rightMargin=1.0 * inch,
    )

    cl_body = ParagraphStyle(
        "cl_body",
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=15,
        spaceAfter=10,
    )
    cl_date = ParagraphStyle(
        "cl_date",
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=14,
        spaceAfter=14,
    )
    cl_closing_line = ParagraphStyle(
        "cl_closing_line",
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=14,
        spaceAfter=4,
    )

    story = []

    # Date — left aligned
    story.append(Paragraph(_date.today().strftime("%B %d, %Y"), cl_date))

    # Salutation
    salutation = f"Dear {hiring_manager}," if hiring_manager.strip() else "Dear Hiring Manager,"
    story.append(Paragraph(_clean(salutation), cl_body))

    # Letter body — split on double newlines
    paragraphs = [p.strip() for p in cover_letter_text.split("\n\n") if p.strip()]

    # Strip any salutation the AI may have included at the start
    if paragraphs and paragraphs[0].lower().startswith("dear "):
        paragraphs = paragraphs[1:]

    for para in paragraphs:
        story.append(Paragraph(_clean(para.replace("\n", " ")), cl_body))

    # Closing block — all left-aligned, each item on its own line
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(_clean(closing_phrase or "Sincerely,"), cl_closing_line))
    story.append(Spacer(1, 0.25 * inch))

    name = closing_name or resume_data.get("name", "")
    if name:
        story.append(Paragraph(_clean(name), cl_closing_line))

    contact = resume_data.get("contact", {})
    lines = closing_contact_lines if closing_contact_lines is not None else [
        p for p in [contact.get("email"), contact.get("phone"), contact.get("website")] if p
    ]
    for line in lines:
        if line.strip():
            story.append(Paragraph(_clean(line.strip()), cl_closing_line))

    doc.build(story)
    return buf.getvalue()


def _clean(text: str) -> str:
    """Clean text for reportlab XML parsing."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
