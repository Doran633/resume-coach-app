from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from sqlalchemy.orm import Session

from .. import models, schemas
from .generation_service import get_generation_payload


BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ACCENT = "2F5597"
BODY_FONT = "Microsoft YaHei"


def _font(run, size: float, bold: bool = False, color: str | None = None) -> None:
    run.font.name = BODY_FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _p(doc: Document, text: str = "", size: float = 9.2, bold: bool = False, color: str | None = None):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.line_spacing = 1.0
    if text:
        run = paragraph.add_run(text)
        _font(run, size, bold, color)
    return paragraph


def _border(paragraph, color: str = ACCENT) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        p_pr.append(borders)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def _heading(doc: Document, text: str) -> None:
    paragraph = _p(doc, text, 14, True, ACCENT)
    paragraph.paragraph_format.space_before = Pt(7)
    _border(paragraph)


def _bullet(doc: Document, text: str, level: int = 0, bold_label: bool = False) -> None:
    paragraph = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    paragraph.paragraph_format.space_after = Pt(1)
    paragraph.paragraph_format.left_indent = Cm(0.45 + level * 0.35)
    if bold_label and "：" in text:
        label, rest = text.split("：", 1)
        run = paragraph.add_run(label + "：")
        _font(run, 9.2, True)
        run = paragraph.add_run(rest)
        _font(run, 9.2)
    else:
        run = paragraph.add_run(text)
        _font(run, 9.2)


def _setup(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.15)
    section.bottom_margin = Cm(1.15)
    section.left_margin = Cm(1.35)
    section.right_margin = Cm(1.35)
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    normal.font.size = Pt(9.2)


def _next_path(prefix: str) -> Path:
    version = 1
    for path in OUTPUT_DIR.glob(f"v*-{prefix}.docx"):
        try:
            version = max(version, int(path.name[1:4]) + 1)
        except ValueError:
            continue
    return OUTPUT_DIR / f"v{version:03d}-{prefix}.docx"


def create_docx(db: Session, request: schemas.DocxCreate) -> schemas.DocxResponse | None:
    payload = get_generation_payload(db, request.generation_result_id)
    if not payload:
        return None

    doc = Document()
    _setup(doc)
    title = _p(doc, "个人简历", 18, True)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    info = payload.resume_sections.personal_info
    table = doc.add_table(rows=1, cols=2)
    left, right = table.rows[0].cells
    left.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for idx, line in enumerate(
        [
            f"姓名：{info.get('姓名', '[待填写]')} · 求职意向：{info.get('求职意向', '[待填写]')}",
            f"邮箱：{info.get('邮箱', '[待填写]')} · 手机号：{info.get('手机号', '[待填写]')}",
        ]
    ):
        paragraph = left.paragraphs[0] if idx == 0 else left.add_paragraph()
        run = paragraph.add_run(line)
        _font(run, 9.5, idx == 0)
    photo = right.paragraphs[0]
    photo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = photo.add_run("[照片：待插入]")
    _font(run, 9, True, "666666")

    _heading(doc, "教育经历")
    edu = payload.resume_sections.education
    _p(doc, f"学校：{edu.get('学校', '[待填写]')} | 专业：{edu.get('专业', '[待填写]')} | 学历：{edu.get('学历', '[待填写]')} | 时间：{edu.get('时间', '[待填写]')}")

    _heading(doc, "个人优势")
    for item in payload.resume_sections.summary:
        _bullet(doc, item)

    _heading(doc, "技能与能力")
    for item in payload.resume_sections.skills:
        _bullet(doc, item)

    _heading(doc, "项目经历")
    for project in payload.resume_sections.projects:
        _p(doc, f"{project.get('name')} | {project.get('meta')} | {project.get('time')}", 11, True, "1F3763")
        _bullet(doc, "项目简介：" + project.get("intro", ""), bold_label=True)
        _bullet(doc, "我的职责：" + project.get("role", ""), bold_label=True)
        _bullet(doc, "技术细节：", bold_label=True)
        for detail in project.get("details", []):
            _bullet(doc, detail, level=1)

    _heading(doc, "面试准备清单")
    for item in payload.resume_sections.interview_preparation:
        _bullet(doc, item)

    path = _next_path("resume-coach-v0")
    doc.save(path)

    row = models.GeneratedFile(
        generation_result_id=request.generation_result_id,
        file_type="docx",
        file_path=str(path),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.DocxResponse(
        file_id=row.id,
        file_name=path.name,
        download_url=f"/api/files/{row.id}",
    )
