"""Round 2 prompt set: 25 candidates per channel, built only from the principles in
round2/principles.md (no IP, character, author or brand names; no "style of").

Each candidate: (id, style key, subject sentence, colour sentence, one-line note in zh-TW).
``check_prompts()`` refuses the whole set if any prompt contains a banned term.
"""

from __future__ import annotations

import re

STYLES = {
    "blob": ("Tiny soft round character about 1.5 heads tall, mochi-like body with a flat bottom and almost no neck, "
             "tiny black dot eyes set wide apart and low on the face, very small mouth, flat colours, thin soft "
             "dark-brown outline, no shading, no texture."),
    "deadpan": ("Simple hand-drawn marker doodle character, slightly wobbly thick black line, minimal features, "
                "deadpan half-closed eyes and a flat mouth, one flat main colour plus white, dry humour."),
    "icon": ("Chunky character about two heads tall with a big round head and small body, strong simple silhouette "
             "that still reads when filled black, round single-colour eyes with one highlight, bold clean outline of "
             "one thickness, almost no inner lines, two or three flat colours."),
    "ink": ("Cute character drawn with confident East Asian brush-ink outlines of even weight, flat washes, tiny dot "
            "eyes, minimal details, no shading."),
    "pencil": ("Clean 2D animation key-frame drawing, crisp dark pencil outline of one weight, flat colours, round "
               "dot eyes, minimal inner lines, slight hand-drawn charm."),
    "sticker": ("Bold flat comic sticker, thick black outline of one weight, flat colours, no gradients, no shading, "
                "simple dot eyes, a short hard offset shadow."),
}
STYLE_ZH = {"blob": "療癒圓團", "deadpan": "台式死魚眼手繪", "icon": "粗框招牌剪影", "ink": "水墨筆線",
            "pencil": "動畫原畫鉛筆", "sticker": "漫畫貼紙"}

TAIL = ("Full body, front view, centered, generous margin around the figure. Plain pure white background. "
        "No text, no letters, no numbers, no logo, no watermark. An original character design. "
        "Minimal details, no patterns, at most one small prop.")

