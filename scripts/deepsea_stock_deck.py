"""Demo deck for the stock-footage trial: deepsea-1 with a few slides turned into free / public-domain NOAA footage.

    python scripts/deepsea_stock_deck.py --src output/deepsea-1/deck.json --out output/deepsea-1-stock/deck.json

Narration, ids and sources are untouched; only ``media`` of the chosen slides changes (kind stock_video, pinned Commons
file, cut window, on-screen note) and ``reference_links`` is added for the original videos we may not show.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

COMMONS = "https://commons.wikimedia.org/wiki/File:"
NOTE = "深海生物示意"
# slide id → footage (all NOAA, public domain / CC0 on Wikimedia Commons; windows skip title and end cards)
FOOTAGE = {
    "s25": {"query": "ctenophore Duobrachium", "keywords": ["duobrachium"], "frame": "panel_right", "end": 28.0,
            "url": COMMONS + "First_footage_of_Duobrachium_Sparksae.webm"},
    "s06": {"query": "psychedelic medusa jellyfish", "keywords": ["medusa"], "frame": "lower", "start": 6.0, "end": 60.0,
            "url": COMMONS + "Okeanos_Explorer_PR_and_USVI_Dive_8-_Psychedelic_Medusa-NOAA-1280x720.webm"},
    "s11": {"query": "deep sea fish rattail", "keywords": ["fish"], "frame": "panel_left", "end": 14.0,
            "url": COMMONS + "Ex1402-dive11_fish.webm"},
    "s13": {"query": "giant isopod bait", "keywords": ["bathynomus"], "frame": "panel_right", "start": 5.0, "end": 55.0,
            "url": COMMONS + "Bathynomus_giganteus_as_seen_by_remotely_operated_vehicle_(ROV)_Deep_Discoverer_at_a_depth"
                             "_of_816_meters_at_South_Reed,_Gulf_of_Mexico,_2017-11-30.webm"},
    "s21": {"query": "hydrothermal vents", "keywords": ["hydrothermal"], "frame": "lower", "start": 4.0, "end": 58.0,
            "url": COMMONS + "0501-hydrothermal-vents-640x360.webm"},
    "s16": {"query": "swimming sea cucumber", "keywords": ["animal"], "frame": "panel_left", "end": 44.0,
            "url": COMMONS + "Ex1402-dive06_red_animal.webm"},
}
REFERENCE_LINKS = [
    {"title": "Discovery／NHK 新聞稿：2012 年首次在棲地拍到活體大王烏賊",
     "url": "https://press.discovery.com/us/dsc/press-releases/2013/giant-squid-captured-video-its-natural-habita-2236",
     "note": "久保寺恒己團隊 2012 年 7 月在小笠原外海拍到的影像由 NHK 與 Discovery 持有版權，本片畫面未使用。"},
    {"title": "Smithsonian Magazine：Elusive giant squid captured on film for the first time",
     "url": "https://www.smithsonianmag.com/smart-news/elusive-giant-squid-captured-on-film-for-the-first-time-540930/",
     "note": "2013 年報導，附 2012 年影像的來龍去脈。"},
    {"title": "NOAA Ocean Exploration：2019 年墨西哥灣拍到大王烏賊（Here Be Monsters）",
     "url": "https://oceanexplorer.noaa.gov/expedition-feature/19biolum-logs-jun20/",
     "note": "Medusa 相機在 759 公尺拍到的影片，頁面標示影像由 Edie Widder 與 Nathan Robinson 提供（第三方版權），本片畫面未使用。"},
    {"title": "NOAA Ocean Exploration：Giant Squid 影片頁（2019）",
     "url": "https://oceanexplorer.noaa.gov/multimedia/edu-themes-bioluminescence-media-multimedia-giant-squid/",
     "note": "同一段 2019 年影片的原始下載頁。"},
]


def build(deck: dict) -> dict:
    sections = []
    for section in deck["sections"]:
        slides = []
        for slide in section["slides"]:
            spec = FOOTAGE.get(slide["id"])
            if spec is None:
                slides.append(slide)
                continue
            media = {"kind": "stock_video", "footage_note": NOTE, **spec}
            slides.append({**slide, "media": media})
        sections.append({**section, "slides": slides})
    return {**deck, "sections": sections, "reference_links": REFERENCE_LINKS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    deck = build(json.loads(args.src.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}: {len(FOOTAGE)} footage slides, {len(REFERENCE_LINKS)} reference links")


if __name__ == "__main__":
    main()
