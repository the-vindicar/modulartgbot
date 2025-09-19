"""Реализует простое сравнение текстовых файлов без форматирования."""
import logging
import typing as t
import difflib
from fnmatch import fnmatch

from ._base import DigestExtractorABC, DigestComparerABC
from ._homoglyphs import normalize_text


class PlaintextExtractor(DigestExtractorABC):
    """Извлекает дайджест из plaintext-файлов."""

    def __init__(self):
        self.mimetypes: t.Collection[str] = []
        self.masks: t.Collection[str] = []
        self.encodings: t.Collection[str] = []
        self.log: t.Optional[logging.Logger] = None

    def initialize(self, log: logging.Logger, settings: dict[str, t.Any]) -> None:
        self.log = log
        self.encodings = list(settings.get('encodings', ['utf-8-sig', 'windows-1251']))
        self.mimetypes = frozenset(settings.get(
            'mimetypes', ['text/plain']
        ))
        self.masks = frozenset(settings.get(
            'masks', ['*.txt', '*.py', '*.pyw', '*.c', '*.cpp', '*.cs', '*.java', '*.js']
        ))

    @classmethod
    def plugin_name(cls) -> str:
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
            else:
                parts[i] = part
        self.log.debug('%d lines left after trimming whitespace', len(parts))
        text = b'\n'.join(parts)
        for enc in self.encodings:
            try:
                string = text.decode(enc)
            except UnicodeDecodeError:
                pass
            else:
                string = normalize_text(string)
                return {'plaintext': string.encode('utf-8')}, {}
        else:
            self.log.warning('Failed to decode text as %s', ', '.join(self.encodings))
            return {'plaintext': text}, {}


class PlaintextComparer(DigestComparerABC):
    """Реализует сравнение простого текста."""
    def __init__(self):
        self.matcher = difflib.SequenceMatcher[bytes]()
        self.last_newer_id: t.Optional[int] = None
        self.last_digest_type: t.Optional[str] = None
        self.log: t.Optional[logging.Logger] = None

    def initialize(self, log: logging.Logger, settings: dict[str, t.Any]) -> None:
        self.log = log

    @classmethod
    def plugin_name(cls) -> str:
        return 'plaintext'

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['plaintext'])

    def compare_digests(self, digest_type: str, older_id: int, older: bytes, newer_id: int, newer: bytes) -> float:
        assert older is not None and newer is not None
        if self.last_newer_id != older_id or self.last_digest_type != digest_type:
            self.matcher.set_seq2(newer.split(b'\n'))
            self.last_newer_id = older_id
            self.last_digest_type = digest_type
        self.matcher.set_seq1(older.split(b'\n'))
        similarity = self.matcher.ratio()
        return similarity
