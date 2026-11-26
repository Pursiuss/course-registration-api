# course-registration-api

FastAPI service for COSC 3506 (Software Engineering, Algoma U) individual assignment.
Deployed on Render; an auto-grader on Moodle VPL hits the live URL in `api_url.txt`.

- **Phase 1** (done): import a course catalog from HTML, look up courses by code.
- **Phase 2** (done, submitted 2026-10-15, self-test 100/100 locally and live):
  per-student academic profile = transcript history (HTML upload) + course plan (JSON).
- **Phase 3** (done, merged to `main` via PR #2 and submitted on 2026-11-10, VPL score
  100/100): audit engine (`GET /audit-report`) + GitHub Actions CI quality gate.
- **Phase 4** (code done on `phase-4-final`, self-test 100/100 locally, CI green on
  2026-11-26; not yet merged to `main`, deployed or submitted): JWT auth (register/login),
  BOLA + RBAC, rate limit on `audit-report`, and `GET /recommendations` (Kahn's algorithm).

Later phases will likely build on these endpoints. Don't change existing routes or
response shapes unless the new spec asks for it, because graded phases may be re-run.

## Files

| File | What it does |
|---|---|
| `main.py` | The FastAPI app and every route. In-memory stores: `courses` (Phase 1) and `students` (Phase 2). Also the Phase 4 FastAPI dependencies (`current_claims`, `require_owner`, `require_owner_or_admin`, `rate_limit_audit`). |
| `models.py` | Pydantic models + Phase 1 helpers (`normalize_code`, `extract_codes`, `parse_credits`). |
| `parser.py` | Phase 1 catalog HTML parser (`parse_catalog`): first `<table>`, columns by position. |
| `transcript_parser.py` | Phase 2 transcript parser (`parse_transcript`): canonical extraction rule below. |
| `audit.py` | Phase 3 audit rules as pure functions (no FastAPI), so they're unit-testable. `build_audit_report()` is the whole response body. |
| `auth.py` | Phase 4, pure functions: bcrypt hashing, JWT create/decode, the in-memory `users` store (admin seeded at import). |
| `rate_limit.py` | Phase 4 `SlidingWindowLimiter` (per-key deque of timestamps; injectable `clock` for tests). |
| `recommend.py` | Phase 4 recommendations, pure functions: Kahn's algorithm pathway. `build_recommendations()` is the whole response body. Reuses `audit.py` helpers. |
| `tests/` | Unit tests per module (`test_audit.py`, `test_auth.py`, `test_rate_limit.py`, `test_recommend.py`) and `test_api.py` (API tests; see Testing for the in-process/live switch). |
| `setup.cfg` | Config for flake8 (`max-line-length = 88`, excludes `venv`/`selftest`), pytest (`pythonpath = .`) and coverage (source `.`, omits tests/venv/selftest). |
| `requirements.txt` | Pinned deps Render installs (includes `bcrypt==5.0.0`, `PyJWT==2.15.1` since Phase 4). **Saved as UTF-16 LE with BOM, CRLF** (PowerShell `pip freeze >`); pip and CI read it fine. Add lines by hand in VS Code (it keeps the encoding); don't regenerate with `pip freeze`, which would pull in dev tools. |
| `requirements-dev.txt` | `-r requirements.txt` + pinned flake8, pytest, pytest-cov, httpx. Used by CI. UTF-8. |
| `.github/workflows/ci.yml` | CI quality gate (see CI section). |
| `api_url.txt` | Live base URL, no trailing slash. This is the file uploaded to VPL. |
| `selftest/` | *Git-ignored.* Course-provided practice grader for the **current** phase (Phase 4), plus `run_selftest.py`. Older phase graders live in subfolders (`selftest/phase2/`, `selftest/phase3/`), each with its own `run_selftest.py`. If it's ever lost: Phase 4 = `Downloads\selftest(2).zip`, Phase 3 = `Downloads\selftest(1).zip` (both unzip to a top-level `selftest/`), Phase 2 = the stale clone's `selftest\` folder; `run_selftest.py` is in the Phase 2 copy. |

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
- Since Phase 4, `POST /history/import` needs the owner's token and `GET /profile` needs owner-or-admin (see Phase 4). The Phase 2 grader imports without a token, so re-running it now fails; the Phase 4 spec requires this.
- Wrong HTTP verb on a route returns 405 (FastAPI default); the grader checks this.

Phase 3, same prefix:
- `GET /audit-report?strict=<bool>` (default false) → 200
  `{student_id, status, timeline_validation, cross_list_violations, credit_summary}`; 404 via `get_student()`.
  - `timeline_validation`: `[{term, errors:[{course_code, type:"MISSING_PREREQUISITE", message:"Missing prerequisite: COSC-3127"}]}]`, only terms with errors, chronological.
  - `cross_list_violations`: `[{course_code, type:"CROSS_LIST_CONFLICT", message:"Cross-listed with completed course COSC-3506"}]`.
  - `credit_summary`: `{total_earned, total_planned, total_remaining_for_graduation}`.
  - `status`: `"ok"` with no issues; otherwise `"failed"` if strict, else `"warning"`.

Phase 4:
- `POST /api/v1/auth/register` body `{username, password}` → **201** `{"status":"registered"}`; **409** if taken (including `admin`, which is pre-seeded); 422 if either is empty.
- `POST /api/v1/auth/login` same body → 200 `{"access_token": "<jwt>", "token_type": "bearer"}`; **401** for a wrong password *or* unknown user (same message).
- `POST /students/{id}/history/import` → **BOLA**: token `sub` must equal `{id}`, else 401 (no token, junk/expired/forged token, someone else's token, even admin's).
- `GET /students/{id}/profile` and new `GET /students/{id}/plan` → **RBAC**: owner or `role == "admin"`, else 401. `GET /plan` → `{student_id, planned_courses}`.
- `GET /students/{id}/audit-report` → still no login needed, but rate-limited: 10 per sliding 60 s, then **429** (audit not run). Keyed by token `sub` if a valid token is sent, else client IP.
- `GET /students/{id}/recommendations` → owner or admin (401), 404 if never imported, else `{student_id, recommended_pathway: [{term, courses: ["COSC-3127", ...]}]}`, chronological.
- Left open on purpose (spec doesn't name them): catalog import, `POST/PUT/DELETE /plan`, `PUT/DELETE /history`.

Storage is per-student: `students[student_id] = {"history": [...], "plan": [...]}`. The grader
checks that students don't leak into each other, so never use a shared global list.
Everything is in memory and lost on restart/redeploy (Render free tier sleeps after ~15 min).
That includes registered users and the rate-limit counters.

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

## Phase 4 rules (`auth.py`, `rate_limit.py`, `recommend.py`)

What the Phase 4 grader (`selftest/grader/grade_service.py`) does: register admin (409 is fine) → login admin → import catalog → register/login student `770002` → import transcript and POST plan with that token → register attacker `770003` → groups A (auth), B (BOLA), C (RBAC on profile), E (recommendations), then **D (rate limit) last**: 11 `audit-report` calls with the student's token.

- **Auth:** bcrypt with `gensalt()` per password; passwords cut to 72 bytes first (bcrypt 5 raises on longer). JWT HS256 with `sub`, `role`, `iat`, `exp` (60 min). Signing key = `JWT_SECRET` env var, else random per process (fine: users are in memory and die on restart too). Register/login are plain `def` so bcrypt runs in FastAPI's threadpool.
- **401 everywhere:** `HTTPBearer(auto_error=False)` so a missing header reaches our code; every auth failure is 401 with `WWW-Authenticate: Bearer`, never 403.
- **Rate limit:** `SlidingWindowLimiter(limit=10, window=60)`, module-level `audit_limiter`. Drops timestamps `>= window` old, refuses at `limit`; refused requests aren't recorded. Behind Render's proxy every no-token caller shares one IP key (the grader always sends a token).
- **Recommendations:** remove Completed courses (Attempted/In-Progress stay) **and** any course cross-listed with a Completed one (both directions, via `cross_listed_partners`); those also count as done for prerequisites. Kahn level-by-level, one level per term, codes sorted within a term, output via `display_code()`. Courses that can never reach in-degree 0 are left out: a prerequisite neither done nor in the catalog, or a cycle. Terms: start the term after the latest readable transcript term (any status), then alternate F → W (summers skipped); no readable terms → the term after today's date. No per-term course cap.

## Running and testing (Windows)

The venv was rebuilt on 2026-11-26 with `py -3.14 -m venv venv` (the git-ignored folders
had been wiped). Calling the venv's Python directly still works everywhere, so keep using it:

```
venv\Scripts\python -m uvicorn main:app --port 8000
venv\Scripts\python selftest\run_selftest.py
venv\Scripts\python -m flake8
venv\Scripts\python -m pytest --cov --cov-report=term-missing --cov-fail-under=80
```

- `selftest\run_selftest.py` is a PowerShell-friendly replacement for `run_selftest.sh` (bash isn't available in the user's PowerShell). It defaults to `http://localhost:8000`. The Phase 4 self-test can reach 100/100 locally. (The Phase 3 one maxes at 95/100 locally: its check F looks for CI proof files that only exist in the VPL submission.)
- **Restart the server between Phase 4 self-test runs** (or wait 60 s): a second run inside the same minute hits the rate limiter and loses group D.
- To test the live deployment, set `API_URL` to the Render URL first (PowerShell: `$env:API_URL = "<url>"`, then `Remove-Item Env:API_URL` afterwards; bash: `API_URL=$(cat api_url.txt) venv/Scripts/python selftest/run_selftest.py`).
- `tests/test_api.py` uses FastAPI's `TestClient` (in-process, counts toward coverage) unless `API_URL` is set, in which case it sends real HTTP to that server. That's how CI's integration step works. Each test uses its own student ID so runs against a shared server don't collide; `auth_headers()` registers (409 is fine) and logs in that ID. The rate-limit and register tests use a `uuid4` username so re-runs start fresh, and `test_recommendations` checks rules rather than an exact pathway (a shared server may hold extra catalog courses from a self-test run).
- Last run: 53 tests, 98% coverage. Two deprecation warnings come from FastAPI/Starlette internals and are harmless. Against `localhost` on Windows the API tests take ~10–20s (slow localhost resolution); in-process and in CI they're quick.
- Dev tools (flake8, pytest, pytest-cov, httpx) are in `requirements-dev.txt`, not `requirements.txt`, because production doesn't need them.

## CI (GitHub Actions)

`.github/workflows/ci.yml`, job `quality-gate`, runs on pushes to `main`/`phase-3`/`phase-4-final` and PRs into `main`:
Python 3.14 → `pip install -r requirements-dev.txt` → `flake8` → pytest with `--cov-fail-under=80`
→ integration step (start uvicorn in the background, poll `GET /` until it answers, then
`API_URL=http://127.0.0.1:8000 pytest tests/test_api.py`). `gh` is authenticated in Claude's shell,
so `gh run list` / `gh run view <id> --log` work for checking runs. First green Phase 4 run:
45894297209 (2026-11-26, 53 tests, 97.78% coverage, 15 integration tests).

Phase 3 proof (`ci_proof.png`, `ci_logs.txt`) was saved outside the repo in the user's
`...\GIT Project FIles\Phase 3\` school folder. Keep submission artifacts out of the repo.

## Deploying

- The repo is `github.com/Pursiuss/course-registration-api`. Render auto-deploys **only `main`** on push (build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`).
- Branch workflow: work on a phase branch (currently `phase-4-final`; `phase-3` is kept, don't delete it), push it (CI runs), then open a PR into `main` and merge once CI is green. That merge is what deploys. Ask the user before merging.
- Optional: set a `JWT_SECRET` env var on Render. Without it each start makes a random key, which is fine while users live in memory.
- This folder (`C:\Users\paris\Documents\GitHub\course-registration-api`) is the GitHub Desktop clone, using an HTTPS remote. `git push` from Claude's shell has worked (2026-11-10); if it ever fails for credentials, ask the user to push with GitHub Desktop ("Push origin").
- After a deploy, confirm it by hitting a new or changed route on the live URL (e.g. a new route returns FastAPI's generic `{"detail":"Not Found"}` before the deploy and your own 404 or 401 after).
- Commit only source files. `venv/`, `__pycache__/`, `selftest/`, `.pytest_cache/` and `.coverage` are git-ignored and must stay off GitHub.
- There's an older, stale clone at `...\Sem 3\Software Engineering\GIT Project FIles\course-registration-api` (branch `Phase-2`, SSH remote). Don't work there.

## Known issues

- Phase 1: `parse_credits` can return a float (e.g. `1.5`), but `Course.credits` is `int`, so a fractional-credit row would fail the catalog import with a 500. Not hit by the Phase 1–4 data; fix (`float | int`) only if a later phase needs it.
- Phase 1: catalog import merges into `courses` instead of replacing it, so a long-running server keeps courses from every catalog it was sent.

## Working with this user

- They're a student. For assignment work they want to be **walked through it step by step and do the work themselves**: explain one step (what and why, code to paste, a check command with its expected output), then pause. Claude may run read-only checks (read their files, flake8/pytest, `gh`, curl the live URL) to verify or debug, but doesn't edit project code or commit unless asked. For housekeeping they may say "just do it" (e.g. this file).
- What worked well in Phase 4: before handing over a step, Claude copies the project to its scratchpad, applies the exact code there, and runs flake8, pytest and the self-test against it. Then when the user says "done", it diffs their files against that tested copy (`diff --strip-trailing-cr`) to pinpoint paste slips by line.
- Common editor slips to check for when something fails: an auto-indented `def` (IndentationError), a line dropped when replacing a decorator (e.g. the `async def` under it), a two-line paste where only one line landed, a file created but never saved (0 bytes), whitespace-only blank lines or a missing final newline (flake8 W293/W292), and running commands from the stale clone instead of this folder. Pressing Enter at the end of a file in VS Code can leave an *indented* last line, which is still W293+W292. VS Code's "Files: Insert Final Newline" setting avoids this.
- New assignment specs come pasted with a grading table. Look for a provided self-test (unzip into `selftest/`, moving the previous phase's into a subfolder) and match the grader's reference logic, flagging any place the spec's wording and the grader's code disagree.
- Coursework allows AI with disclosure: they need an **AI Interaction Log** for each VPL submission, so be ready to draft an accurate one.
- Never stop processes by window title or name. If you start a temporary server, stop it by its own PID.
