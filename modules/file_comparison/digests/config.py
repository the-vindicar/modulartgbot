"""Конфигурация модуля сравнения файлов"""
import typing as t
import dataclasses


__all__ = ['FileComparisonConfig']


@dataclasses.dataclass
class FileComparisonConfig:
    """Общая конфигурация анализатора файлов."""
    refresh_interval_seconds: int = 60
    ignore_files_larger_than: t.Optional[int] = None
    ignore_files_older_than_days: t.Optional[int] = None
    plugin_settings: dict[str, t.Optional[dict[str, t.Any]]] = dataclasses.field(default_factory=dict)
