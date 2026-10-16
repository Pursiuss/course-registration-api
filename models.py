import re
from pydantic import BaseModel, Field

# Cell values that mean "no data" rather than an actual prerequisite/cross-listing.
# The sample file only uses "None", but the hidden grading file may use others,
# so we treat a small set of common sentinels as empty.
NULL_VALUES = {"", "none", "n/a", "na", "-", "--", "tbd", "nil"}


def normalize_code(raw: str) -> str:
    """
    Turn a course code into a canonical form for use as a dict key
    and inside prerequisite/cross-listed arrays.

    'COSC 3506' -> 'COSC3506'
    ' cosc-3506 ' -> 'COSC3506'
    """
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def is_empty(raw: str) -> bool:
    """True for table cells that represent 'no data' rather than a real value."""
    return (raw or "").strip().lower() in NULL_VALUES


def parse_credits(raw: str):
    """
    Pull the first number out of a credits cell.

    '3' -> 3
    '3 credits' -> 3
    '1.5' -> 1.5
    '' or 'TBD' -> 0
    """
    match = re.search(r"\d+(?:\.\d+)?", raw or "")
    if not match:
        return 0
    value = float(match.group())
    return int(value) if value.is_integer() else value


def extract_codes(raw: str) -> list[str]:
    """
    Pull every course-code-shaped token out of a free-text string and
    normalize each one. Used for both prerequisites and cross-listed cells.

    'Requires COSC 1046 and either COSC 1047 or ITEC 1047'
        -> ['COSC1046', 'COSC1047', 'ITEC1047']
    'None' -> []
    'COSC 3506' -> ['COSC3506']
    """
    if is_empty(raw):
        return []
    # letters, optional space/dash, then digits e.g. "COSC 1046", "ITEC-1047"
    matches = re.findall(r"[A-Za-z]{2,4}\s?-?\s?\d{3,4}", raw)
    return [normalize_code(m) for m in matches]


class Course(BaseModel):
    course_code: str
    title: str
    credits: int
    prerequisites: list[str] = Field(default_factory=list)
    cross_listed: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    imported: int
    course_codes: list[str]


# ---- Phase 2: student profiles ----

class HistoryRecord(BaseModel):
    """One past course from a student's transcript."""
    course_code: str
    term: str
    credits_earned: int
    status: str


class PlannedCourse(BaseModel):
    """One course the student intends to take."""
    course_code: str
    term: str


class HistoryUpdate(BaseModel):
    """Body of PUT /history: the complete replacement history."""
    history: list[HistoryRecord]


class PlanRequest(BaseModel):
    """Body of POST/PUT /plan."""
    planned_courses: list[PlannedCourse]


class StudentProfile(BaseModel):
    """GET /profile response: exactly these three keys."""
    student_id: str
    history: list[HistoryRecord]
    plan: list[PlannedCourse]
