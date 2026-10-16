from fastapi import FastAPI, UploadFile, File, HTTPException
from models import (
    Course, ImportResult, normalize_code,
    HistoryUpdate, PlanRequest, StudentProfile,
)
from parser import parse_catalog
from transcript_parser import parse_transcript

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


@app.get("/")
async def root():
    return {"status": "ok"}


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

@app.post("/api/v1/students/{student_id}/history/import", status_code=201)
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


@app.delete("/api/v1/students/{student_id}/plan")
async def clear_plan(student_id: str):
    student = get_student(student_id)
    student["plan"] = []
    return {"status": "success", "message": "Plan cleared"}


# ---- Phase 2: unified profile ----

@app.get("/api/v1/students/{student_id}/profile", response_model=StudentProfile)
async def get_profile(student_id: str):
    student = get_student(student_id)
    return StudentProfile(
        student_id=student_id,
        history=student["history"],
        plan=student["plan"],
    )
