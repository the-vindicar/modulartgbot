"""Реализует извлечение текста из документа в формате DOCX для последующего сравнения."""
import typing as t
from collections import defaultdict
import dataclasses
from fnmatch import fnmatch
import io
import logging
import re
import xml.dom.minidom
import zipfile

from ._base import DigestExtractorABC
from ._homoglyphs import normalize_text


__all__ = ['DocxExtractor']


def _query_xml(root, *path: str) -> t.Union[xml.dom.Node, str, None]:
    current = root
    for part in path:
        if part == '@':
            bits = [child.data for child in current.childNodes if child.nodeType == child.TEXT_NODE]
            return ''.join(bits)
        elif part.startswith('@'):
            return current.getAttribute(part[1:]) if current.hasAttribute(part[1:]) else None
        elif part.startswith('*'):
            for node in current.getElementsByTagName(part[1:]):
                current = node
                break
            else:
                return None
        else:
            for child in current.childNodes:
                if child.nodeType == child.ELEMENT_NODE and child.tagName == part:
                    current = child
                    break
            else:
                return None
    return current


@dataclasses.dataclass
class Style:
    """Описание стиля документа."""
    default: bool
    base: t.Optional[str]
    font: t.Optional[str]
    justify: t.Optional[str]
    color: t.Optional[str]
    size: t.Optional[int]


class _StyleTable(t.Mapping[str, Style]):
    """Таблица стилей позволяет определить итоговый вид заданного стиля для документа."""
    def __init__(self, style_file: t.IO[bytes]):
        self._table: dict[str, Style] = {}
        with xml.dom.minidom.parse(style_file) as styles:
            for style in styles.getElementsByTagName('w:style'):
                style_id = _query_xml(style, '@w:styleId')
                default = bool(_query_xml(style, '@w:default'))
                justify = _query_xml(style, 'w:pPr', 'w:jc', '@w:val')
                based_on = _query_xml(style, 'w:basedOn', '@w:val')
                fontname = _query_xml(style, 'w:rPr', 'w:rFonts', '@w:hAnsi')
                color = _query_xml(style, 'w:rPr', 'w:color', '@w:val')
                try:
                    size = int(_query_xml(style, 'w:sz', '@w:val'))
                except (TypeError, ValueError):
                    size = None
                if not fontname and not based_on:
                    continue
                self._table[style_id] = Style(
                    default=default,
                    base=based_on,
                    font=fontname,
                    color=color,
                    size=size,
                    justify=justify
                )
                if default:
                    self._table[''] = self._table[style_id]

    def __getitem__(self, name: str) -> t.Optional[Style]:
        styles = []
        visited = {name}
        current = self._table.get(name, None)
        while current is not None:
            styles.insert(0, current)
            if current.base is not None and current.base not in visited and current.base in self._table:
                current = self._table[current.base]
                visited.add(current.base)
            else:
                current = None
        if '' in self._table:
            result = self._table['']
        elif styles:
            result = styles[0]
        else:
            raise KeyError(name)
        for item in styles:
            result = dataclasses.replace(result, **{k: v for k, v in dataclasses.asdict(item).items() if v is not None})
        return result

    def __len__(self) -> int:
        return len(self._table)

    def __iter__(self) -> t.Iterator[str]:
        return iter(self._table)


class DocxExtractor(DigestExtractorABC):
    """Извлекает дайджест из docx-файлов."""
    WHITESPACE_COLLAPSE = re.compile(r'[ \t]+')

    def __init__(self):
        self.mimetypes: t.Collection[str] = []
        self.masks: t.Collection[str] = []
        self.accepted_fonts: t.Collection[str] = []
        self.font_threshold: float = 0.0
        self.log: t.Optional[logging.Logger] = None

    def initialize(self, log: logging.Logger, settings: dict[str, t.Any]) -> None:
        self.log = log
        self.mimetypes = frozenset(settings.get(
            'mimetypes', ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        ))
        self.masks = frozenset(settings.get(
            'masks', ['*.docx']
        ))
        self.accepted_fonts = frozenset(settings.get(
            'accepted_fonts', ['Times New Roman', 'Arial', 'Courier New']
        ))
        self.font_threshold = float(settings.get(
            'font_threshold', 0.1
        ))

    @classmethod
    def plugin_name(cls) -> str:
        return 'docx'

    def can_process_file(self, filename: str, mimetype: str, filesize: int) -> bool:
        return (mimetype in self.mimetypes) or any(fnmatch(filename, mask) for mask in self.masks)

    @classmethod
    def digest_types(cls) -> frozenset[str]:
        return frozenset(['document'])

    def process_file(self, filename: str, mimetype: str, content: bytes) -> tuple[dict[str, bytes], dict[str, str]]:
        textlines: list[bytes] = []  # строки текста отчёта
        line_bits: list[str] = []  # фрагменты собираемой строки текста
        font_lengths: dict[str, int] = defaultdict(int)  # использование разных шрифтов, в символах
        warnings: dict[str, str] = {}  # предупреждения
        with (io.BytesIO(content) as buffer, zipfile.ZipFile(buffer) as docx):
            with (
                docx.open('word/document.xml', 'r') as content,
                docx.open('word/styles.xml', 'r') as styles,
                xml.dom.minidom.parse(content) as doc,
            ):
                style_info = _StyleTable(styles)
                for paragraph in doc.getElementsByTagName('w:p'):  # перебираем абзацы документа
                    # извлекаем текст абзаца
                    line_bits.clear()
                    for text in paragraph.getElementsByTagName('w:t'):
                        line_bits.extend(node.data for node in text.childNodes if node.nodeType == node.TEXT_NODE)
                    # избавляемся от лишних пробелов
                    line = str.strip(''.join(line_bits))
                    line = self.WHITESPACE_COLLAPSE.sub(' ', line)
                    # преобразуем гомоглифы
                    line = normalize_text(line)
                    bline = line.encode('utf-8')
                    if bline:
                        textlines.append(bline)
                    # извлекаем сведения о шрифтах
                    try:
                        p_style_name = _query_xml(paragraph, 'w:pPr', 'w:pStyle', '@w:val')
                        p_font = style_info[p_style_name].font if p_style_name else style_info[''].font
                        for run in paragraph.getElementsByTagName('w:r'):
                            r_style_name = _query_xml(run, 'w:rPr', 'w:rStyle', '@w:val')
                            r_font = style_info[r_style_name].font if r_style_name else None
                            r_spec_font = _query_xml(run, 'w:rPr', 'w:rFonts', '@w:hAnsi')
                            font = r_spec_font or r_font or p_font
                            if font and font not in self.accepted_fonts:
                                text = _query_xml(run, 'w:t', '@') or ''
                                font_lengths[font] += len(text.strip())
                    except KeyError:
                        pass
                self.log.debug('%d lines left after trimming whitespace', len(textlines))
                total = sum(font_lengths.values())
                if total > 0:
                    wrong_fonts = []
                    for font, usage in font_lengths.items():
                        if usage > self.font_threshold * total:
                            wrong_fonts.append(f'{font}: {usage / total:.1%}')
                    if wrong_fonts:
                        warnings['wrong_fonts'] = '; '.join(wrong_fonts)
        return {'document': b'\n'.join(textlines)}, warnings
