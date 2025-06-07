import dataclasses


@dataclasses.dataclass
class MoodleMonitorCoursesConfig:
    load_inprogress_only: bool = True
    ignore_no_ending_date: bool = False
    teachers_have_capability: str = 'moodle/grade:viewall'
    db_batch_size: int = 5
    update_interval_seconds: int = 60*60*12


@dataclasses.dataclass
class MoodleMonitorParticipantConfig:
    chunk_size: int = 50


@dataclasses.dataclass
class MoodleMonitorAssignmentConfig:
    ignore_older_than_days: int = 180
    deadline_before_seconds: int = 60*60*2
    deadline_after_seconds: int = 60*30
    db_batch_size: int = 5
    update_interval_seconds: int = 60*60*12
    update_course_batch_size: int = 1


@dataclasses.dataclass
class MoodleMonitorSubmissionConfig:
    db_batch_size: int = 5
    update_open_interval_seconds: int = 60*60*3
    update_open_batch_size: int = 1
    update_deadline_interval_seconds: int = 60*3
    update_deadline_batch_size: int = 1


@dataclasses.dataclass
class MoodleMonitorConfig:
    server_timezone: str = 'UTC'
    wakeup_interval_seconds: int = 60
    courses: MoodleMonitorCoursesConfig = dataclasses.field(default_factory=MoodleMonitorCoursesConfig)
    participants: MoodleMonitorParticipantConfig = dataclasses.field(default_factory=MoodleMonitorParticipantConfig)
    assignments: MoodleMonitorAssignmentConfig = dataclasses.field(default_factory=MoodleMonitorAssignmentConfig)
    submissions: MoodleMonitorSubmissionConfig = dataclasses.field(default_factory=MoodleMonitorSubmissionConfig)
