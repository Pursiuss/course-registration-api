# course-registration-api

FastAPI service for COSC 3506 (Software Engineering, Algoma U) individual assignment.
Deployed on Render; an auto-grader on Moodle VPL hits the live URL in `api_url.txt`.

- **Phase 1** (done): import a course catalog from HTML, look up courses by code.
- **Phase 2** (done, submitted 2026-10-15, self-test 100/100 locally and live):
  per-student academic profile = transcript history (HTML upload) + course plan (JSON).
- **Phase 3** (done, merged to `main` via PR #2 and submitted on 2026-11-10, VPL score
  100/100): audit engine (`GET /audit-report`) + GitHub Actions CI quality gate.

Later phases will likely build on these endpoints. Don't change existing routes or
response shapes unless the new spec asks for it, because graded phases may be re-run.

## Files

| File | What it does |
|---|---|
| `main.py` | The FastAPI app and every route. In-memory stores: `courses` (Phase 1) and `students` (Phase 2). |
| `models.py` | Pydantic models + Phase 1 helpers (`normalize_code`, `extract_codes`, `parse_credits`). |
| `parser.py` | Phase 1 catalog HTML parser (`parse_catalog`): first `<table>`, columns by position. |
| `transcript_parser.py` | Phase 2 transcript parser (`parse_transcript`): canonical extraction rule below. |
| `audit.py` | Phase 3 audit rules as pure functions (no FastAPI), so they're unit-testable. `build_audit_report()` is the whole response body. |
| `tests/` | `test_audit.py` (unit tests for `audit.py`), `test_api.py` (API tests; see Testing for the in-process/live switch). |
| `setup.cfg` | Config for flake8 (`max-line-length = 88`, excludes `venv`/`selftest`), pytest (`pythonpath = .`) and coverage (source `.`, omits tests/venv/selftest). |
| `requirements.txt` | Pinned deps Render installs. **Saved as UTF-16** (PowerShell `pip freeze >`); pip reads it fine (it has a BOM), but keep the encoding in mind if editing. |
| `requirements-dev.txt` | `-r requirements.txt` + pinned flake8, pytest, pytest-cov, httpx. Used by CI. UTF-8. |
| `.github/workflows/ci.yml` | CI quality gate (see CI section). |
| `api_url.txt` | Live base URL, no trailing slash. This is the file uploaded to VPL. |
| `selftest/` | *Git-ignored.* Course-provided practice grader for the **current** phase (Phase 3), plus `run_selftest.py`. Older phase graders live in subfolders (`selftest/phase2/`), each with its own `run_selftest.py`. |

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

Phase 3, same prefix:
- `GET /audit-report?strict=<bool>` (default false) → 200
  `{student_id, status, timeline_validation, cross_list_violations, credit_summary}`; 404 via `get_student()`.
  - `timeline_validation`: `[{term, errors:[{course_code, type:"MISSING_PREREQUISITE", message:"Missing prerequisite: COSC-3127"}]}]`, only terms with errors, chronological.
  - `cross_list_violations`: `[{course_code, type:"CROSS_LIST_CONFLICT", message:"Cross-listed with completed course COSC-3506"}]`.
  - `credit_summary`: `{total_earned, total_planned, total_remaining_for_graduation}`.
  - `status`: `"ok"` with no issues; otherwise `"failed"` if strict, else `"warning"`.

Storage is per-student: `students[student_id] = {"history": [...], "plan": [...]}`. The grader
checks that students don't leak into each other, so never use a shared global list.
Everything is in memory and lost on restart/redeploy (Render free tier sleeps after ~15 min).

## Transcript parsing rule (Phase 2, must match the grader exactly)

