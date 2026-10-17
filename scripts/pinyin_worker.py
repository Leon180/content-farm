"""Text → pinyin, run with the local TTS venv's python (pypinyin lives only there, Leon 2026-10-17).

stdin: JSON list of strings. stdout: JSON list of lists of syllables with tone numbers
("zhong1"); characters pypinyin cannot read (Latin letters, digits) come back unchanged.
"""

import json
import sys

from pypinyin import Style, lazy_pinyin


def main() -> None:
    texts = json.load(sys.stdin)
    out = [lazy_pinyin(text, style=Style.TONE3, neutral_tone_with_five=True, errors=lambda s: list(s)) for text in texts]
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
