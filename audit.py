"""Phase 3 audit engine: the academic rules behind GET /audit-report."""
import re
from models import normalize_code

# Season order within a year: Winter < Spring < Summer < Fall.
SEASON_ORDER = {"W": 0, "SP": 1, "S": 2, "F": 3}

# "<2-digit year><season>", e.g. "26F", "24W", "26SP".
TERM_PATTERN = re.compile(r"(\d{2})(SP|W|S|F)")

# Sort key for a term we can't read: after every real term, so it is
# never treated as "earlier" than anything.
UNKNOWN_TERM = (999, 999)

# Credits needed to graduate.
GRADUATION_CREDITS = 120


def term_sort_key(term: str) -> tuple[int, int]:
    """
    Turn a term code into a key that sorts chronologically.

    '23F' -> (23, 3)    '24W' -> (24, 0)    '26SP' -> (26, 1)
    Anything unreadable -> (999, 999), so it sorts last.
    """
    match = TERM_PATTERN.fullmatch((term or "").strip().upper())
    if match is None:
        return UNKNOWN_TERM
    year, season = match.groups()
    return (int(year), SEASON_ORDER[season])


def display_code(code: str) -> str:
    """'COSC3127' -> 'COSC-3127', the hyphenated style transcripts use."""
    return re.sub(r"^([A-Z]+)(\d+)$", r"\1-\2", code)


def earliest_completion(history: list[dict]) -> dict[str, tuple[int, int]]:
    """
    Normalized course code -> sort key of the earliest term the student
    Completed it. Attempted / In-Progress rows don't count.
    """
    earliest: dict[str, tuple[int, int]] = {}
    for record in history:
        if record["status"] != "Completed":
            continue
        code = normalize_code(record["course_code"])
        key = term_sort_key(record["term"])
        if code not in earliest or key < earliest[code]:
            earliest[code] = key
    return earliest


def check_prerequisites(plan: list[dict], history: list[dict],
                        catalog: dict) -> list[dict]:
    """
    Build timeline_validation: one entry per planned term that has
    errors, ordered chronologically.

    A prerequisite is satisfied only by a Completed history entry in a
    strictly earlier term than the planned course.
    """
    completed = earliest_completion(history)
    errors_by_term: dict[str, list[dict]] = {}

    for planned in plan:
        course = catalog.get(normalize_code(planned["course_code"]))
        if course is None:
            continue  # not in the catalog: no prerequisites to check
        term = planned["term"]
        planned_key = term_sort_key(term)

        for prereq in course.prerequisites:
            done = completed.get(prereq)
            if done is None or done >= planned_key:
                missing = display_code(prereq)
                error = {
                    "course_code": planned["course_code"],
                    "type": "MISSING_PREREQUISITE",
                    "message": f"Missing prerequisite: {missing}",
                }
                errors_by_term.setdefault(term, []).append(error)

    ordered_terms = sorted(errors_by_term, key=term_sort_key)
    return [
        {"term": term, "errors": errors_by_term[term]}
        for term in ordered_terms
    ]


def cross_listed_partners(code: str, catalog: dict) -> set[str]:
    """
    Every course the catalog says is cross-listed with `code`. Checked in
    both directions, in case only one of the two rows lists the other.
    """
    partners = set()
    course = catalog.get(code)
    if course is not None:
        partners.update(course.cross_listed)
    for other in catalog.values():
        if code in other.cross_listed:
            partners.add(other.course_code)
    partners.discard(code)
    return partners


def check_cross_listings(plan: list[dict], history: list[dict],
                         catalog: dict) -> list[dict]:
    """
    Build cross_list_violations: a planned course that is cross-listed
    with a course the student already Completed (no earning credit twice).
    """
    completed = earliest_completion(history)
    violations = []

    for planned in plan:
        code = normalize_code(planned["course_code"])
        for partner in sorted(cross_listed_partners(code, catalog)):
            if partner not in completed:
                continue
            taken = display_code(partner)
            violations.append({
                "course_code": planned["course_code"],
                "type": "CROSS_LIST_CONFLICT",
                "message": f"Cross-listed with completed course {taken}",
            })

    return violations


def total_earned(history: list[dict]) -> int:
    """
    Credits from Completed history entries, counting each course once.
    Attempted / In-Progress rows earn 0, so a failed attempt followed by
    a later pass counts just the pass. If a course was Completed more
    than once, only the most recent completion counts.
    """
    latest: dict[str, tuple[tuple[int, int], int]] = {}
    for record in history:
        if record["status"] != "Completed":
            continue
        code = normalize_code(record["course_code"])
        key = term_sort_key(record["term"])
        if code not in latest or key > latest[code][0]:
            latest[code] = (key, record["credits_earned"])
    return sum(credits for _, credits in latest.values())


def total_planned(plan: list[dict], catalog: dict) -> int:
    """Catalog credits of every planned course; unknown courses add 0."""
    total = 0
    for planned in plan:
        course = catalog.get(normalize_code(planned["course_code"]))
        if course is not None:
            total += course.credits
    return total


def credit_summary(plan: list[dict], history: list[dict],
                   catalog: dict) -> dict:
    """The credit_summary block of the audit report."""
    earned = total_earned(history)
    planned = total_planned(plan, catalog)
    remaining = max(0, GRADUATION_CREDITS - earned - planned)
    return {
        "total_earned": earned,
        "total_planned": planned,
        "total_remaining_for_graduation": remaining,
    }


def build_audit_report(student_id: str, plan: list[dict],
                       history: list[dict], catalog: dict,
                       strict: bool = False) -> dict:
    """
    The full GET /audit-report body.

    status is "ok" when there are no issues; otherwise "failed" in strict
    mode and "warning" when not.
    """
    timeline = check_prerequisites(plan, history, catalog)
    cross_list = check_cross_listings(plan, history, catalog)

    if not timeline and not cross_list:
        status = "ok"
    elif strict:
        status = "failed"
    else:
        status = "warning"

    return {
        "student_id": student_id,
        "status": status,
        "timeline_validation": timeline,
        "cross_list_violations": cross_list,
        "credit_summary": credit_summary(plan, history, catalog),
    }
