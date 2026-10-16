import re
from bs4 import BeautifulSoup

# Statuses that mean the student actually took (or is taking) the course.
# "Fulfilled" and "Planned" rows are requirement placeholders, not history.
PAST_STATUSES = {"Completed", "In-Progress", "Attempted"}

# Column order inside each transcript table:
# Status | Course | (title) | Grade | Term | Credits
STATUS_COL, COURSE_COL, GRADE_COL, TERM_COL, CREDITS_COL = 0, 1, 3, 4, 5


def _is_course_table(table) -> bool:
    """True if this <table>'s header row has the transcript columns."""
    headers = {th.get_text(strip=True) for th in table.find_all("th")}
    return {"Status", "Course", "Credits"} <= headers


def _parse_credits(raw: str) -> int:
    """Credits cell as an integer; 0 if blank or non-numeric (e.g. a failed lab)."""
    try:
        return int(raw)
    except ValueError:
        return 0


def _grade_rank(grade: str) -> tuple:
    """
    How informative a grade is, for picking between duplicate rows.
    A numeric grade beats a letter grade, which beats P/blank.

    '78' -> (2, 78.0)    'B+' -> (1, 0.0)    'P' or '' -> (0, 0.0)
    """
    grade = (grade or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?", grade):
        return (2, float(grade))
    if re.fullmatch(r"[A-EF][+-]?", grade, re.I):
        return (1, 0.0)
    return (0, 0.0)


def parse_transcript(html_bytes: bytes) -> list[dict]:
    """
    Extract a student's past courses from a transcript HTML export.

    A row counts when its Status is Completed/In-Progress/Attempted and its
    Term cell is non-empty. The export repeats courses under several
    requirement tables, so rows are deduplicated by (course_code, term),
    keeping the one with the most informative grade, then the higher credits.

    Each record: {"course_code", "term", "credits_earned", "status"}
    """
    soup = BeautifulSoup(html_bytes, "html.parser")

    # (course_code, term) -> (rank used for dedup, record)
    best: dict[tuple, tuple] = {}

    for table in soup.find_all("table"):
        if not _is_course_table(table):
            continue

        for row in table.find_all("tr"):
            # Header rows use <th>, so they have no <td> cells and get skipped.
            cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
            if len(cells) <= CREDITS_COL:
                continue

            status = cells[STATUS_COL]
            course_code = cells[COURSE_COL]
            term = cells[TERM_COL]

            if not course_code or status not in PAST_STATUSES or not term:
                continue

            record = {
                "course_code": course_code,
                "term": term,
                "credits_earned": _parse_credits(cells[CREDITS_COL]),
                "status": status,
            }
            rank = (_grade_rank(cells[GRADE_COL]), record["credits_earned"])

            key = (course_code, term)
            if key not in best or rank > best[key][0]:
                best[key] = (rank, record)

    return [record for _, record in best.values()]
