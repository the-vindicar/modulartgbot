"""Описывает структуру файлов конфигурации, управляющих модулем moodle_monitoring."""
import dataclasses


@dataclasses.dataclass
class MoodleMonitorCoursesConfig:
    """Конфигурация отслеживания курсов."""
    update_interval_seconds: int = 60*60*12
    load_inprogress_only: bool = True
    teacher_role_ids: list[int] = dataclasses.field(default_factory=list)
    db_batch_size: int = 5


@dataclasses.dataclass
class MoodleMonitorAssignmentConfig:
    """Конфигурация отслеживания заданий."""
    update_interval_seconds: int = 60*60*12
    update_course_batch_size: int = 1
    db_batch_size: int = 5
    deadline_before_seconds: int = 60*60*2
    deadline_after_seconds: int = 60*30


@dataclasses.dataclass
class MoodleMonitorSubmissionConfig:
    """Конфигурация отслеживания ответов на задания."""
    update_open_interval_seconds: int = 60*60*3
    update_open_batch_size: int = 1
    update_deadline_interval_seconds: int = 60*3
    update_deadline_batch_size: int = 1
    db_batch_size: int = 5


@dataclasses.dataclass
class MoodleMonitorConfig:
    """Общая конфигурация монитора Moodle."""
    wakeup_interval_seconds: int = 60
    courses: MoodleMonitorCoursesConfig = dataclasses.field(default_factory=MoodleMonitorCoursesConfig)
    assignments: MoodleMonitorAssignmentConfig = dataclasses.field(default_factory=MoodleMonitorAssignmentConfig)
    submissions: MoodleMonitorSubmissionConfig = dataclasses.field(default_factory=MoodleMonitorSubmissionConfig)
