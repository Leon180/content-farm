"""Shrink the kyubi description to <= 4800 bytes: keep summary, chapters, primary sources, artwork credits and the AI
disclosure; move the full source list to pinned-comment.txt. Reads the .bak copies so it is re-runnable.

python3 shrink_metadata.py <pack-dir>/yokai-kyubi-v3
"""
import re
import sys
from pathlib import Path

LIMIT = 4800
KEEP_SOURCES = ("山海經・南山經", "山海經・海外東經", "白虎通・封禪", "吳越春秋", "玄中記", "朝野僉載・補輯",
                "封神演義 第一回", "玉藻前（精選版", "殺生石（日本大百科", "Japan's 'killing stone'")


def size(text: str) -> int:
    return len(text.encode("utf-8"))


def main(folder: Path) -> int:
    original = (folder / "metadata.md.bak").read_text(encoding="utf-8")
    block = re.search(r"```text\n(.*?)\n```", original, re.S)
    if not block:
        print("no description block", file=sys.stderr)
        return 1
    lines = block.group(1).split("\n")
    start = lines.index("原典與參考文獻：")
    end = next(i for i, line in enumerate(lines) if line.startswith("（其餘參考文獻"))
    sources = [line for line in lines[start + 1:end] if line.startswith("• ")]
    kept = [line for line in sources if any(key in line for key in KEEP_SOURCES)]
    moved = [line for line in sources if line not in kept]
    head = lines[:start]
    tail = [line for line in lines[end + 1:]]
    # artwork URLs are not in the description; drop the second list of cited-report URL duplicate (Guardian is kept above)
    cited = tail.index("引用報導 / Cited reports（引用標題，非轉載全文）:")
    ai_start = tail.index("AI 示意圖 / AI illustrations（非史料，僅示意）:")
    tail = tail[:cited] + tail[ai_start:]
    new_lines = head + ["原典與參考文獻（主要；完整清單與畫作原頁連結見置頂留言）："] + kept + tail
    description = "\n".join(new_lines)
    if size(description) > LIMIT:
        print(f"still {size(description)} bytes", file=sys.stderr)
        return 1
    new_meta = original.replace(block.group(1), description)
    new_meta = new_meta.replace(
        "說明欄放不下全部連結（YouTube 上限 5000 字），完整清單在 `pinned-comment.txt`，上傳後貼成置頂留言。",
        "說明欄上限 5000 bytes，只放摘要、章節、主要原典、畫作署名與 AI 揭露；完整出處清單在 `pinned-comment.txt`，上傳後貼成置頂留言。")
    (folder / "metadata.md").write_text(new_meta, encoding="utf-8")

    old_pinned = (folder / "pinned-comment.txt.bak").read_text(encoding="utf-8").rstrip("\n").split("\n")
    first_art = next(i for i, line in enumerate(old_pinned) if line.startswith("畫作 / Artwork:"))
    old_refs = [line for line in old_pinned if line.startswith("• ")]
    artwork = old_pinned[first_art:]
    pinned = ["參考文獻與畫作原頁連結（完整版）", "", "原典與參考文獻："] + moved + old_refs + [""] + artwork
    # primary sources are already in the description; list them again so the pinned comment is the single complete list
    pinned = pinned[:3] + kept + pinned[3:]
    (folder / "pinned-comment.txt").write_text("\n".join(pinned) + "\n", encoding="utf-8")
    print(f"description {size(description)} bytes, kept {len(kept)} sources, moved {len(moved)}; "
          f"pinned {len(chr(10).join(pinned))} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
