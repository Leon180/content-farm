"""Launch fixes for the cel deck (policy review 2026-10, C4): python edit_cel_deck.py <run-dir>

Idempotent: reads deck.before.json (written on first run) and rewrites deck.json.
- s03: 「六成說今年比較難過」 → 「六成業績變差」 (it is financial data, not what companies said).
- s10: on-screen note 「本頻道依兩項不同口徑資料估算」 for the self-computed ≈12%.
- s01/s04/s24: cel's own opening and sign-off; no wording shared with 晶片貓.
- title cards: outlet headline verbatim (媒體原標題) apart from the channel summary.
- new section: MAPPA's 100%-funded Chainsaw Man as the counter-case, plus 研究室的看法 (take), +~80 s.
"""
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
before = run / "deck.before.json"
if not before.is_file():
    before.write_text((run / "deck.json").read_text(encoding="utf-8"), encoding="utf-8")
deck = json.loads(before.read_text(encoding="utf-8"))
slides = {s["id"]: s for sec in deck["sections"] for s in sec["slides"]}

HEADLINES = {  # fetched 2026-10-16 (h1 / og:title), see REPORT-launch-fixes.md
    "tdb-2024-anime-prod-market": "アニメ制作市場　2024年は3621億円　過去最高を更新　元請制作の6割が「業績悪化」アニメーター不足が顕在化",
    "tdb-2025-anime-prod-market": "アニメ制作市場、初の4千億円突破もピークアウトの可能性―人手不足と自社IPが鍵か―帝国データバンクが業界調査",
    "jftc-creator-trade-survey-2025": "(令和7年12月24日)映画・アニメの制作現場におけるクリエイターの取引環境に係る実態調査について",
    "toei-fy2026-revision": "東映アニメ、26年3月期通期の連結業績予想を上方修正　海外における版権事業の好調や為替差益の計上、有価証券売却益を計上などで　期末配当予想も増配に",
    "netflix-mappa-2026": "Netflix and MAPPA expand partnership to launch exclusive global anime slate",
    "gainax-bankruptcy-2024": "アニメ制作会社ガイナックスが破産申請。多額の負債を抱え「完全に運営能力を喪失」",
}
for source in deck["sources"]:
    if source["id"] in HEADLINES:
        source["headline"] = HEADLINES[source["id"]]

NEW_SOURCES = [
    {"id": "ann-2022-chainsawman", "title": "MAPPA Team Discuss Chainsaw Man Anime",
     "url": "https://www.animenewsnetwork.com/convention/2022/anime-expo/mappa-team-discuss-chainsaw-man-anime/.187194",
     "note": "publisher=Anime News Network; published=2022-07-11; accessed=2026-10-16; type=press; "
             "Makoto Kimura (MAPPA producer): no committee, 100% MAPPA",
     "publisher": "Anime News Network", "published": "2022-07-11",
     "headline": "MAPPA Team Discuss Chainsaw Man Anime"},
    {"id": "toyokeizai-2023-mappa",
     "title": "｢呪術廻戦｣制作会社が挑むアニメ業界の悪習打破 MAPPAが｢チェンソーマン｣に100％出資した狙い",
     "url": "https://toyokeizai.net/articles/-/672004",
     "note": "publisher=東洋経済オンライン; published=2023-05-17; accessed=2026-10-16; type=press; "
             "interview with MAPPA president Manabu Otsuka (収支は完全に成功; パッケージはもっと行きたかった)",
     "publisher": "東洋経済オンライン", "published": "2023-05-17"},
    {"id": "ann-2023-otsuka", "title": "MAPPA CEO Reflects on Financial Performance of Chainsaw Man",
     "url": "https://www.animenewsnetwork.com/interest/2023-05-18/mappa-ceo-reflects-on-financial-performance-of-chainsaw-man/.198194",
     "note": "publisher=Anime News Network; published=2023-05-18; accessed=2026-10-16; type=press; "
             "does not plan to invest 100% in all future titles",
     "publisher": "Anime News Network", "published": "2023-05-18"},
]
deck["sources"] = [*deck["sources"], *NEW_SOURCES]

deck["description"] = (
    "2024 年日本動畫市場 3 兆 8,407 億日圓創新高，承包整部作品的製作公司卻有六成業績變差。"
    "這一卷帳本對的是：製作委員會是什麼、觀眾的錢在哪裡轉彎、為什麼有版權的人和只拿工錢的人差這麼多，"
    "MAPPA 自己出資做《鏈鋸人》換來什麼，以及台灣在這條河上的位置。"
    "約 12% 這個比例是本頻道依兩項不同口徑的資料估算，只能當量級看。資料截至 2026-10。"
)

