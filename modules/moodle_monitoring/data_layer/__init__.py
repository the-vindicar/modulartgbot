from .moodle_classes import *
from .courses_users import create_tables_courses_users, store_courses, load_courses, get_open_course_ids
from .assignments import (create_tables_assignments, store_assignments, load_assignments,
                          get_active_assignment_ids_with_deadlines, OpenAssignments)
from .submissions import (create_tables_submissions, store_submissions, load_submissions_after,
                          get_last_submission_times)


async def create_tables(conn) -> None:
    await create_tables_courses_users(conn)
    await create_tables_assignments(conn)
    await create_tables_submissions(conn)
