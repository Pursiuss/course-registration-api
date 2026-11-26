# Course Registration API

A FastAPI service that helps a student plan their degree. It imports a course
catalog and a student's transcript, checks a course plan against prerequisite
and cross-listing rules, and recommends a term-by-term pathway to graduation.
Accounts, tokens and rate limiting keep each student's data private.

Built for COSC 3506 (Software Engineering) at Algoma University as a four-phase
individual assignment, graded by an auto-grader that calls the live service.

**Live service:** https://paris-cosc3506-individualassigment-api.onrender.com
(free Render instance: the first request after a quiet spell can take up to a
minute while it wakes up)

## Features

| Phase | What it adds |
|---|---|
| 1 | Import a course catalog from an HTML table; look up any course by code. |
| 2 | Per-student profiles: import a transcript from HTML, save a course plan, read both back. |
| 3 | An audit report that flags missing prerequisites and cross-listing conflicts and sums credits toward the 120 needed to graduate; a CI quality gate. |
| 4 | Register/login with bcrypt-hashed passwords and JWTs, ownership checks (BOLA) and an admin role (RBAC), a sliding-window rate limit, and graduation-pathway recommendations using Kahn's algorithm. |

## API

All student routes start with `/api/v1/students/{student_id}`. Protected routes
take an `Authorization: Bearer <token>` header from `POST /api/v1/auth/login`.

| Method and path | Access | What it does |
|---|---|---|
| `GET /` | public | Health check: `{"status": "ok"}` |
| `POST /api/v1/admin/catalog/import` | public | Upload a catalog HTML file (multipart field `file`) |
| `GET /api/v1/catalog/courses/{course_code}` | public | One course; `COSC-3506`, `cosc 3506` and `COSC3506` all match |
| `POST /api/v1/auth/register` | public | `{"username", "password"}` → 201, or 409 if the name is taken |
| `POST /api/v1/auth/login` | public | Same body → `{"access_token", "token_type": "bearer"}`, or 401 |
| `POST …/history/import` | owner | Upload a transcript HTML file; creates the student (201) |
| `PUT …/history`, `DELETE …/history` | public | Replace or clear the history |
| `POST …/plan`, `PUT …/plan`, `DELETE …/plan` | public | Save, replace or clear the plan `{"planned_courses": [{course_code, term}]}` |
| `GET …/plan` | owner or admin | The saved plan |
| `GET …/profile` | owner or admin | `{student_id, history, plan}` |
| `GET …/audit-report?strict=false` | public, 10 per minute | Prerequisite and cross-listing check plus a credit summary; 429 past the limit |
| `GET …/recommendations` | owner or admin | `{student_id, recommended_pathway: [{term, courses}]}` |

"Owner" means the token's username equals `{student_id}`. Anything else gets a
**401**. The admin account is built in (`admin` / `admin`, as the assignment
requires). Student routes return 404 for a student whose transcript was never
imported. Interactive docs are at `/docs` when the service is running.

### Example

```bash
BASE=http://localhost:8000

curl -X POST $BASE/api/v1/auth/register -H "Content-Type: application/json" \
     -d '{"username":"s12345","password":"MyPass1!"}'

TOKEN=$(curl -s -X POST $BASE/api/v1/auth/login -H "Content-Type: application/json" \
     -d '{"username":"s12345","password":"MyPass1!"}' \
     | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST $BASE/api/v1/admin/catalog/import -F "file=@catalog.html"
curl -X POST $BASE/api/v1/students/s12345/history/import \
     -H "Authorization: Bearer $TOKEN" -F "file=@transcript.html"
curl -H "Authorization: Bearer $TOKEN" $BASE/api/v1/students/s12345/recommendations
```

A response looks like this (the courses depend on the catalog and transcript):

```json
{
  "student_id": "s12345",
  "recommended_pathway": [
    {"term": "26F", "courses": ["COSC-2406", "COSC-3127"]},
    {"term": "27W", "courses": ["COSC-4426"]}
  ]
}
```

## How it works

- **Catalog and transcripts** are parsed from HTML tables with BeautifulSoup.
  Course codes are normalized (`COSC-3506` → `COSC3506`) for comparison and
  shown hyphenated in responses.
- **Audit report:** each planned course's prerequisites must be *Completed* in a
  strictly earlier term; a planned course cross-listed with a completed one is a
  conflict. `strict=true` turns warnings into a failed status.
- **Authentication:** passwords are stored only as salted bcrypt hashes. Login
  returns an HS256 JWT with `sub` (username), `role` and a 60-minute expiry.
  Forged, expired and missing tokens are all rejected with 401.
- **Rate limiting:** a sliding window per caller (the token's user, or the IP
  address without one) allows 10 audit reports in any 60 seconds.
- **Recommendations:** the catalog is treated as a graph where an edge A → B
  means "A is a prerequisite of B". Courses already completed (or cross-listed
  with a completed course) are removed, then Kahn's algorithm schedules one
  level per term, so every prerequisite lands in an earlier term than the courses
  that need it. Terms alternate Fall and Winter, starting after the student's
  latest transcript term. Courses that can never be scheduled (a missing
  prerequisite or a prerequisite cycle) are left out.

All data lives in memory, so it resets whenever the service restarts.

## Running locally

Requires Python 3.14.

```bash
python -m venv venv
venv/bin/pip install -r requirements-dev.txt        # Windows: venv\Scripts\pip
venv/bin/python -m uvicorn main:app --port 8000     # Windows: venv\Scripts\python
```

Then open http://localhost:8000/docs.

Optional: set `JWT_SECRET` to keep the token-signing key the same across
restarts. Without it a random key is generated at startup.

## Tests

```bash
python -m flake8
python -m pytest --cov --cov-report=term-missing --cov-fail-under=80
```

Each module has unit tests (`tests/test_audit.py`, `test_auth.py`,
`test_rate_limit.py`, `test_recommend.py`), and `tests/test_api.py` exercises the
routes. The API tests run in-process by default; set `API_URL` to run the same
tests against a real server instead.

**CI:** GitHub Actions (`.github/workflows/ci.yml`) runs flake8, the tests with an
80% coverage gate, and the API tests against a freshly started server on every
push to `main` and the phase branches and on pull requests into `main`.

## Project layout

```
main.py               FastAPI app: routes, auth and rate-limit dependencies
models.py             Pydantic models and course-code helpers
parser.py             Catalog HTML parser
transcript_parser.py  Transcript HTML parser
audit.py              Audit-report rules
auth.py               Password hashing, JWTs, user store
rate_limit.py         Sliding-window rate limiter
recommend.py          Kahn's-algorithm pathway
tests/                Unit and API tests
```

## Deployment

Hosted on Render, which deploys automatically from `main`:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`

`api_url.txt` holds the live base URL that is submitted to the course grader.
