import dataclasses


@dataclasses.dataclass
class MoodleMonitorCoursesConfig:
    load_inprogress_only: bool = True
    ignore_no_ending_date: bool = False
    teachers_have_capability: str = 'moodle/grade:viewall'
    chunk_size: int = 25


@dataclasses.dataclass
class MoodleMonitorParticipantConfig:
    chunk_size: int = 50


@dataclasses.dataclass
class MoodleMonitorAssignmentConfig:
    ignore_older_than_days: int = 180


@dataclasses.dataclass
class MoodleMonitorSubmissionConfig:
    chunk_size: int = 20


@dataclasses.dataclass
class MoodleMonitorConfig:
    courses: MoodleMonitorCoursesConfig = dataclasses.field(default_factory=MoodleMonitorCoursesConfig)
    participants: MoodleMonitorParticipantConfig = dataclasses.field(default_factory=MoodleMonitorParticipantConfig)
    assignments: MoodleMonitorAssignmentConfig = dataclasses.field(default_factory=MoodleMonitorAssignmentConfig)
    submissions: MoodleMonitorSubmissionConfig = dataclasses.field(default_factory=MoodleMonitorSubmissionConfig)
