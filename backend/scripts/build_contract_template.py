"""Генерирует шаблон backend/templates/service_contract_kz.docx для docxtpl.

Текст договора фиксированный (Deterministic Core): LLM в его создании не
участвует, в шаблон подставляются только проверенные Pydantic-значения.
Перед реальным использованием текст должен проверить юрист.

Запуск из папки backend: ``.venv\\Scripts\\python scripts\\build_contract_template.py``
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

OUT = Path(__file__).resolve().parents[1] / "templates" / "service_contract_kz.docx"

SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. ПРЕДМЕТ ДОГОВОРА",
        [
            "1.1. Исполнитель обязуется по заданию Заказчика оказать следующие услуги: {{ scope_of_work }} "
            "(далее — «Услуги»), а Заказчик обязуется принять и оплатить Услуги на условиях настоящего Договора.",
            "1.2. Срок оказания Услуг — до {{ deadline }} включительно.",
        ],
    ),
    (
        "2. СТОИМОСТЬ УСЛУГ И ПОРЯДОК РАСЧЁТОВ",
        [
            "2.1. Стоимость Услуг по настоящему Договору составляет {{ amount }} {{ currency_name }}.",
            "2.2. Оплата производится Заказчиком в течение 5 (пяти) банковских дней с даты подписания Сторонами "
            "акта оказанных услуг путём перечисления денежных средств на банковский счёт Исполнителя.",
        ],
    ),
    (
        "3. ПРАВА И ОБЯЗАННОСТИ СТОРОН",
        [
            "3.1. Исполнитель обязан оказать Услуги качественно и в срок, установленный пунктом 1.2 Договора.",
            "3.2. Заказчик обязан своевременно предоставлять Исполнителю информацию, необходимую для оказания "
            "Услуг, принять оказанные Услуги и оплатить их в порядке, установленном разделом 2 Договора.",
        ],
    ),
    (
        "4. ОТВЕТСТВЕННОСТЬ СТОРОН",
        [
            "4.1. За неисполнение или ненадлежащее исполнение обязательств по Договору Стороны несут "
            "ответственность в соответствии с законодательством Республики Казахстан.",
        ],
    ),
    (
        "5. РАЗРЕШЕНИЕ СПОРОВ",
        [
            "5.1. Споры, возникающие из настоящего Договора, разрешаются путём переговоров. При недостижении "
            "согласия спор передаётся на рассмотрение суда в соответствии с законодательством Республики Казахстан.",
        ],
    ),
    (
        "6. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ",
        [
            "6.1. Договор вступает в силу с даты его подписания Сторонами и действует до полного исполнения "
            "Сторонами своих обязательств.",
            "6.2. Договор составлен в двух экземплярах на русском языке, имеющих одинаковую юридическую силу, "
            "по одному экземпляру для каждой из Сторон.",
        ],
    ),
]


def build() -> None:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run("ДОГОВОР ВОЗМЕЗДНОГО ОКАЗАНИЯ УСЛУГ № {{ contract_number }}").bold = True

    place = doc.add_paragraph("г. {{ city }}\t\t\t\t\t\t\t{{ contract_date }}")
    place.alignment = WD_ALIGN_PARAGRAPH.LEFT

    preamble = doc.add_paragraph(
        "{{ executor_name }}, БИН {{ executor_bin }}, именуемое в дальнейшем «Исполнитель», в лице "
        "{{ executor_signatory }}, действующего на основании {{ executor_basis }}, с одной стороны, и "
        "{{ client_name }}, ИИН/БИН {{ client_bin_iin }}, именуемое в дальнейшем «Заказчик», с другой стороны, "
        "совместно именуемые «Стороны», заключили настоящий Договор о нижеследующем:"
    )
    preamble.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    for heading, clauses in SECTIONS:
        h = doc.add_paragraph()
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        h.add_run(heading).bold = True
        for clause in clauses:
            doc.add_paragraph(clause).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run("7. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН").bold = True

    table = doc.add_table(rows=4, cols=2)
    rows = [
        ("Исполнитель:", "Заказчик:"),
        ("{{ executor_name }}", "{{ client_name }}"),
        ("БИН: {{ executor_bin }}", "ИИН/БИН: {{ client_bin_iin }}"),
        ("_______________ / {{ executor_signatory }}", "_______________ / ______________"),
    ]
    for row, (left, right) in zip(table.rows, rows):
        row.cells[0].text = left
        row.cells[1].text = right
    for cell in table.rows[0].cells:
        cell.paragraphs[0].runs[0].bold = True

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(OUT))
    print(f"saved {OUT}")


if __name__ == "__main__":
    build()
