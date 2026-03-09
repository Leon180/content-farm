# Content Farm - YouTube Content Factory

Automated YouTube video script generation pipeline powered by Claude API.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Set API key
cp .env.example .env
# Edit .env with your CF_ANTHROPIC_API_KEY

# Generate a script
python scripts/generate_script.py --topic "How Bitcoin Works" --tone educational --length medium

# Run tests
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
