# course-registration-api

FastAPI service for COSC 3506 (Software Engineering, Algoma U) individual assignment.
Deployed on Render; an auto-grader on Moodle VPL hits the live URL in `api_url.txt`.

- **Phase 1** (done): import a course catalog from HTML, look up courses by code.
- **Phase 2** (done, submitted 2026-10-15, self-test 100/100 locally and live):
  per-student academic profile = transcript history (HTML upload) + course plan (JSON).

Later phases will likely build on these endpoints. Don't change existing routes or
response shapes unless the new spec asks for it, because graded phases may be re-run.

## Files

| File | What it does |
|---|---|
| `main.py` | The FastAPI app and every route. In-memory stores: `courses` (Phase 1) and `students` (Phase 2). |
| `models.py` | Pydantic models + Phase 1 helpers (`normalize_code`, `extract_codes`, `parse_credits`). |
| `parser.py` | Phase 1 catalog HTML parser (`parse_catalog`): first `<table>`, columns by position. |
| `transcript_parser.py` | Phase 2 transcript parser (`parse_transcript`): canonical extraction rule below. |
| `requirements.txt` | Pinned deps Render installs. **Saved as UTF-16** (PowerShell `pip freeze >`); pip reads it fine, but keep the encoding in mind if editing. |
| `api_url.txt` | Live base URL, no trailing slash. This is the file uploaded to VPL. |
| `selftest/` | *Git-ignored.* Course-provided practice grader + sample transcripts. See Testing. |

## Endpoints

Phase 1:
- `GET /` → `{"status": "ok"}` (health check; graders use it to wake the service)
- `POST /api/v1/admin/catalog/import` (multipart `file`) → `{imported, course_codes}`
- `GET /api/v1/catalog/courses/{course_code}` → Course, 404 if missing. Lookup is normalized (`cosc-3506` = `COSC3506`).

Phase 2, prefix `/api/v1/students/{student_id}`:
- `POST /history/import` (multipart `file`) → **201** `{"status":"success","past_courses_imported":N}`. Creates the student; replaces history, keeps plan.
- `PUT /history` body `{"history":[{course_code, term, credits_earned, status}]}` → 200, full overwrite.
- `DELETE /history` → 200, clears it.
- `POST /plan` and `PUT /plan` body `{"planned_courses":[{course_code, term}]}` → 200; both replace the whole plan.
- `DELETE /plan` → 200, clears it.
- `GET /profile` → exactly `{student_id, history, plan}` (enforced by `StudentProfile` response_model).
- Every Phase 2 route except import returns **404** for a student that was never imported (`get_student()` helper).
- Wrong HTTP verb on a route returns 405 (FastAPI default); the grader checks this.

Storage is per-student: `students[student_id] = {"history": [...], "plan": [...]}`. The grader
checks that students don't leak into each other, so never use a shared global list.
Everything is in memory and lost on restart/redeploy (Render free tier sleeps after ~15 min).

## Transcript parsing rule (Phase 2, must match the grader exactly)

Mirrors `parse_transcript` in `selftest/grader/grade_service.py`:
- Only `<table>`s whose `<th>` texts include `Status`, `Course`, `Credits`.
- Row cells by position: `Status | Course | (title) | Grade | Term | Credits` (indexes 0,1,3,4,5); cell text via `get_text(" ", strip=True)`.
- Keep a row if Status ∈ {Completed, In-Progress, Attempted}, Course is non-empty, and Term is non-empty.
- `course_code`, `term` and `status` are verbatim (e.g. `COSC-1046`, hyphen kept, unlike Phase 1's normalized codes).
- `credits_earned = int(cell)`, otherwise 0. This is deliberately strict: `"3.0"` → 0, to match the grader.
- Dedupe by `(course_code, term)`: numeric grade > letter grade > P/blank, then higher credits.

## Running and testing (Windows)

The project venv was copied from an older folder, so `venv\Scripts\activate` and
`uvicorn.exe` still point at the old path. Call the venv's Python directly instead:

```
venv\Scripts\python -m uvicorn main:app --port 8000
venv\Scripts\python selftest\run_selftest.py
```

- `selftest\run_selftest.py` is a PowerShell-friendly replacement for `run_selftest.sh` (bash isn't available in the user's PowerShell). It defaults to `http://localhost:8000`.
- To test the live deployment, set `API_URL` to the Render URL first (bash: `API_URL=$(cat api_url.txt) venv/Scripts/python selftest/run_selftest.py`).
- `httpx` is installed in the venv for the grader. It isn't in `requirements.txt` because production doesn't need it.

## Deploying

- The repo is `github.com/Pursiuss/course-registration-api`, branch `main`. Render auto-deploys on push (build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`).
- This folder (`C:\Users\paris\Documents\GitHub\course-registration-api`) is the GitHub Desktop clone, using an HTTPS remote. Pushing from Claude's shell may fail for lack of credentials. If so, ask the user to push with GitHub Desktop ("Push origin").
- After a push, wait a few minutes and confirm the deploy by hitting a new or changed route on the live URL.
- Commit only source files. `venv/`, `__pycache__/` and `selftest/` are git-ignored and must stay off GitHub.

## Known issues

- Phase 1: `parse_credits` can return a float (e.g. `1.5`), but `Course.credits` is `int`, so a fractional-credit row would fail the catalog import with a 500. Not hit by the Phase 1 data; fix (`float | int`) only if a later phase needs it.

## Working with this user

- They're a student and want to be **walked through work step by step**: lay out the steps, do one, then pause for confirmation before the next.
- New assignment specs come pasted with a grading table. Look for a provided self-test (unzip into `selftest/`) and match the grader's reference logic exactly.
- Coursework allows AI with disclosure: they need an **AI Interaction Log** for each VPL submission, so be ready to draft an accurate one.
- Never stop processes by window title or name. If you start a temporary server, stop it by its own PID.