Mirrors `parse_transcript` in the Phase 2 grader (`selftest/phase2/grader/grade_service.py`):
- Only `<table>`s whose `<th>` texts include `Status`, `Course`, `Credits`.
- Row cells by position: `Status | Course | (title) | Grade | Term | Credits` (indexes 0,1,3,4,5); cell text via `get_text(" ", strip=True)`.
- Keep a row if Status ∈ {Completed, In-Progress, Attempted}, Course is non-empty, and Term is non-empty.
- `course_code`, `term` and `status` are verbatim (e.g. `COSC-1046`, hyphen kept, unlike Phase 1's normalized codes).
- `credits_earned = int(cell)`, otherwise 0. This is deliberately strict: `"3.0"` → 0, to match the grader.
- Dedupe by `(course_code, term)`: numeric grade > letter grade > P/blank, then higher credits.
- Note: Attempted rows keep their Credits cell (e.g. 3), so anything summing credits must filter on `status == "Completed"`.

## Audit rules (Phase 3, in `audit.py`)

- **Codes:** the catalog stores normalized codes (`COSC3127`, also inside `prerequisites`/`cross_listed`); history and plan keep the hyphen. Always compare via `normalize_code()`. `display_code()` turns `COSC3127` back into `COSC-3127` for messages.
- **Terms:** `term_sort_key()` → `(year, season)` with W < SP < S < F. Unreadable terms → `(999, 999)`, i.e. later than everything, so they never satisfy a prerequisite.
- **Prerequisites:** each catalog prerequisite of a planned course needs a **Completed** history entry in a **strictly earlier** term (same term fails). Planned courses not in the catalog are skipped. One error per missing prerequisite, grouped under the plan's term string.
- **Cross-listings:** checked in **both directions** (the planned course's row, or any row naming it). Violation only if the partner is **Completed** (Attempted doesn't count).
- **total_earned:** Completed entries only, **each course counted once** (most recent completion wins). The user chose this deliberately: it matches the spec wording. The grader's own code sums every Completed `(course, term)`, which differs only if a course is Completed twice in different terms.
- **total_planned:** catalog credits of planned courses (not in catalog → 0). **remaining:** `max(0, 120 - earned - planned)`.

## Running and testing (Windows)

The project venv was copied from an older folder, so `venv\Scripts\activate` and
`uvicorn.exe` still point at the old path. Call the venv's Python directly instead:

```
venv\Scripts\python -m uvicorn main:app --port 8000
venv\Scripts\python selftest\run_selftest.py
venv\Scripts\python -m flake8
venv\Scripts\python -m pytest --cov --cov-report=term-missing --cov-fail-under=80
```

- `selftest\run_selftest.py` is a PowerShell-friendly replacement for `run_selftest.sh` (bash isn't available in the user's PowerShell). It defaults to `http://localhost:8000`. Locally the max is 95/100: check F looks for the CI proof files, which only exist in the VPL submission.
- To test the live deployment, set `API_URL` to the Render URL first (PowerShell: `$env:API_URL = "<url>"`, then `Remove-Item Env:API_URL` afterwards; bash: `API_URL=$(cat api_url.txt) venv/Scripts/python selftest/run_selftest.py`).
- `tests/test_api.py` uses FastAPI's `TestClient` (in-process, counts toward coverage) unless `API_URL` is set, in which case it sends real HTTP to that server. That's how CI's integration step works. Each test uses its own student ID so runs against a shared server don't collide.
- Last run: 29 tests, 96% coverage. Two deprecation warnings come from FastAPI/Starlette internals and are harmless. Against `localhost` on Windows the API tests take ~20s (slow localhost resolution); in-process and in CI they take under a second.
- Dev tools (flake8, pytest, pytest-cov, httpx) are in `requirements-dev.txt`, not `requirements.txt`, because production doesn't need them.

## CI (GitHub Actions)

`.github/workflows/ci.yml`, job `quality-gate`, runs on pushes to `main`/`phase-3` and PRs into `main`:
Python 3.14 → `pip install -r requirements-dev.txt` → `flake8` → pytest with `--cov-fail-under=80`
→ integration step (start uvicorn in the background, poll `GET /` until it answers, then
`API_URL=http://127.0.0.1:8000 pytest tests/test_api.py`). `gh` is authenticated in Claude's shell,
so `gh run list` / `gh run view <id> --log` work for checking runs.

Phase 3 proof (`ci_proof.png`, `ci_logs.txt`) was saved outside the repo in the user's
`...\GIT Project FIles\Phase 3\` school folder. Keep submission artifacts out of the repo.

## Deploying

- The repo is `github.com/Pursiuss/course-registration-api`. Render auto-deploys **only `main`** on push (build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`).
- Branch workflow: work on a phase branch (currently `phase-3`, kept after merging; don't delete it), push it (CI runs), then open a PR into `main` and merge once CI is green. That merge is what deploys. Ask the user before merging.
- This folder (`C:\Users\paris\Documents\GitHub\course-registration-api`) is the GitHub Desktop clone, using an HTTPS remote. `git push` from Claude's shell has worked (2026-11-10); if it ever fails for credentials, ask the user to push with GitHub Desktop ("Push origin").
- After a deploy, confirm it by hitting a new or changed route on the live URL (e.g. a new route returns FastAPI's generic `{"detail":"Not Found"}` before the deploy and your own 404 message after).
- Commit only source files. `venv/`, `__pycache__/`, `selftest/`, `.pytest_cache/` and `.coverage` are git-ignored and must stay off GitHub.
- There's an older, stale clone at `...\Sem 3\Software Engineering\GIT Project FIles\course-registration-api` (branch `Phase-2`, SSH remote). Don't work there.

## Known issues

- Phase 1: `parse_credits` can return a float (e.g. `1.5`), but `Course.credits` is `int`, so a fractional-credit row would fail the catalog import with a 500. Not hit by the Phase 1–3 data; fix (`float | int`) only if a later phase needs it.

## Working with this user

- They're a student. For assignment work they want to be **walked through it step by step and do the work themselves**: explain one step (what and why, code to paste, a check command with its expected output), then pause. Claude may run read-only checks (read their files, flake8/pytest, `gh`, curl the live URL) to verify or debug, but doesn't edit project code or commit unless asked. For housekeeping they may say "just do it" (e.g. this file).
- Common editor slips to check for when something fails: an auto-indented `def` (IndentationError), a file created but never saved (0 bytes), whitespace-only blank lines or a missing final newline (flake8 W293/W292), and running commands from the stale clone instead of this folder.
- New assignment specs come pasted with a grading table. Look for a provided self-test (unzip into `selftest/`, moving the previous phase's into a subfolder) and match the grader's reference logic, flagging any place the spec's wording and the grader's code disagree.
- Coursework allows AI with disclosure: they need an **AI Interaction Log** for each VPL submission, so be ready to draft an accurate one.
- Never stop processes by window title or name. If you start a temporary server, stop it by its own PID.
