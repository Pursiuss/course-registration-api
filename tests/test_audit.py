"""Unit tests for the Phase 3 audit rules (audit.py)."""
from audit import (
    build_audit_report,
    check_cross_listings,
    check_prerequisites,
    credit_summary,
    display_code,
    term_sort_key,
    total_earned,
)
from models import Course


def course(code, credits=3, prereqs=(), cross=()):
    return Course(course_code=code, title=code, credits=credits,
                  prerequisites=list(prereqs), cross_listed=list(cross))


def record(code, term, status="Completed", credits=3):
    return {"course_code": code, "term": term,
            "credits_earned": credits, "status": status}


def planned(code, term="26F"):
    return {"course_code": code, "term": term}


CATALOG = {
    "COSC4426": course("COSC4426", prereqs=["COSC3127"]),
    "COSC3127": course("COSC3127"),
    "COSC3506": course("COSC3506", cross=["ITEC3506"]),
    "ITEC3506": course("ITEC3506", cross=["COSC3506"]),
    "ACCT2000": course("ACCT2000", cross=["MATH2000"]),
    "MATH2000": course("MATH2000"),
}


# ---- term ordering ----

def test_terms_sort_chronologically():
    terms = ["26F", "23F", "26SP", "24W", "24F", "26S"]
    assert sorted(terms, key=term_sort_key) == [
        "23F", "24W", "24F", "26SP", "26S", "26F"]


def test_term_key_ignores_case_and_spaces():
    assert term_sort_key(" 26sp ") == term_sort_key("26SP")


def test_unreadable_term_sorts_last():
    assert term_sort_key("banana") > term_sort_key("99F")
    assert term_sort_key(None) > term_sort_key("99F")


def test_display_code_adds_hyphen():
    assert display_code("COSC3127") == "COSC-3127"
    assert display_code("weird") == "weird"


# ---- prerequisites ----

def test_missing_prerequisite_is_reported():
    timeline = check_prerequisites([planned("COSC-4426")], [], CATALOG)
    assert timeline == [{"term": "26F", "errors": [{
        "course_code": "COSC-4426",
        "type": "MISSING_PREREQUISITE",
        "message": "Missing prerequisite: COSC-3127",
    }]}]


def test_prerequisite_in_earlier_term_is_satisfied():
    history = [record("COSC 3127", "26W")]
    timeline = check_prerequisites([planned("COSC-4426")], history, CATALOG)
    assert timeline == []


def test_prerequisite_in_same_term_is_not_enough():
    history = [record("COSC-3127", "26F")]
    timeline = check_prerequisites([planned("COSC-4426")], history, CATALOG)
    assert timeline[0]["term"] == "26F"


def test_attempted_prerequisite_does_not_count():
    history = [record("COSC-3127", "25F", status="Attempted")]
    timeline = check_prerequisites([planned("COSC-4426")], history, CATALOG)
    assert len(timeline) == 1


def test_timeline_is_chronological():
    plan = [planned("COSC-4426", "27W"), planned("COSC-4426", "25F")]
    timeline = check_prerequisites(plan, [], CATALOG)
    assert [entry["term"] for entry in timeline] == ["25F", "27W"]


def test_course_not_in_catalog_is_skipped():
    assert check_prerequisites([planned("XYZ-1000")], [], CATALOG) == []


# ---- cross-listings ----

def test_cross_listed_with_completed_course():
    history = [record("COSC-3506", "26W")]
    plan = [planned("ITEC 3506")]
    assert check_cross_listings(plan, history, CATALOG) == [{
        "course_code": "ITEC 3506",
        "type": "CROSS_LIST_CONFLICT",
        "message": "Cross-listed with completed course COSC-3506",
    }]


def test_cross_listing_found_from_the_other_row():
    # Only ACCT-2000's row lists MATH-2000.
    history = [record("ACCT-2000", "25F")]
    plan = [planned("MATH-2000")]
    assert len(check_cross_listings(plan, history, CATALOG)) == 1


def test_cross_listed_with_attempted_course_is_fine():
    history = [record("COSC-3506", "26W", status="Attempted")]
    plan = [planned("ITEC-3506")]
    assert check_cross_listings(plan, history, CATALOG) == []


# ---- credits ----

def test_retake_counts_only_the_pass():
    history = [record("COSC-1701", "25F", status="Attempted"),
               record("COSC-1701", "26W")]
    assert total_earned(history) == 3


def test_course_completed_twice_counts_once():
    history = [record("COSC-1701", "25F", credits=3),
               record("COSC 1701", "26W", credits=4)]
    assert total_earned(history) == 4  # most recent completion wins


def test_in_progress_earns_nothing():
    assert total_earned([record("COSC-1701", "26F", "In-Progress")]) == 0


def test_credit_summary_totals():
    history = [record("COSC-3506", "26W"), record("MATH-1056", "25W")]
    plan = [planned("COSC-4426"), planned("ITEC-3506"), planned("XYZ-1000")]
    assert credit_summary(plan, history, CATALOG) == {
        "total_earned": 6,
        "total_planned": 6,  # XYZ-1000 isn't in the catalog
        "total_remaining_for_graduation": 108,
    }


def test_remaining_never_goes_negative():
    history = [record(f"COSC-{n}", "25F", credits=10)
               for n in range(1000, 1013)]
    summary = credit_summary([], history, CATALOG)
    assert summary["total_remaining_for_graduation"] == 0


# ---- status ----

def test_status_ok_when_no_issues():
    report = build_audit_report("1", [], [], CATALOG, strict=True)
    assert report["status"] == "ok"


def test_status_warning_or_failed_when_issues():
    plan = [planned("COSC-4426")]
    lax = build_audit_report("1", plan, [], CATALOG, strict=False)
    strict = build_audit_report("1", plan, [], CATALOG, strict=True)
    assert lax["status"] == "warning"
    assert strict["status"] == "failed"
