# Style Palette for Storyboard Generator

此檔案定義 `/project:storyboard` 產出 Nano Banana prompt 時可選用的視覺風格。
每個 shot 可從中挑一種，**同一個變體內可混搭不同風格**。

編輯此檔案即可新增/移除/修改風格。skill 會讀取這裡的定義。

---

## 可用風格

### cinematic_doc — 電影感紀錄片風
National Geographic / BBC Earth 調性。高質感、淺景深、戲劇性光影。
```
cinematic documentary photography, National Geographic style,
shallow depth of field, dramatic lighting, high quality,
realistic skin tones, emotional atmosphere
```
**適用：** Hook 段、情感收尾、真實場景

---

### textbook_diagram — 教科書示意圖風
復古紙張質感、箭頭標註、圖解風格。用來解釋原理、機制、流程。
```
vintage textbook illustration, educational diagram style,
labels with arrows, aged cream paper background,
flat limited colors, thick black outlines, retro science book aesthetic
```
**適用：** 原理解釋、機制揭露、步驟說明

---

### vintage_cartoon — 老卡通風（Hanna-Barbera）
1960s Flintstones 風格。扁平色塊、粗黑線條、誇張比例。
```
1960s vintage Hanna-Barbera cartoon style, flat limited color palette,
thick black outlines, retro Saturday morning animation,
warm mid-century illustration, aged paper texture, exaggerated proportions
```
**適用：** 幽默橋段、荒謬對比、輕鬆氛圍

---

### pixar_3d — Pixar 風 3D
圓潤可愛、溫暖燈光、皮克斯短片質感。
```
Pixar animation style 3D render, soft warm lighting,
rounded shapes, expressive characters, cinematic composition,
high quality animation, family-friendly aesthetic
```
**適用：** 角色動作、情感高峰、故事性場景

---

### japanese_anime — 日式動畫風
Studio Ghibli / 新海誠質感。氛圍感、細膩光影、手繪感。
```
Japanese anime style illustration, Studio Ghibli inspired,
soft watercolor textures, cinematic lighting, detailed atmosphere,
nostalgic mood, hand-drawn feel
```
**適用：** 情感鋪陳、懷舊段落、自然風景

---

### comic_page — 單頁漫畫（多格分鏡）
日漫/美漫風格的單張圖，內含 3-6 個 panel，畫面誇張、有動作線、對白框、擬聲詞。
適合長一點的 shot（5-10 秒），讓觀眾在一張圖裡讀完一整段劇情節拍。
```
single comic book page layout, 3-5 panels arranged dynamically,
exaggerated manga/anime style, bold action lines and motion blur,
expressive cartoon characters with big emotive eyes,
speech bubbles with dramatic onomatopoeia, dynamic panel borders,
high contrast inks, vivid color palette,
modern manga/comic aesthetic
```
**適用：** 長段敘事的搞笑/誇張橋段、需要在一張圖內展示多個動作或時間流動的場景

---

### infographic — 資訊圖表風
扁平幾何、數據視覺化、現代設計感。
```
modern flat infographic style, data visualization,
clean geometric shapes, bold accent colors on minimal background,
clear typography, professional design aesthetic
```
**適用：** 數據揭曉、比較對比、統計說明

---

### stock_real — 真實素材（不使用 AI 生圖）
**特殊：** 這類 shot 不產生 Nano Banana prompt，而是從網路找真實圖片並標註來源。

**何時使用此類別（必要！）：**
- fMRI / MRI / CT / X-ray 等醫學影像（不得 AI 偽造）
- 從特定論文或研究引用的數據圖表
- 歷史照片、新聞事件、真實人物
- 考古文物、博物館藏品實拍
- 天文觀測影像（NASA、JWST、哈伯等）
- 顯微鏡/電子顯微鏡實拍
- 任何需要觀眾信任為真實資料的圖像

**何時不需要此類別：**
- 純概念性/抽象圖解（骨導示意、情緒比喻）— 可用 AI
- 通用場景（人拿手機、街景）— 可用 AI
- 風格化插畫（Ghibli、卡通）— 可用 AI

**Shot 輸出格式（非 prompt，是來源清單）：**
```
Topic: [具體搜尋主題 — 例如 "fMRI brain language area activation"]
Suggested sources:
  - [描述] — https://原始論文或新聞 URL
  - [描述] — https://另一個來源
Search keywords: [英文關鍵字，用於 Google Images / Unsplash / 學術資源]
Attribution overlay: "來源: [出版物名稱]" (影片上要標的文字)
Fallback: 若找不到 CC 授權圖，標示為 "使用需授權" 並在 skill 輸出中提醒使用者
```

**適用：** 醫學影像、研究數據、真實事件、科學觀測

---

### kdrama — 韓劇風
高飽和、高製作質感的韓國電視劇美學。柔和霧面打光、城市夜景或精緻室內、情感特寫。常見 teal-orange 調色。
```
Korean drama cinematography style, high production value,
soft diffused lighting with subtle lens flare, muted pastel or teal-orange color grading,
emotional close-up composition, clean modern urban interior or cityscape,
melancholic or romantic atmosphere, Netflix K-drama aesthetic
```
**適用：** 情感衝擊、現代都市場景、角色特寫、濾鏡/手機場景

---

### us_drama — 美劇風（Prestige TV）
HBO/Netflix 劇集風格。高對比、略去飽和、電影感強。適合科技驚悚、社會批判主題（Black Mirror、Succession 氛圍）。
```
prestige American TV drama cinematography, HBO/Netflix production quality,
desaturated high-contrast color grading, cinematic shallow depth of field,
cold or clinical lighting with intentional shadow, dramatic close-ups,
moody atmospheric background blur, Black Mirror or Euphoria visual aesthetic
```
**適用：** Hook 驚嚇、科技批判、數據揭露的戲劇化呈現、社會議題場景

---

### jdrama — 日劇風
溫暖、日常、帶點顆粒感的日本電視劇美學。自然光、家居或咖啡廳場景、安靜的情緒流動。
```
Japanese TV drama cinematography, warm intimate atmosphere,
natural window light with soft shadows, slight film grain texture,
everyday domestic or cafe setting, quiet emotional restraint,
slice-of-life aesthetic, muted warm palette with pops of natural color
```
**適用：** 日常情感場景、角色內心掙扎、安靜的轉折時刻

---

### tw_drama — 台劇風
近年台劇（《你的婚禮》《想見你》《天橋上的魔術師》風格）。黃金時段色調、台灣本地場景感、情感真實貼近生活。
```
Taiwanese TV drama cinematography, warm golden-hour color grading,
relatable everyday Taiwanese urban setting (convenience store, MRT, night market adjacent),
natural emotional expression, intimate handheld-feel camera work,
slightly warm desaturated tones, grounded slice-of-life visual storytelling
```
**適用：** 台灣本地場景、貼近生活的情感橋段、收尾段落

---

## 通用規格（每個 prompt 都會附加）

```
portrait 9:16 aspect ratio, 1080x1920 resolution
```

## 新增風格格式

若要新增風格，依照以下模板：

```markdown
### style_key — 風格中文名
簡短描述（1-2 句）。

(triple backtick)
Full prompt text suffix appended to every shot of this style.
Multi-line OK.
(triple backtick)

**適用：** 什麼類型的 shot
```
