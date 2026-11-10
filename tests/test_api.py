"""
API tests. By default they run the app in-process with FastAPI's
TestClient. If the API_URL environment variable is set, they send real
HTTP requests to that server instead (the CI integration step).
"""
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app

API_URL = os.environ.get("API_URL")


def table(header, rows):
    """Build a minimal HTML <table> (header row + data rows) as bytes."""
    head = "".join(f"<th>{h}</th>" for h in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><tr>{head}</tr>{body}</table>".encode()


CATALOG_HTML = table(
    ["Course Code", "Title", "Credits", "Prerequisites", "Cross-listed"],
    [
        ["COSC-4426", "Capstone", "3", "COSC-3127", ""],
        ["COSC-3127", "Algorithms", "3", "None", ""],
        ["ITEC-3506", "Web Systems", "3", "None", "COSC-3506"],
        ["COSC-3506", "Software Eng", "3", "None", "ITEC-3506"],
    ],
)

TRANSCRIPT_HTML = table(
    ["Status", "Course", "", "Grade", "Term", "Credits"],
    [
        ["Attempted", "COSC-1701", "Intro CS", "45", "25F", "3"],
        ["Completed", "COSC-1701", "Intro CS", "68", "26W", "3"],
        ["Completed", "COSC-3506", "Software Eng", "75", "26W", "3"],
        ["Planned", "COSC-9999", "Future", "", "", "3"],
    ],
)

PLAN = {"planned_courses": [
    {"course_code": "COSC-4426", "term": "26F"},
    {"course_code": "ITEC-3506", "term": "26F"},
]}


@pytest.fixture
def client():
    if API_URL:
        with httpx.Client(base_url=API_URL, timeout=30) as live:
            yield live
    else:
        with TestClient(app) as local:
            yield local


def import_catalog(client):
    files = {"file": ("catalog.html", CATALOG_HTML, "text/html")}
    return client.post("/api/v1/admin/catalog/import", files=files)


def import_history(client, sid):
    files = {"file": ("transcript.html", TRANSCRIPT_HTML, "text/html")}
    return client.post(f"/api/v1/students/{sid}/history/import", files=files)


# ---- Phase 1 + 2 routes (regression) ----

def test_health_check(client):
    assert client.get("/").json() == {"status": "ok"}


def test_catalog_import_and_lookup(client):
    response = import_catalog(client)
    assert response.status_code == 200
    assert response.json()["imported"] == 4
    course = client.get("/api/v1/catalog/courses/cosc-4426").json()
    assert course["prerequisites"] == ["COSC3127"]
    missing = client.get("/api/v1/catalog/courses/NOPE-0000")
    assert missing.status_code == 404


def test_history_import_and_profile(client):
    sid = "test-profile"
    response = import_history(client, sid)
    assert response.status_code == 201
    assert response.json()["past_courses_imported"] == 3
    client.post(f"/api/v1/students/{sid}/plan", json=PLAN)
    profile = client.get(f"/api/v1/students/{sid}/profile").json()
    assert set(profile) == {"student_id", "history", "plan"}
    assert len(profile["plan"]) == 2


def test_history_and_plan_can_be_replaced_and_cleared(client):
    sid = "test-lifecycle"
    import_history(client, sid)
    base = f"/api/v1/students/{sid}"
    record = {"course_code": "MATH-1056", "term": "25W",
              "credits_earned": 3, "status": "Completed"}
    new_history = {"history": [record]}
    assert client.put(f"{base}/history", json=new_history).status_code == 200
    assert client.put(f"{base}/plan", json=PLAN).status_code == 200
    assert client.delete(f"{base}/plan").status_code == 200
    assert client.delete(f"{base}/history").status_code == 200
    profile = client.get(f"{base}/profile").json()
    assert profile["history"] == [] and profile["plan"] == []


def test_wrong_method_is_405(client):
    assert client.delete("/api/v1/catalog/courses/COSC4426").status_code == 405


# ---- Phase 3: audit report ----

def test_unknown_student_is_404(client):
    response = client.get("/api/v1/students/never-imported/audit-report")
    assert response.status_code == 404


def test_audit_report(client):
    sid = "test-audit"
    import_catalog(client)
    import_history(client, sid)
    client.post(f"/api/v1/students/{sid}/plan", json=PLAN)

    report = client.get(f"/api/v1/students/{sid}/audit-report").json()
    assert report["status"] == "warning"
    errors = report["timeline_validation"][0]["errors"]
    assert errors[0]["course_code"] == "COSC-4426"
    assert errors[0]["type"] == "MISSING_PREREQUISITE"
    violation = report["cross_list_violations"][0]
    assert violation["course_code"] == "ITEC-3506"
    assert report["credit_summary"] == {
        "total_earned": 6,
        "total_planned": 6,
        "total_remaining_for_graduation": 108,
    }


def test_audit_report_strict_mode_fails(client):
    sid = "test-strict"
    import_catalog(client)
    import_history(client, sid)
    client.post(f"/api/v1/students/{sid}/plan", json=PLAN)
    url = f"/api/v1/students/{sid}/audit-report"
    assert client.get(url, params={"strict": "true"}).json()["status"] == "failed"


def test_audit_report_ok_with_no_issues(client):
    sid = "test-ok"
    import_history(client, sid)
    report = client.get(f"/api/v1/students/{sid}/audit-report").json()
    assert report["status"] == "ok"
