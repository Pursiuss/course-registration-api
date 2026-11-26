from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models import (
    Course, ImportResult, normalize_code,
    HistoryUpdate, PlanRequest, StudentProfile, Credentials,
)
from parser import parse_catalog
from transcript_parser import parse_transcript
from audit import build_audit_report
from auth import register_user, authenticate, create_token, decode_token
from rate_limit import SlidingWindowLimiter
from recommend import build_recommendations


app = FastAPI()

# module-level dict acting as our in-memory "database"
courses: dict[str, Course] = {}

# Per-student state, keyed by student_id. Each value holds that student's
# own lists, so one student's data can never leak into another's:
#   {"123456789": {"history": [...], "plan": [...]}}
students: dict[str, dict[str, list]] = {}


def get_student(student_id: str) -> dict[str, list]:
    """Look up a student, or 404 if no history import has created them yet."""
    student = students.get(student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return student


# ---- Phase 4: who is calling? ----

# auto_error=False: a missing header gives us None instead of FastAPI's
# own error, so every auth failure below is the 401 the spec asks for.
bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def current_claims(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """Claims from a valid Bearer token, or 401 (missing, forged, expired)."""
    claims = decode_token(creds.credentials) if creds else None
    if claims is None:
        raise unauthorized("Missing or invalid token")
    return claims


def require_owner(student_id: str, claims: dict = Depends(current_claims)) -> dict:
    """BOLA lock: the token's sub must be exactly this student_id."""
    if claims.get("sub") != student_id:
        raise unauthorized("Token does not belong to this student")
    return claims


def require_owner_or_admin(
    student_id: str, claims: dict = Depends(current_claims)
) -> dict:
    """RBAC: the student themselves, or anyone whose token says role=admin."""
    if claims.get("sub") != student_id and claims.get("role") != "admin":
        raise unauthorized("Not allowed to view this student")
    return claims


@app.get("/")
async def root():
    return {"status": "ok"}


# ---- Phase 4: authentication ----

# Plain "def", not "async def": bcrypt is deliberately slow, so FastAPI
# runs these in a worker thread instead of blocking every other request.
@app.post("/api/v1/auth/register", status_code=201)
def register(body: Credentials):
    if not register_user(body.username, body.password):
        raise HTTPException(status_code=409, detail="Username already exists")
    return {"status": "registered"}


@app.post("/api/v1/auth/login")
def login(body: Credentials):
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_token(body.username, user["role"])
    return {"access_token": token, "token_type": "bearer"}


# ---- Phase 1: course catalog ----

@app.post("/api/v1/admin/catalog/import", response_model=ImportResult)
async def import_catalog(file: UploadFile = File(...)):
    html_bytes = await file.read()
    parsed_courses = parse_catalog(html_bytes)

    for course in parsed_courses:
        courses[course.course_code] = course

    return ImportResult(
        imported=len(parsed_courses),
        course_codes=[c.course_code for c in parsed_courses],
    )


@app.get("/api/v1/catalog/courses/{course_code}", response_model=Course)
async def get_course(course_code: str):
    key = normalize_code(course_code)
    course = courses.get(key)

    if course is None:
        raise HTTPException(status_code=404, detail=f"Course '{course_code}' not found")

    return course


# ---- Phase 2: student history ----

@app.post(
    "/api/v1/students/{student_id}/history/import",
    status_code=201,
    dependencies=[Depends(require_owner)],
)
async def import_history(student_id: str, file: UploadFile = File(...)):
    html_bytes = await file.read()
    history = parse_transcript(html_bytes)

    # Creates the student on first import; a re-import replaces the
    # history but keeps any plan already saved.
    student = students.setdefault(student_id, {"history": [], "plan": []})
    student["history"] = history

    return {"status": "success", "past_courses_imported": len(history)}


@app.put("/api/v1/students/{student_id}/history")
async def replace_history(student_id: str, body: HistoryUpdate):
    student = get_student(student_id)
    student["history"] = [record.model_dump() for record in body.history]
    return {"status": "success", "message": "Academic history updated successfully"}


@app.delete("/api/v1/students/{student_id}/history")
async def clear_history(student_id: str):
    student = get_student(student_id)
    student["history"] = []
    return {"status": "success", "message": "Academic history cleared"}


# ---- Phase 2: student plan ----

@app.post("/api/v1/students/{student_id}/plan")
async def save_plan(student_id: str, body: PlanRequest):
    student = get_student(student_id)
    student["plan"] = [course.model_dump() for course in body.planned_courses]
    return {"status": "success", "planned_courses_saved": len(student["plan"])}


@app.put("/api/v1/students/{student_id}/plan")
async def replace_plan(student_id: str, body: PlanRequest):
    student = get_student(student_id)
    student["plan"] = [course.model_dump() for course in body.planned_courses]
    return {
        "status": "success",
        "message": "Plan replaced successfully",
        "planned_courses_saved": len(student["plan"]),
    }


@app.get(
    "/api/v1/students/{student_id}/plan",
    dependencies=[Depends(require_owner_or_admin)],
)
async def get_plan(student_id: str):
    student = get_student(student_id)
    return {"student_id": student_id, "planned_courses": student["plan"]}


@app.delete("/api/v1/students/{student_id}/plan")
async def clear_plan(student_id: str):
    student = get_student(student_id)
    student["plan"] = []
    return {"status": "success", "message": "Plan cleared"}


# ---- Phase 2: unified profile ----

@app.get(
    "/api/v1/students/{student_id}/profile",
    response_model=StudentProfile,
    dependencies=[Depends(require_owner_or_admin)],
)
async def get_profile(student_id: str):
    student = get_student(student_id)
    return StudentProfile(
        student_id=student_id,
        history=student["history"],
        plan=student["plan"],
    )


# ---- Phase 3: audit report ----

# 10 audit reports per 60 seconds, counted separately for each caller.
audit_limiter = SlidingWindowLimiter(limit=10, window=60)


def rate_limit_audit(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    """429 once a caller passes the limit. A caller is the token's user if
    a valid token is sent, otherwise the client's IP address."""
    claims = decode_token(creds.credentials) if creds else None
    if claims:
        key = f"user:{claims['sub']}"
    else:
        key = f"ip:{request.client.host if request.client else 'unknown'}"
    if not audit_limiter.allow(key):
        raise HTTPException(
            status_code=429, detail="Too many requests: limit is 10 per minute"
        )


@app.get(
    "/api/v1/students/{student_id}/audit-report",
    dependencies=[Depends(rate_limit_audit)],
)
async def audit_report(student_id: str, strict: bool = False):
    student = get_student(student_id)
    return build_audit_report(
        student_id, student["plan"], student["history"], courses, strict
    )


# ---- Phase 4: recommendations ----

@app.get(
    "/api/v1/students/{student_id}/recommendations",
    dependencies=[Depends(require_owner_or_admin)],
)
async def recommendations(student_id: str):
    student = get_student(student_id)
    return build_recommendations(student_id, student["history"], courses)