YOKAI = (
    ("Y01", "blob", "a little paper lantern spirit whose round glowing lantern is its whole body, two tiny feet, a red tassel underneath",
     "cream body, small cinnabar-red accents", "燈籠精：怕黑，偏偏自己就是燈"),
    ("Y02", "icon", "a small one-horned guardian beast pup with a curly ink-black mane and a single jade-green horn, a red seal tag on its collar",
     "cream body, black mane, small red accent", "獬豸幼獸：專頂沒有出處的說法"),
    ("Y03", "ink", "a slim bookworm larva scholar curled like a half-open scroll, tiny round glasses",
     "rice-paper cream body, ink-grey outline, one cinnabar dot", "書蟲學究（改細長身形，避開圓胖坐姿）"),
    ("Y04", "deadpan", "a talisman paper charm creature: a tall strip of yellow paper with a face, stubby arms, abstract red swirl marks that are not letters",
     "pale yellow paper, red swirl marks", "符紙精：被貼過太多次，表情很累"),
    ("Y05", "blob", "a tiny square seal-stamp creature with a small wooden knob handle on its head",
     "cinnabar-red body, cream face", "印章仔：蓋下去就是「出處確認」"),
    ("Y06", "icon", "a small fox kit with one big fluffy brush-like tail whose tip is dipped in black ink, holding a little lantern",
     "cream fur, black tail tip, small red lantern", "墨尾狐：只有一條尾巴，用尾巴寫字"),
    ("Y07", "ink", "a round owl scholar holding a bamboo scroll",
     "ink-grey feathers, cream face, small red ribbon", "夜讀貓頭鷹：只在半夜開館"),
    ("Y08", "blob", "a spirit shaped like a single drop of black ink, with a curl like a brush tip on top",
     "ink black body with white dot eyes, tiny red cheeks", "墨滴：古書裡掉出來的一滴墨"),
    ("Y09", "icon", "a little round bronze mirror spirit, disc-shaped body with a green patina rim, tiny arms",
     "bronze and verdigris green, cream face area", "銅鏡精：照出妖怪的原形"),
    ("Y10", "deadpan", "a sleepy grey cat traveller wearing a wide straw hat and holding a paper lantern",
     "grey cat, straw-yellow hat, red lantern", "說書貓（簡化版）：講到一半自己先怕"),
    ("Y11", "ink", "a little candle spirit with a short wax body and a flame-shaped hair tuft",
     "cream wax, small orange flame", "蠟燭精：一講鬼故事就閃爍"),
    ("Y12", "blob", "a tiny stone guardian lion pup with a curly mane, resting one paw on a small ball",
     "light stone grey, small red ribbon", "石獅子幼崽：守門守到睡著"),
    ("Y13", "icon", "a round wooden geomancy compass spirit whose needle sticks up like a single antenna",
     "warm wood brown, red needle, cream face", "羅盤精：專門找源頭的方向"),
    ("Y14", "ink", "a little frog scribe holding a calligraphy brush",
     "soft jade green, cream belly, black brush", "青蛙書記：抄經抄成近視"),
    ("Y15", "blob", "a beast made of a swirling white auspicious cloud, two tiny horns",
     "white cloud body, pale gold horns", "祥雲獸：一害羞就散開"),
    ("Y16", "deadpan", "a ghost made of an old torn book page, carrying a magnifying glass",
     "aged paper cream, black outline", "古籍頁鬼：一頁一頁幫你考據"),
    ("Y17", "icon", "a tiny dragon-turtle carrying a small blank stone tablet on its back",
     "jade green shell, grey tablet, cream face", "馱碑小龜：背著史料到處跑"),
    ("Y18", "ink", "a round magpie messenger holding a rolled letter",
     "ink black and white, small red string", "喜鵲信差：送來最早的那份記載"),
    ("Y19", "blob", "a small round bat with tiny wings",
     "ink black body, cinnabar-red ear tips", "福蝠：名字諧音「福」，其實很怕光"),
    ("Y20", "icon", "a calligraphy brush creature whose fluffy brush tip is its hair",
     "bamboo-cream body, black brush tip", "毛筆精：一激動就滴墨"),
    ("Y21", "ink", "a little mountain goat kid with one curled horn, a tiny scroll tied to the horn",
     "cream fur, grey horn, red tie", "山羊考據員：角上掛著今天的書單"),
    ("Y22", "deadpan", "a flat rectangular inkstone creature",
     "dark slate grey, cream face", "硯台精：被磨了幾百年，看破一切"),
    ("Y23", "blob", "a tiny mountain spirit: a rounded mossy rock with one leaf on top",
     "moss green, stone grey", "山精：山海經裡的山，都是牠的親戚"),
    ("Y24", "icon", "a little turtle carrying a lit paper lantern on its shell",
     "teal shell, warm lantern glow, cream face", "夜行燈龜：慢慢走，但每條路都走到底"),
    ("Y25", "ink", "a small paper-cut shadow-puppet figure with jointed round limbs",
     "cream and cinnabar red", "皮影偶：台灣民俗戲偶當說書人"),
)

