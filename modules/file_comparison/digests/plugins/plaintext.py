"""Реализует простое сравнение текстовых файлов без форматирования."""
import typing as t
import difflib
from fnmatch import fnmatch

from ..base import DigestExtractorABC, DigestComparerABC


class PlaintextExtractor(DigestExtractorABC):
    """Извлекает дайджест из plaintext-файлов."""
    mimetypes: t.Collection[str]
    masks: t.Collection[str]

    def initialize(self, settings: dict[str, t.Any]) -> None:
        self.mimetypes = frozenset(settings.get(
            'mimetypes', ['text/plain']
        ))
        self.masks = frozenset(settings.get(
            'masks', ['*.txt', '*.py', '*.pyw', '*.c', '*.cpp', '*.cs', '*.java', '*.js']
        ))

    @classmethod
    def name(cls) -> str:
        return 'plaintext'

    def can_process_file(self, filename: str, mimetype: str, filesize: int) -> bool:
        return (mimetype in self.mimetypes) or any(fnmatch(filename, mask) for mask in self.masks)

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['plaintext'])

    def process_file(self, filename: str, mimetype: str, content: bytes) -> tuple[dict[str, bytes], dict[str, str]]:
        parts = content.split(b'\n')
        for i in range(len(parts)-1, -1, -1):
            part = parts[i].strip(b' \t\r\n')
            if not part:
                del parts[i]
        return {'plaintext': b'\n'.join(parts)}, {}


class PlaintextComparer(DigestComparerABC):
    """Реализует сравнение простого текста."""
    def __init__(self):
        self.matcher = difflib.SequenceMatcher[bytes]()
        self.last_newer_id: t.Optional[int] = None
        self.last_digest_type: t.Optional[str] = None

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['plaintext'])

    def compare_digests(self, digest_type: str, older_id: int, older: bytes, newer_id: int, newer: bytes) -> float:
        if self.last_newer_id != older_id or self.last_digest_type != digest_type:
            self.matcher.set_seq2(b'\n'.split(newer))
            self.last_newer_id = older_id
            self.last_digest_type = digest_type
        self.matcher.set_seq1(b'\n'.split(older))
        return self.matcher.ratio()
