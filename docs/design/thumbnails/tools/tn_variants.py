"""The three thumbnail variants per launch video (docs/design/thumbnails/rules.md).

Every line and number below is spoken in the video's first 60 seconds (narration checked by hand
against script.json, then by QC: promise_findings). Key-art prompts carry no IP / brand names.
"""

from __future__ import annotations

KEYART_TAIL = "Illustration, not a photograph. No text, no letters, no numbers, no logos, no watermark."

VIDEOS = {
    "cowos": {
        "source": "cowos-chipcat", "channel": "chipcat", "vertical": False,
        "keyart_prompt": ("Editorial illustration: one glowing AI processor chip stuck at the front of a long queue of "
                          "identical chips on a factory conveyor belt, waiting at a closed packaging station gate, "
                          "clean flat vector style, deep navy and warm amber colours, strong contrast, plain background. "
                          + KEYART_TAIL),
        "variants": {
            "a": {"layout": "character", "lines": ["卡住 AI 的", "不是晶片"], "highlight": "不是晶片", "sub": "是時間差",
                  "visual": {"kind": "mascot", "pose": "shocked"}, "promise": ["卡住出貨的", "是時間差"]},
            "b": {"layout": "keyart", "lines": ["AI 晶片", "卡在哪？"], "highlight": "卡在哪",
                  "visual": {"kind": "image", "path": "keyart/keyart.png", "credit": "AI 示意圖（FLUX.2 klein）"},
                  "promise": ["真正卡住出貨的"]},
            "c": {"layout": "compare", "lines": ["產能夠嗎？"], "visual": {"kind": "mascot", "pose": "think"},
                  "compare": [{"value": "80%", "label": "需求能滿足"}, {"value": "18", "label": "個月等產能"}],
                  "promise": ["80%", "18 個月"]},
        },
    },
    "short7722": {
        "source": "chipcat-7722-launch", "channel": "chipcat", "vertical": True,
        "keyart_prompt": ("Editorial illustration, top-down view: a large glossy square silicon interposer tile with fine "
                          "gold circuit traces lying on a dark navy desk beside a round silicon wafer, dramatic soft light, "
                          "clean modern style. " + KEYART_TAIL),
        "variants": {
            "a": {"layout": "character", "lines": ["7,722", "平方毫米"], "highlight": "7,722",
                  "visual": {"kind": "mascot", "pose": "shocked"}, "promise": ["7,722 平方毫米"]},
            "b": {"layout": "keyart", "lines": ["8.8 公分", "的中介層"], "highlight": "8.8 公分",
                  "visual": {"kind": "image", "path": "keyart/keyart.png", "credit": "AI 示意圖"},
                  "promise": ["8.8 公分"]},
            "c": {"layout": "compare", "lines": ["拼到幾倍？"], "visual": {"kind": "mascot", "pose": "point"},
                  "compare": [{"value": "9", "label": "倍光罩"}], "promise": ["9 倍"]},
        },
    },
    "kyubi": {
        "source": "yokai-kyubi-launch", "channel": "yokai", "vertical": False, "keyart_prompt": None,
        "variants": {
            "a": {"layout": "character", "lines": ["九尾狐", "會吃人？"], "highlight": "吃人", "sub": "最早的原典",
                  "visual": {"kind": "mascot", "pose": "shocked"}, "promise": ["會吃人", "最早寫到牠的書"]},
            "b": {"layout": "keyart", "lines": ["牠跟美女", "沒關係？"], "highlight": "美女",
                  "visual": {"kind": "image", "path": "assets/artwork/hokusai_fox.jpg",
                             "credit": "葛飾北齋〈九尾狐〉大都會博物館 CC0", "focus": "center"},
                  "promise": ["跟美女一點關係都沒有"]},
            "c": {"layout": "compare", "lines": ["原本會吃人"], "highlight": "吃人",
                  "visual": {"kind": "mascot", "pose": "smug"},
                  "compare": [{"value": "九", "label": "條尾巴"}], "promise": ["九條尾巴", "會吃人"]},
        },
    },
    "cel": {
        "source": "cel-ep1", "channel": "cel", "vertical": False,
        "keyart_prompt": ("Simple hand-drawn editorial illustration of an empty animation studio desk at night: a glowing "
                          "light table, stacks of pencil drawings on paper, a red pencil and a calculator, warm paper "
                          "colours, original, no characters. " + KEYART_TAIL),
        "variants": {
            "a": {"layout": "character", "lines": ["史上最好賺", "卻在虧？"], "highlight": "虧",
                  "visual": {"kind": "mascot", "pose": "shocked"}, "promise": ["史上最好賺的一年", "虧損"]},
            "b": {"layout": "keyart", "lines": ["錢去哪了？"],
                  "visual": {"kind": "image", "path": "keyart/keyart.png", "credit": "AI 示意圖（FLUX.2 klein）"},
                  "sub": "帳對不起來", "promise": ["帳就對不起來"]},
            "c": {"layout": "compare", "lines": ["市場新高", "公司虧損？"], "highlight": "虧損",
                  "visual": {"kind": "mascot", "pose": "deadpan"},
                  "compare": [{"value": "34.5%", "label": "虧損"}, {"value": "60%", "label": "業績變差"}],
                  "promise": ["34.5% 虧損", "60.0%"]},
        },
    },
}
