"""Реализует обработку гомоглифов в тексте. Буквы, похожие на латиницу, заменяются на латиницу."""
import homoglyphs as hg


__all__ = ['normalize_text']

hglyphs = hg.Homoglyphs(
    languages=['ru', 'en'],
    categories=('LATIN',),
    strategy=hg.STRATEGY_LOAD,
    ascii_strategy=hg.STRATEGY_IGNORE,
    ascii_range=range(ord('a'), ord('z'))
)
latin = frozenset(chr(i) for i in range(ord('a'), ord('z')+1)) | frozenset(chr(i) for i in range(ord('A'), ord('Z')+1))
replace = {}
for ch in latin:
    for alt in hglyphs.get_combinations(ch):
        replace[alt] = ch
table = str.maketrans(replace)


def normalize_text(text: str) -> str:
    """Заменяет символы в тексте на похожие символы латиницы, если таковые существуют."""
    return text.translate(table)
