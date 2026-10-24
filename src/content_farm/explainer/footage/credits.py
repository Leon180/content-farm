"""Description-box text for outside footage and for the links to video we may not show."""

from __future__ import annotations

from collections.abc import Sequence


def footage_credits_text(entries: Sequence[dict]) -> str:
    """One line per distinct clip: author, title, source, licence (+ licence URL for CC BY / BY-SA), page URL."""
    seen: dict[str, dict] = {}
    for e in entries:
        if e.get("kind") == "stock_video":
            seen.setdefault(str(e.get("source_url")), e)
    if not seen:
        return ""
    lines = ["外部影像素材 / Footage（免費或公有領域，畫面左上角標示來源）:"]
    for e in seen.values():
        licence = str(e.get("license", ""))
        if e.get("license_url") and e.get("attribution_required"):
            licence += f" {e['license_url']}"
        title = f"〈{e['title']}〉" if e.get("title") else ""
        lines.append(f"- {e.get('author') or 'Unknown'}{title}, {e.get('provider', '')}: {e.get('source_url')} ({licence})")
    if any(e.get("share_alike") for e in seen.values()):
        lines.append("（CC BY-SA 片段僅取數秒；該片段依原授權散布。）")
    return "\n".join(lines)


def reference_links_text(links: Sequence[object]) -> str:
    """Title + URL + one line each. These are linked, never shown in the video."""
    if not links:
        return ""
    lines = ["延伸觀看 / Original footage（版權屬原作者，本片畫面未使用，請至原處觀看）:"]
    for link in links:
        lines.append(f"- {link.title}: {link.url}\n  {link.note}")  # type: ignore[attr-defined]
    return "\n".join(lines)