slides["s01"]["narration"] = ("動畫一部比一部紅，周邊一檔比一檔貴，可是新聞裡的動畫公司，常常在虧錢、在倒閉。"
                              "這裡是賽璐璐研究室。CUT 01，同一年的兩則新聞，放在一起看，帳就對不起來。")
slides["s03"]["heading"] = "同一年：六成主力業績變差"
slides["s03"]["narration"] = ("再看第二個新聞。帝國資料銀行調查承包整部作品的製作公司，2024 年有 34.5% 虧損，"
                              "虧損加上減益，合計 60.0%。史上最好賺的一年，主力製作公司有六成業績變差。")
slides["s04"]["narration"] = ("這兩件事同時成立，不是誰在說謊，而是動畫市場和動畫公司，根本不是同一個錢包。"
                              "研究室先把這集的論點寫在場記板上：製作公司領的是工錢，不是分紅。"
                              "動畫主角可以靠友情逆轉，損益表不行。")
slides["s10"]["body"]["caption"] = "業界市場 ÷ 廣義市場，2024 年（本頻道依兩項不同口徑資料估算）"
slides["s10"]["take"] = True
slides["s24"]["take"] = True
slides["s24"]["narration"] = ("所以，動畫市場創新高和動畫公司很窮，並不矛盾。觀眾的錢先經過窗口、經過委員會，"
                              "最後只有約一成多回到製作公司，而且開工前就談定。想翻身的公司，做的都是同一件事：自己出資，自己拿版權。"
                              "下次聽到某部動畫賣爆了，可以多問一句：賣爆的錢，進了誰的帳？這裡是賽璐璐研究室，這卷帳本先對到這裡。")

NEW = [
    {"id": "c1", "layout": "quote", "heading": "有人真的不組委員會",
     "body": {"text": "不組委員會，這部 100% 由 MAPPA 來做。", "who": "MAPPA 製作人 Makoto Kimura（2022，中譯）"},
     "narration": ("真的有公司試過繞開委員會。2022 年的電視動畫鏈鋸人，MAPPA 的製作人在美國動漫展上說，"
                   "他們提案時就表明不組委員會，百分之百由 MAPPA 出資製作，也因此拿到了原作的動畫化授權。"
                   "動畫裡換老闆通常是劇情轉折，這次是製作公司自己當老闆。"),
     "source_ids": ["ann-2022-chainsawman"], "beat": "joke",
     "media": {"kind": "title_card", "source_id": "ann-2022-chainsawman",
               "headline": "MAPPA 製作人：鏈鋸人不組委員會，100% 自己出資", "summary": "2022-07 美國動漫展座談"}},
    {"id": "c2", "layout": "compare", "heading": "自己出資，帳怎麼算",
     "body": {"left": {"label": "委員會模式", "items": ["製作費開工前談定", "賠了不用扛"]},
              "right": {"label": "100% 自己出資", "items": ["收益自己拿", "虧損也自己扛"]}},
     "narration": ("差別在風險。委員會模式，製作公司領固定的製作費，大賣不會追加，賠了也不用扛；"
                   "百分之百自己出資，賺了自己拿，賠了也自己扛。東洋經濟訪問 MAPPA 社長大塚學，"
                   "他說收支上可以說是完全成功；但藍光這類實體商品，坦白說，他希望能賣到更多觀眾手上。"),
     "source_ids": ["toyokeizai-2023-mappa", "production-committee-nlab"],
     "media": {"kind": "animated", "animation": "reveal_list"}},
    {"id": "c3", "layout": "bullets", "heading": "研究室的看法",
     "body": {"items": ["出資，就是買回版權", "前提是扛得住虧損", "專門工作室難複製"]},
     "narration": ("研究室的看法是：鏈鋸人證明了製作公司也拿得回版權，但前提是口袋夠深。"
                   "連 MAPPA 社長後來都說，不打算每一部都百分之百出資。對平均年營收只有 4 億多日圓的專門工作室來說，"
                   "要自己押下一整部作品，風險大得多。所以真正的問題不是委員會好不好，而是誰扛得起風險，誰就拿得到版權。"),
     "source_ids": ["ann-2023-otsuka", "tdb-2024-anime-prod-market"], "beat": "gossip", "take": True,
     "media": {"kind": "animated", "animation": "reveal_list"}},
]

sections = deck["sections"]
titles = [sec["title"] for sec in sections]
at = titles.index("還不知道的事與結論")
experiment = {"title": "一個實驗：製作公司自己出資", "slides": NEW}
deck["sections"] = [*sections[:at], experiment, *sections[at:]]

(run / "deck.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("slides:", sum(len(s["slides"]) for s in deck["sections"]))
