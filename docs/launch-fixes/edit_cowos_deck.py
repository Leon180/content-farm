"""Launch fixes for the CoWoS deck (policy review 2026-10, C1): python edit_cowos_deck.py <run-dir>

Idempotent: reads deck.before.json (written on first run) and rewrites deck.json.
- s09: 7,722 mm² is the 9-reticle INTERPOSER (中介層), not a 「超級載板」; 載板 = ABF substrate (s18).
- s01/s03: no 「用二十四張圖」/「我先把結論放在這裡」 (shared with cel = template look).
- s02: the 「這是媒體轉述」 sentence leaves the hook; the card shows it as small text instead.
- title cards: outlet headline verbatim (媒體原標題) apart from the channel summary.
- new section 「晶片貓的算盤」: own geometry estimate + three judgments (take slides), +~80 s.
"""
import copy
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
    "register-2023": "TSMC warns AI chip crunch will last another 18 months",
    "trendforce-ap8": "TSMC Acquires Innolux's Plant in Southern Taiwan to Expand Advanced Packaging Capacity",
    "taiwannews-2024-10": "Taiwan’s TSMC fixes Nvidia Blackwell design flaw",
    "techtimes-2026-07": "TSMC Posts Record Quarter as AI Chip Demand Pushes Full-Year Growth Outlook Past 40%",
}
for source in deck["sources"]:
    if source["id"] in HEADLINES:
        source["headline"] = HEADLINES[source["id"]]

deck["description"] = (
    "AI 晶片卡在 CoWoS，不是因為沒人會做，而是這門手藝被冷落多年，需求兩年內爆發，蓋廠卻要好幾年。"
    "這集從封裝、HBM、中介層三個名詞開始，追 CoWoS 從冷門變咽喉的十年，拆解誰做哪一段、台灣站在哪裡；"
    "晶片貓也自己算了一筆帳：中介層越做越大，一片晶圓能做的封裝反而越少。"
    "片中引用的媒體報導以「據報導」標示，新聞卡上分開列出媒體原標題與本頻道摘要。資料截至 2026-10。"
)

slides["s01"]["narration"] = ("全世界都在搶 AI 晶片，但真正卡住出貨的，常常不是晶片本身，而是把晶片包起來的那一步。"
                              "我是晶片貓，今天要拆的這一關，叫 CoWoS。")
slides["s02"]["narration"] = ("時間拉回 2023 年 9 月。據日經報導，台積電董事長說，公司大約只能滿足 80% 的 CoWoS 需求，"
                              "新產能要再等約 18 個月。")
slides["s02"]["media"]["summary"] = "80%：2023-09 據日經報導的董事長說法（媒體轉述，非逐字引言）"
slides["s03"]["narration"] = ("晶片貓的論點先押在這裡。CoWoS 不是什麼沒人會的黑科技，它被冷落了很多年；"
                              "等到 AI 突然需要它，蓋廠、買機台、練良率都要時間。卡住全世界的，是時間差，不是技術差。"
                              "接下來，我們一張一張證明它。")

s09 = slides["s09"]
s09["heading"] = "拼出更大的中介層"
s09["body"] = {"value": "9", "unit": "倍光罩", "caption": "台積電規劃的 9 倍光罩中介層，面積 7,722 mm²"}
s09["narration"] = ("曝光機一次能印的面積有上限，大約 26 乘 33 毫米，就像影印機一次只能印一張 A4。"
                    "要做更大的中介層，就得把好幾張拼起來印。2024 年底的技術報導說，台積電當時量產 3.3 倍，"
                    "承諾 5.5 倍，還規劃 9 倍光罩大小的中介層，面積 7,722 平方毫米，差不多是 8.8 公分見方。")

# beats: keep 「≤ 3 slides without a beat」 and never the same beat twice in a row
slides["s19"]["beat"] = None
slides["s20"]["beat"] = "gossip"

slides["s24"]["narration"] = ("所以 AI 晶片卡在這一關，真正的意思是：一門被冷落多年的手藝，被要求從 2024 年底約 3.5 萬片，"
                              "兩年內長到 13 萬片以上。卡住的是蓋廠、買機台、練良率的時間，而這段時間，大部分發生在台灣。"
                              "晶片貓只拆產業、不報明牌。我是晶片貓，我們下一關見。")

