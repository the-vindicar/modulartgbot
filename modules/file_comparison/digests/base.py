"""Описание протокола для плагинов, реализующих обработку файлов."""
import abc
from fnmatch import fnmatch
import typing as t


__all__ = ['DigestExtractorABC', 'DigestComparerABC']


class DigestExtractorABC(abc.ABC):
    """
    Абстрактный базовый класс плагина, который умеет обрабатывать файлы определённого типа.
    Класс должен иметь конструктор без параметров. Роль конструктора берёт на себя метод initialize().
    При работе с внешними ресурсами код должен исходить из предположения, что он выполняется
    параллельно в нескольких дочерних процессах.
    """

    @abc.abstractmethod
    def initialize(self, settings: dict[str, t.Any]) -> None:
        """Подготавливает плагин к работе."""

    @classmethod
    @abc.abstractmethod
    def name(cls) -> str:
        """Имя плагина."""

    @classmethod
    @abc.abstractmethod
    def digest_types(cls) -> frozenset[str]:
        """Возвращает множество типов дайджестов, которые поддерживаются данным плагином."""

    @abc.abstractmethod
    def can_process_file(self, filename: str, mimetype: str, filesize: int) -> bool:
        """
        Может ли данный плагин обработать данный файл и извлечь из него выжимку?

        :param filename: Имя файла. Расширение файла может подсказать тип содержимого.
        :param mimetype: MIME-тип файла, сообщённый сервером. Может подсказать тип содержимого.
        :param filesize: Размер файла в байтах. Позволяет игнорировать слишком большие файлы.
        :return: True, если плагин готов попытаться извлечь дайджест из этого файла."""


    @abc.abstractmethod
    def process_file(self, filename: str, mimetype: str, content: bytes
                     ) -> tuple[dict[str, bytes], dict[str, str]]:
        """
        Обрабатывает содержимое файла и возвращает выжимки и предупреждения, если получилось.
        В случае неудачи обязательно выбрасывает исключение.

        :param filename: Имя файла. Расширение файла может подсказать тип содержимого.
        :param mimetype: MIME-тип файла, сообщённый сервером. Может подсказать тип содержимого.
        :param content: Содержимое файла как массив байт.
        :return: Выжимки тех или иных типов; предупреждения тех или иных типов.
        """


class DigestComparerABC(abc.ABC):
    """
    Абстрактный базовый класс плагина, который умеет сравнивать дайджесты определённого типа.
    При работе с внешними ресурсами код должен исходить из предположения, что он выполняется
    параллельно в нескольких дочерних процессах.
    """

    @classmethod
    @abc.abstractmethod
    def digest_types(cls) -> frozenset[str]:
        """Возвращает множество типов дайджестов, которые поддерживаются данным плагином."""

    @abc.abstractmethod
    def compare_digests(self, digest_type: str, older_id: int, older: bytes, newer_id: int, newer: bytes) -> float:
        """Сравнивает две выжимки и возвращает степень сходства от 0 (сходства нет совсем) до 1 (полное совпадение)."""
