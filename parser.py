from bs4 import BeautifulSoup
from models import Course, normalize_code, extract_codes, parse_credits


def parse_catalog(html_bytes: bytes) -> list[Course]:
    """
    Parse a course catalog HTML file into a list of Course objects.

    Assumes: a <table> containing course rows, with each row's <td> cells
    in the order Course Code, Title, Credits, Prerequisites, Cross-listed.
    Works off column position, not classes/ids/text, so it isn't tied to
    the specific wording of any one catalog.
    """
    soup = BeautifulSoup(html_bytes, "html.parser")

    table = soup.find("table")
    if table is None:
        return []

    courses: list[Course] = []

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")

        # Skip header rows (they use <th>, so find_all("td") returns nothing)
        # and any malformed row that doesn't have all 5 columns.
        if len(cells) < 5:
            continue

        code_cell, title_cell, credits_cell, prereq_cell, cross_cell = cells[:5]

        code = normalize_code(code_cell.get_text(strip=True))
        title = title_cell.get_text(strip=True)
        credits = parse_credits(credits_cell.get_text(strip=True))
        prerequisites = extract_codes(prereq_cell.get_text(strip=True))
        cross_listed = extract_codes(cross_cell.get_text(strip=True))

        if not code:
            # A row with no parseable course code isn't a course we can index.
            continue

        courses.append(
            Course(
                course_code=code,
                title=title,
                credits=credits,
                prerequisites=prerequisites,
                cross_listed=cross_listed,
            )
        )

    return courses
