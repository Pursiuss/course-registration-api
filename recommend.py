"""
Phase 4 recommendations: a term-by-term pathway to graduation.

The catalog is a Directed Acyclic Graph: an edge A -> B means "A is a
prerequisite of B". Kahn's algorithm takes it apart level by level:
every course with no prerequisites left to take goes in the next term,
then those courses are crossed off, which frees up the next level.

Pure functions (no FastAPI), like audit.py, so they're easy to unit-test.
"""
from datetime import date

from audit import (
    SEASON_ORDER, UNKNOWN_TERM, term_sort_key, display_code, cross_listed_partners,
)
from models import normalize_code

FALL = SEASON_ORDER["F"]
WINTER = SEASON_ORDER["W"]
SEASON_LETTER = {number: letter for letter, number in SEASON_ORDER.items()}


def next_term(term: tuple[int, int]) -> tuple[int, int]:
    """The next regular term (Fall/Winter; summers are skipped).

    (26, F) -> (27, W)    (27, W) -> (27, F)    (26, S) -> (26, F)
    """
    year, season = term
    if season == FALL:
        return (year + 1, WINTER)
    return (year, FALL)


def term_label(term: tuple[int, int]) -> str:
    """(27, W) -> '27W', the same style transcripts use."""
    year, season = term
    return f"{year:02d}{SEASON_LETTER[season]}"


def first_term(history: list[dict], today: date | None = None) -> tuple[int, int]:
    """The term after the student's latest transcript term. With no
    readable terms, the next term after today's date instead."""
    known = [term_sort_key(record["term"]) for record in history]
    known = [key for key in known if key != UNKNOWN_TERM]
    if known:
        return next_term(max(known))
    today = today or date.today()
    current = (today.year % 100, FALL if today.month >= 9 else WINTER)
    return next_term(current)


def build_pathway(history: list[dict], catalog: dict) -> list[dict]:
    """
    Schedule every catalog course the student hasn't Completed, one Kahn
    level per term, so each prerequisite lands in an earlier term than
    the courses that need it.

    Also skipped: a course cross-listed with a completed one. It's the same
    course under another code (audit-report would flag taking it), so it
    also counts as done when another course lists it as a prerequisite.

    A course is left out if it can never be scheduled: a prerequisite
    that's neither done nor in the catalog, or a prerequisite cycle.
    """
    completed = {
        normalize_code(record["course_code"])
        for record in history
        if record["status"] == "Completed"
    }
    done = completed | {
        code for code in catalog if cross_listed_partners(code, catalog) & completed
    }
    remaining = {code: c for code, c in catalog.items() if code not in done}

    # in_degree[B]: how many of B's prerequisites are still to be taken.
    # dependents[A]: the courses that list A as a prerequisite.
    in_degree: dict[str, int] = {}
    dependents: dict[str, list[str]] = {code: [] for code in remaining}
    for code, course in remaining.items():
        needed = set(course.prerequisites) - done
        in_degree[code] = len(needed)
        for prereq in needed:
            if prereq in dependents:
                dependents[prereq].append(code)

    pathway = []
    term = first_term(history)
    ready = sorted(code for code, count in in_degree.items() if count == 0)
    while ready:
        pathway.append({
            "term": term_label(term),
            "courses": [display_code(code) for code in ready],
        })
        unlocked = []
        for code in ready:
            for dependent in dependents[code]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    unlocked.append(dependent)
        ready = sorted(unlocked)
        term = next_term(term)
    return pathway


def build_recommendations(student_id: str, history: list[dict],
                          catalog: dict) -> dict:
    """The whole GET /recommendations response body."""
    return {
        "student_id": student_id,
        "recommended_pathway": build_pathway(history, catalog),
    }
