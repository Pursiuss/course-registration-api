from fastapi import FastAPI, UploadFile, File, HTTPException
from models import Course, ImportResult, normalize_code
from parser import parse_catalog

app = FastAPI()

# module-level dict acting as our in-memory "database"
courses: dict[str, Course] = {}


@app.get("/")
async def root():
    return {"status": "ok"}


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
