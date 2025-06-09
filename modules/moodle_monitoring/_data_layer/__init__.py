from .courses_users import create_tables_courses_users, store_courses, load_courses, get_open_course_ids
from .assignments import (create_tables_assignments, store_assignments, load_assignments,
                          get_active_assignments_ending_soon, get_active_assignments_ending_later)
from .submissions import (create_tables_submissions, store_submissions, load_submissions,
                          get_last_submission_times)


async def create_tables(conn):
    await create_tables_courses_users(conn)
    await create_tables_assignments(conn)
    await create_tables_submissions(conn)