OFFWORK = (
    ("O01", "deadpan", "a grey office cat in an oversized hoodie holding a coffee mug", "grey cat, charcoal hoodie, pink mug",
     "下班貓：……我已經下班了"),
    ("O02", "icon", "a cream puppy project manager with floppy brown ears, a blue shirt and a clipboard, far too cheerful",
     "cream and brown, blue shirt", "PM 狗：這個應該很快吧？"),
    ("O03", "sticker", "a pink sticky-note creature with stick arms and legs, one corner curling up", "pink note, black limbs",
     "便利貼精：這件事明天再說"),
    ("O04", "blob", "a round pufferfish office worker puffed up with anger, a tiny necktie", "cream body, pink tie",
     "河豚：我沒有生氣，只是有點腫"),
    ("O05", "deadpan", "a bubble milk tea cup creature with dark tapioca pearls inside and a straw as an antenna, exhausted",
     "milk-tea beige, dark pearls", "珍奶上班族：全糖是續命不是享受"),
    ("O06", "blob", "a melting slime blob flattened on the floor, wearing an employee ID lanyard", "pale mint body, blue lanyard",
     "融化史萊姆：週一早上的形狀"),
    ("O07", "sticker", "an alarm clock creature yelling with its mouth wide open", "white body, pink accents",
     "鬧鐘：每天叫你，自己也很累"),
    ("O08", "deadpan", "a wobbly white tofu block office worker wearing a necktie", "white tofu, blue tie",
     "豆腐社畜：一碰就碎，但還是來上班"),
    ("O09", "icon", "a capybara in a tiny necktie staring blankly ahead, perfectly calm", "warm brown, pink tie",
     "水豚經理：天塌下來也一樣表情"),
    ("O10", "blob", "a steamed bun creature with a pleated swirl on top, sleepy", "white bun, pink cheeks",
     "包子：被會議蒸到軟爛"),
    ("O11", "deadpan", "a penguin in a suit holding a briefcase", "black and white, blue tie", "企鵝社畜：穿得很正式，心已經下班"),
    ("O12", "sticker", "a computer mouse creature whose cable is its tail", "white body, pink cheeks", "滑鼠：被點了一整天"),
    ("O13", "blob", "a seal pup lying completely flat on its belly, exhausted", "pale grey, white belly", "癱平海豹：電量 1%"),
    ("O14", "deadpan", "a potted office cactus with one small bandage", "green cactus, terracotta pot", "辦公室仙人掌：唯一不用休假的同事"),
    ("O15", "icon", "a white rubber duck sitting in front of a tiny laptop", "white duck, orange beak, grey laptop",
     "除錯鴨：你講完 bug 就自己解了"),
    ("O16", "sticker", "a lunch box creature with two chopsticks sticking up like antennae", "red box, white rice", "便當：午休是牠唯一的高光時刻"),
    ("O17", "deadpan", "a sloth hanging from a desk lamp holding a mug", "warm brown, white mug", "樹懶：進度 0%，但很努力在掛著"),
    ("O18", "blob", "a round hamster sitting on a tiny office chair with a laptop", "orange and white", "倉鼠：輪子換成了專案"),
    ("O19", "icon", "a small anglerfish whose glowing lure is a tiny laptop screen, working late", "navy body, glowing screen",
     "加班燈籠魚：自帶光源所以不准下班"),
    ("O20", "deadpan", "a tired slice of white bread wearing a necktie", "toast beige, blue tie", "吐司：被夾在中間的中階主管"),
    ("O21", "sticker", "a single blank keyboard keycap creature running away", "white keycap, pink cheeks", "逃脫鍵：每天都想按自己"),
    ("O22", "blob", "a sleepy cat curled into a perfect loaf shape, wearing an ID lanyard", "cream cat, blue lanyard", "貓吐司：打卡後立刻變成麵包"),
    ("O23", "icon", "a grumpy owl in a cardigan holding a mug, working the night shift", "brown owl, blue cardigan", "夜貓子：大夜班資深員工"),
    ("O24", "deadpan", "an instant noodle cup creature with steam rising like hair", "white cup, red band", "泡麵：三分鐘就是一頓晚餐"),
    ("O25", "sticker", "a small stressed goldfish in an office water cooler bottle", "orange fish, pale blue water", "飲水機金魚：每次有人來裝水都嚇到"),
)