NEW = [
    {"id": "k1", "layout": "big_number", "heading": "一片晶圓排得下幾片",
     "body": {"value": "≈5", "unit": "片", "caption": "12 吋晶圓排 9 倍光罩中介層（本頻道以正方形幾何粗估）"},
     "narration": ("晶片貓自己算了一筆帳。一片 12 吋晶圓，扣掉邊緣，把中介層當成正方形去排："
                   "2016 年 P100 那種約 830 平方毫米的，大約排得下 70 片；3.3 倍光罩剩 17 片左右；"
                   "9 倍光罩的 7,722 平方毫米，只放得下大約 5 片。這是我們的幾何粗估，不是台積電的數字。"
                   "中介層長大的速度，跟我的體重一樣，只會往上。"),
     "source_ids": ["pcper-2016", "iftle-615"], "beat": "joke", "take": True,
     "mascot": {"pose": "shocked"}, "media": {"kind": "animated", "animation": "count_up"}},
    {"id": "k2", "layout": "compare", "heading": "產能翻倍，晶片不一定翻倍",
     "body": {"left": {"label": "新聞常算的", "items": ["每月幾萬片晶圓", "兩年長到四倍"]},
              "right": {"label": "也要一起看的", "items": ["每片排幾個封裝", "中介層越做越大"]}},
     "narration": ("所以新聞說月產能從 3 萬多片長到 13 萬片，算的是晶圓片數。可是每一代 AI 晶片的中介層都在變大，"
                   "同一片晶圓能做的封裝數反而變少。晶圓翻倍，能出貨的晶片不一定跟著翻倍。"
                   "我的判斷是，這是產能一直擴、交期卻還是一年起跳的原因之一。"),
     "source_ids": ["trendforce-2024-03", "trendforce-2026-08", "techtimes-2026-07"], "take": True,
     "mascot": {"pose": "think"}, "media": {"kind": "animated", "animation": "reveal_list"}},
    {"id": "k3", "layout": "bullets", "heading": "晶片貓的三個判斷",
     "body": {"items": ["瓶頸是時間，不是技術", "晶片越大，越吃產能", "下一關：基板與面板"]},
     "narration": ("把整支片收成三個判斷。第一，卡住的是蓋廠、買機台、練良率的時間，不是沒人會做。"
                   "第二，AI 晶片越做越大，每片晶圓能做的數量越少，產能數字要打折看。"
                   "第三，瓶頸會往外搬，ABF 基板和面板級封裝，是下一個要盯的地方。這是晶片貓的解讀，不是投資建議。"),
     "source_ids": ["tvbs-2026-04", "trendforce-2026-09"], "take": True,
     "mascot": {"pose": "point"}, "media": {"kind": "animated", "animation": "reveal_list"}},
    {"id": "k4", "layout": "bullets", "heading": "看新聞時盯這三個數字",
     "body": {"items": ["交期：還是 50 週以上？", "CoW 外包比例變大沒", "ABF 基板稼動率"]},
     "narration": ("如果你想自己追這條線，下次看新聞可以盯三個數字。一，CoWoS 交期是不是還在 52 週以上；"
                   "二，CoW 外包給封測廠的比例有沒有變大；三，ABF 基板廠的產能利用率，是不是還在九成以上。"
                   "三個數字一起鬆下來，這一關才算真的開了。"),
     "source_ids": ["techtimes-2026-07", "trendforce-2026-08", "tvbs-2026-04"],
     "mascot": {"pose": "smug"},
     "media": {"kind": "stock", "query": "person reading news on smartphone",
               "keywords": ["news", "smartphone", "phone", "reading"]}},
]

sections = deck["sections"]
last = sections[-1]               # 沒人知道的事與結論: s21 s22 s23 s24
assert [s["id"] for s in last["slides"]] == ["s21", "s22", "s23", "s24"], last["slides"]
unknown = {**last, "title": "沒人說得準的兩件事", "slides": [slides["s21"], slides["s22"]]}
take = {"title": "晶片貓的算盤：晶片越大，越吃產能", "slides": NEW[:3]}
ending = {"title": "結論：卡住的是時間", "slides": [NEW[3], slides["s23"], slides["s24"]]}
deck["sections"] = [*sections[:-1], unknown, take, ending]

(run / "deck.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("slides:", sum(len(s["slides"]) for s in deck["sections"]))
