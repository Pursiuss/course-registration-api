"""Unit tests for recommend.py: the Kahn's-algorithm pathway."""
from datetime import date

from models import Course
from recommend import (
    build_pathway, build_recommendations, first_term, next_term, term_label,
)


def course(code, prereqs=(), cross=()):
    return Course(course_code=code, title=code, credits=3,
                  prerequisites=list(prereqs), cross_listed=list(cross))


def catalog(*courses):
    return {c.course_code: c for c in courses}


def completed(code, term="26W"):
    return {"course_code": code, "term": term,
            "credits_earned": 3, "status": "Completed"}


# A completed course that isn't in the test catalogs. It only sets the
# latest transcript term to 26W, so every pathway starts in 26F.
STARTS_26F = [completed("ZZZZ-0000")]


def test_terms_alternate_fall_and_winter():
    assert term_label(next_term((26, 3))) == "27W"  # 26F -> 27W
    assert term_label(next_term((27, 0))) == "27F"  # 27W -> 27F


def test_first_term_follows_the_latest_transcript_term():
    history = [completed("A-1000", "25F"), completed("B-1000", "26W")]
    assert term_label(first_term(history)) == "26F"


def test_first_term_without_history_uses_today():
    assert term_label(first_term([], today=date(2026, 11, 26))) == "27W"
    assert term_label(first_term([], today=date(2027, 3, 1))) == "27F"


def test_prerequisites_come_in_earlier_terms():
    cat = catalog(course("A1000"), course("B1000", ["A1000"]),
                  course("C1000", ["A1000", "B1000"]), course("D1000"))
    assert build_pathway(STARTS_26F, cat) == [
        {"term": "26F", "courses": ["A-1000", "D-1000"]},
        {"term": "27W", "courses": ["B-1000"]},
        {"term": "27F", "courses": ["C-1000"]},
    ]


def test_completed_courses_are_left_out_and_satisfy_prerequisites():
    cat = catalog(course("A1000"), course("B1000", ["A1000"]))
    assert build_pathway([completed("A-1000")], cat) == [
        {"term": "26F", "courses": ["B-1000"]},
    ]


def test_attempted_is_not_completed():
    attempted = {"course_code": "A-1000", "term": "26W",
                 "credits_earned": 0, "status": "Attempted"}
    assert build_pathway([attempted], catalog(course("A1000"))) == [
        {"term": "26F", "courses": ["A-1000"]},
    ]


def test_cross_listed_twin_of_a_completed_course_is_skipped():
    cat = catalog(course("COSC3506", cross=["ITEC3506"]), course("ITEC3506"),
                  course("ITEC4000", ["COSC3506"]))
    assert build_pathway([completed("ITEC-3506")], cat) == [
        {"term": "26F", "courses": ["ITEC-4000"]},
    ]


def test_unschedulable_courses_are_left_out():
    cat = catalog(course("A1000", ["PHIL9999"]),  # prerequisite not in catalog
                  course("X1000", ["Y1000"]),  # X and Y need each other
                  course("Y1000", ["X1000"]),
                  course("B1000"))
    assert build_pathway(STARTS_26F, cat) == [
        {"term": "26F", "courses": ["B-1000"]},
    ]


def test_response_body():
    body = build_recommendations("s1", [completed("A-1000")],
                                 catalog(course("A1000")))
    assert body == {"student_id": "s1", "recommended_pathway": []}
