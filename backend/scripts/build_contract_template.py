"""backend/templates/service_contract_kz.docx шаблонын docxtpl үшін жасайды.

Келісімшарт мәтіні тіркелген (Deterministic Core): оны жасауға LLM
қатыспайды, шаблонға тек Pydantic тексерген мәндер қойылады.
Нақты қолданар алдында мәтінді заңгер тексеруі керек.

Іске қосу ``backend`` папкасынан: ``.venv\\Scripts\\python scripts\\build_contract_template.py``
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

OUT = Path(__file__).resolve().parents[1] / "templates" / "service_contract_kz.docx"

SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. КЕЛІСІМШАРТ НЫСАНЫ",
        [
            "1.1. Орындаушы Тапсырыс берушінің тапсырмасы бойынша мынадай қызметтерді көрсетуге міндеттенеді: {{ scope_of_work }} "
            "(бұдан әрі — «Қызметтер»), ал Тапсырыс беруші осы Келісімшарттың талаптарында Қызметтерді қабылдап, төлеуге міндеттенеді.",
            "1.2. Қызметтерді көрсету мерзімі — {{ deadline }} қоса алғанда.",
        ],
    ),
    (
        "2. ҚЫЗМЕТТЕРДІҢ ҚҰНЫ ЖӘНЕ ЕСЕП АЙЫРЫСУ ТӘРТІБІ",
        [
            "2.1. Осы Келісімшарт бойынша Қызметтердің құны {{ amount }} {{ currency_name }} құрайды.",
            "2.2. Төлемді Тапсырыс беруші Тараптар көрсетілген қызметтер актісіне қол қойған күннен бастап 5 (бес) банк күні ішінде "
            "ақшаны Орындаушының банк шотына аудару арқылы жүргізеді.",
        ],
    ),
    (
        "3. ТАРАПТАРДЫҢ ҚҰҚЫҚТАРЫ МЕН МІНДЕТТЕРІ",
        [
            "3.1. Орындаушы Қызметтерді Келісімшарттың 1.2-тармағында белгіленген мерзімде және сапалы көрсетуге міндетті.",
            "3.2. Тапсырыс беруші Қызметтерді көрсету үшін қажетті ақпаратты Орындаушыға уақтылы беруге, "
            "көрсетілген Қызметтерді қабылдауға және оларды Келісімшарттың 2-бөлімінде белгіленген тәртіппен төлеуге міндетті.",
        ],
    ),
    (
        "4. ТАРАПТАРДЫҢ ЖАУАПКЕРШІЛІГІ",
        [
            "4.1. Келісімшарт бойынша міндеттемелерді орындамағаны немесе тиісінше орындамағаны үшін Тараптар "
            "Қазақстан Республикасының заңнамасына сәйкес жауапкершілік көтереді.",
        ],
    ),
    (
        "5. ДАУЛАРДЫ ШЕШУ",
        [
            "5.1. Осы Келісімшартта туындайтын даулар келіссөздер жолымен шешіледі. Келісімге қол жеткізілмеген жағдайда "
            "дау Қазақстан Республикасының заңнамасына сәйкес сотқа қарауға беріледі.",
        ],
    ),
    (
        "6. ҚОРЫТЫНДЫ ЕРЕЖЕЛЕР",
        [
            "6.1. Келісімшарт Тараптар оған қол қойған күннен бастап күшіне енеді және Тараптар өз міндеттемелерін "
            "толық орындағанға дейін қолданылады.",
            "6.2. Келісімшарт қазақ тілінде екі данада жасалды, екі дананың заңды күші бірдей, "
            "әр Тарапқа бір-бірден.",
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
    title.add_run("ӨТЕУЛІ ҚЫЗМЕТ КӨРСЕТУ КЕЛІСІМШАРТЫ № {{ contract_number }}").bold = True

    place = doc.add_paragraph("{{ city }} қ.\t\t\t\t\t\t\t{{ contract_date }}")
    place.alignment = WD_ALIGN_PARAGRAPH.LEFT

    preamble = doc.add_paragraph(
        "{{ executor_name }}, БСН {{ executor_bin }}, бұдан әрі «Орындаушы» деп аталатын, атынан "
        "{{ executor_signatory }}, {{ executor_basis }} негізінде әрекет ететін, бір жағынан, және "
        "{{ client_name }}, ЖСН/БСН {{ client_bin_iin }}, бұдан әрі «Тапсырыс беруші» деп аталатын, екінші жағынан, "
        "бұдан әрі бірлесіп «Тараптар» деп аталатындар, төмендегілер туралы осы Келісімшартты жасасты:"
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
    h.add_run("7. ТАРАПТАРДЫҢ ДЕРЕКТЕМЕЛЕРІ МЕН ҚОЛДАРЫ").bold = True

    table = doc.add_table(rows=4, cols=2)
    rows = [
        ("Орындаушы:", "Тапсырыс беруші:"),
        ("{{ executor_name }}", "{{ client_name }}"),
        ("БСН: {{ executor_bin }}", "ЖСН/БСН: {{ client_bin_iin }}"),
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
