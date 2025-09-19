"""Реализует извлечение текста из документа в формате PDF для последующего сравнения."""
import typing as t
from fnmatch import fnmatch
import io
import logging
import re

import pdfplumber

from ._base import DigestExtractorABC
from ._homoglyphs import normalize_text


__all__ = ['PdfExtractor']


class PdfExtractor(DigestExtractorABC):
    """Извлекает дайджест из pdf-файлов."""
    WHITESPACE_COLLAPSE = re.compile(r'[ \t]+')

    def __init__(self):
        self.mimetypes: t.Collection[str] = []
        self.masks: t.Collection[str] = []
        self.log: t.Optional[logging.Logger] = None

    def initialize(self, log: logging.Logger, settings: dict[str, t.Any]) -> None:
        self.log = log
        self.mimetypes = frozenset(settings.get(
            'mimetypes', ['application/pdf']
        ))
        self.masks = frozenset(settings.get(
            'masks', ['*.pdf']
        ))

    @classmethod
    def plugin_name(cls) -> str:
        return 'pdf'

    def can_process_file(self, filename: str, mimetype: str, filesize: int) -> bool:
        return (mimetype in self.mimetypes) or any(fnmatch(filename, mask) for mask in self.masks)

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['document'])

    def process_file(self, filename: str, mimetype: str, content: bytes) -> tuple[dict[str, bytes], dict[str, str]]:
        textlines: list[bytes] = []  # строки текста отчёта
        warnings: dict[str, str] = {}  # предупреждения
        with (io.BytesIO(content) as buffer, pdfplumber.PDF(buffer) as pdf):
            for page in pdf.pages:
                text = page.extract_text()
                for line in text.split('\n'):
                    line = self.WHITESPACE_COLLAPSE.sub(' ', line).strip(' \t\r\n')
                    line = normalize_text(line)
                    textlines.append(line.encode('utf-8'))
        return {'document': b'\n'.join(textlines)}, warnings
