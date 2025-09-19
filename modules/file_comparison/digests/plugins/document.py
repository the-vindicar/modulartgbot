"""Реализует сравнение текста из документов."""
import typing as t
import logging
import difflib

from ._base import DigestComparerABC


class DocumentComparer(DigestComparerABC):
    """Реализует сравнение текста отчётов и т.п. документов."""
    def __init__(self):
        self.matcher = difflib.SequenceMatcher[bytes]()
        self.last_newer_id: t.Optional[int] = None
        self.last_digest_type: t.Optional[str] = None
        self.log: t.Optional[logging.Logger] = None

    def initialize(self, log: logging.Logger, settings: dict[str, t.Any]) -> None:
        self.log = log

    @classmethod
    def plugin_name(cls) -> str:
        return 'document'

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['document'])

    def compare_digests(self, digest_type: str, older_id: int, older: bytes, newer_id: int, newer: bytes) -> float:
        assert older is not None and newer is not None
        if self.last_newer_id != older_id or self.last_digest_type != digest_type:
            self.matcher.set_seq2(newer.split(b'\n'))
            self.last_newer_id = older_id
            self.last_digest_type = digest_type
        self.matcher.set_seq1(older.split(b'\n'))
        similarity = self.matcher.ratio()
        return similarity

