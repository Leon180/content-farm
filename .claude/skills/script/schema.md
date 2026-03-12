# Script JSON Schema

## script.json

```json
{
  "stage": "script_generation",
  "video_title": "你的手機裡有個AI助手，它現在正在偷聽你？",
  "description": "描述文字...",
  "scenes": [
    {
      "scene_number": 1,
      "title": "場景標題",
      "narration": "旁白文字（口語化繁體中文）",
      "visual_hint": {
        "description": "畫面描述（中文）",
        "style": "stock_footage",
        "keywords": ["keyword1", "keyword2"],
        "source_preference": "auto"
      },
      "duration_seconds": 15,
      "transition": "cut"
    }
  ],
  "target_length": "short",
  "tone": "educational",
  "language": "zh-TW",
  "total_duration_seconds": 45,
  "tags": ["tag1", "tag2"],
  "sources": [
    "Source Title — https://example.com/article"
  ],
  "ai_disclosure": true
}
```

## Field Descriptions

### Top-Level

| Field | Type | Description |
|-------|------|-------------|
| `stage` | string | Always `"script_generation"` |
| `video_title` | string | zh-TW video title, catchy and concise |
| `description` | string | zh-TW video description for YouTube |
| `scenes` | array | Ordered scene objects |
| `target_length` | string | `"short"` (30-90s), `"medium"` (3-10min), `"long"` (10+min) |
| `tone` | string | `"educational"`, `"entertaining"`, `"dramatic"` |
| `language` | string | `"zh-TW"` |
| `total_duration_seconds` | int | Sum of all scene durations |
| `tags` | array[string] | zh-TW tags for discoverability |
| `sources` | array[string] | Real source citations, format: `"Title — URL"` |
| `ai_disclosure` | bool | Always `true` |

### Scene Object

| Field | Type | Description |
|-------|------|-------------|
| `scene_number` | int | 1-indexed |
| `title` | string | zh-TW scene title |
| `narration` | string | Spoken narration text (50-80 chars/scene for short-form) |
| `visual_hint` | object | What should appear on screen |
| `duration_seconds` | int | Estimated scene duration in seconds |
| `transition` | string | `"cut"`, `"fade"`, `"dissolve"` |

### VisualHint Object

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Visual description (zh-TW) |
| `style` | string | `"stock_footage"`, `"animation"`, `"text_overlay"` |
| `keywords` | array[string] | **English** keywords for stock footage search |
| `source_preference` | string | `"auto"`, `"stock"`, `"ai"` |

## storyboard.txt

Human-readable format:

```
# [Video Title]
[Description]

## 場景 1: [Title]
時長: 15s (00:00-00:15) | 轉場: cut

### 旁白
[Narration text]

### 畫面提示
描述: [Visual description]
關鍵字: keyword1, keyword2
風格: stock_footage | 來源: auto

## 場景 2: ...
```
