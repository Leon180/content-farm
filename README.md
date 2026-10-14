# Content Farm — YouTube Content Factory

zh-TW YouTube 內容工廠：自動從主題產出完整影片並上架。支援兩條 workflow：**短影片**（直式 Shorts）與**長影片**（橫式 10-min）。

**維護者請讀：[docs/WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md)** — 完整的專案教學、skill 串接、擴充方式。

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Set API key
cp .env.example .env
# Edit .env with your CF_ANTHROPIC_API_KEY

# 短影片 script
python scripts/generate_script.py --topic "飛機窗戶為什麼是圓的" --length short

# 長影片 chapter outline（只產章節、不展開，快速驗證 prompt）
python scripts/try_chapter_outline.py --topic "台灣為什麼年年淹水" --genre knowledge

# 長影片完整 script
python scripts/generate_script.py --topic "..." --length long --genre knowledge --orientation landscape

# Tests
pytest tests/unit/ -v
```

## Architecture

```
Topic → Script Generation → [Voice → Visual → Assembly → Upload]
         (Phase 1 now)            (future phases)
```

### Two-Phase Script Generation
- **Phase 1** (Haiku): Generate scene outline (~$0.001)
- **Phase 2** (Sonnet): Expand each scene concurrently (~$0.01/scene)
- Cost: ~$0.05-0.10/video

## Project Structure

```
src/content_farm/
├── config.py          # Settings (env vars, CF_ prefix)
├── types.py           # Tone, VideoLength, PipelineArtifact
├── pipeline/base.py   # PipelineStage protocol
├── llm/
│   ├── client.py      # Async Anthropic SDK wrapper
│   └── cache.py       # File/Redis cache
└── script_gen/
    ├── schemas.py     # ScriptRequest, Scene, Script
    ├── prompts.py     # Prompt templates
    └── generator.py   # Two-phase ScriptGenerator
```

## Configuration

All settings via `CF_` prefixed env vars. See `.env.example`.