CEL = (
    ("C01", "icon", "a creature whose body is a dark film-strip frame with sprocket holes on both sides and a cream window as its face, a red pencil sticking up as a hair tuft",
     "charcoal frame, cream face, red pencil", "格仔：一秒 24 格，這一格是我"),
    ("C02", "blob", "a short stubby red colored-pencil creature with a pink eraser cap", "red pencil, pink eraser", "紅鉛筆：修正專用，看到錯就忍不住"),
    ("C03", "pencil", "a spirit made of a see-through animation cel sheet with three registration holes along the top, curled at the bottom",
     "pale cream, light blue edges", "透透：倉庫裡的老賽璐璐片"),
    ("C04", "icon", "a clapperboard creature whose striped top stick opens like a mouth", "black and white stripes, red cheeks",
     "場記板：每次開口都是「Cut！」"),
    ("C05", "blob", "a hedgehog whose spines are colored pencils", "cream face, multicolour pencil spines", "鉛筆刺蝟：全身都是工具"),
    ("C06", "pencil", "a round octopus animator with each tentacle holding a pencil", "soft coral body", "章魚原畫師：八隻手也趕不完進度"),
    ("C07", "deadpan", "a squished grey kneaded-eraser blob", "soft grey", "軟橡皮：被捏來捏去的外包"),
    ("C08", "icon", "a small robot whose head is a film reel", "silver body, red accents", "底片捲機器人：負責倒帶回顧業界史"),
    ("C09", "blob", "a small paint bottle creature with a drip of paint on its head", "white bottle, blue paint", "顏料瓶：一格一格上色的老師傅"),
    ("C10", "pencil", "a mole researcher with round glasses holding a clipboard with a grid sheet", "brown mole, white sheet",
     "鼴鼠研究員：挖數據挖到看不見"),
    ("C11", "icon", "a squirrel holding a giant pencil like a staff", "orange-brown fur, red pencil", "松鼠：把預算一顆一顆存起來"),
    ("C12", "deadpan", "a tired paper airplane folded from a storyboard sheet with blank panels", "white paper, blue panel lines",
     "分鏡紙飛機：飛不出會議室"),
    ("C13", "blob", "a flat square light-table creature glowing softly", "pale grey frame, warm white glow", "透寫台：熬夜時唯一亮著的東西"),
    ("C14", "pencil", "a small flipbook creature whose fluttering pages form its hair", "cream pages, red cover", "翻頁書：動畫最原始的祖先"),
    ("C15", "icon", "a panda accountant in a beret holding an abacus", "black and white, red beret", "熊貓會計：專算製作委員會的帳"),
    ("C16", "deadpan", "a crumpled paper ball of a rejected drawing", "white paper, grey lines", "廢稿紙團：被退了三次的原畫"),
    ("C17", "blob", "a tiny ink bottle wearing a pen nib as a hat", "dark blue bottle, silver nib", "墨水瓶：描線組資深員工"),
    ("C18", "pencil", "a cat researcher in a white lab coat with a red pencil behind its ear", "ginger cat, white coat", "研究員貓：看到不合理的數字就炸毛"),
    ("C19", "icon", "a round bird whose beak is a sharpened pencil", "pale blue bird, red pencil beak", "鉛筆鳥：啄一下就是一條線"),
    ("C20", "deadpan", "a coffee-stained grid timesheet paper creature", "white paper, blue grid, brown stain", "攝影表精：上面寫滿了延期"),
    ("C21", "blob", "a frog animator wearing a headband with a pencil tucked in it", "green frog, white headband", "青蛙動畫師：截稿前一天的樣子"),
    ("C22", "pencil", "a beaver stacking colored pencils like logs", "brown beaver, colourful pencils", "河狸：一根一根堆出一部作品"),
    ("C23", "icon", "a round stopwatch creature", "silver and red", "碼錶：計算一秒到底要幾張"),
    ("C24", "deadpan", "a long flat peg-bar creature with three small pegs on top like spikes", "light grey bar, black pegs",
     "定位尺：讓每一張都對得準"),
    ("C25", "blob", "a small round film canister creature with a strip of film sticking out like a tongue", "silver tin, dark film",
     "底片盒：吐舌頭的老膠卷"),
)

CHANNELS = {"yokai": YOKAI, "offwork": OFFWORK, "cel": CEL}

# Names from the reference IPs Leon picked (and their creators / publishers), plus other famous
# mascots our concepts sit near. Lower-cased, matched on word boundaries for latin, substring for CJK.
BANNED = (
    "chiikawa", "hachiware", "momonga", "sumikko", "sumikkogurashi", "san-x", "nagano",
    "pokemon", "pokémon", "pikachu", "nintendo", "game freak", "doraemon", "fujiko", "nobita",
    "pig girl", "duncan", "kirby", "totoro", "ghibli", "miyazaki", "sanrio", "hello kitty", "rilakkuma",
    "haechi", "molang", "pusheen", "snoopy", "line friends", "kakao",
    "in the style of", "style of", "inspired by",
    "吉伊卡哇", "角落生物", "寶可夢", "皮卡丘", "哆啦", "小叮噹", "豬小妹", "兔兔", "龍貓", "拉拉熊",
)


def prompt_for(style: str, subject: str, colour: str) -> str:
    return f"{STYLES[style]} The character: {subject}. Colours: {colour}. {TAIL}"


def banned_terms(text: str) -> list[str]:
    low = text.lower()
    hits = []
    for term in BANNED:
        if term.isascii():
            if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", low):
                hits.append(term)
        elif term in text:
            hits.append(term)
    return hits


def all_prompts() -> list[dict]:
    rows = []
    for code, items in CHANNELS.items():
        for i, (cid, style, subject, colour, note) in enumerate(items):
            rows.append({"id": cid, "channel": code, "style": style, "style_zh": STYLE_ZH[style], "note": note,
                         "seed": 200 + i, "prompt": prompt_for(style, subject, colour)})
    return rows


def check_prompts(rows: list[dict]) -> None:
    bad = {r["id"]: banned_terms(r["prompt"]) for r in rows}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        raise ValueError(f"banned terms in prompts: {bad}")
    if not banned_terms("cute mouse in the style of Pikachu") or not banned_terms("像吉伊卡哇"):
        raise AssertionError("banned-term detector failed its own control cases")
