"""Which spelling does the TTS read right? Synthesize each candidate line with a channel's reference voice
(VoxCPM2, local) and read it back with the pipeline's ASR (whisper) → ``trial.json`` (one row per line × seed).

Run in the TTS venv through the queue (scripts/heavy), e.g.:

    scripts/heavy --step voice --label "fable:pron-trial" -- \
        /Users/lileon/.local/share/qwen3-tts/.venv/bin/python scripts/pronunciation_trial.py \
        --ref ~/.local/share/content-farm-voices/fable-ref.wav --ref-text-file ref.txt \
        --lines lines.json --out ~/Downloads/pron-trial --seeds 1 2

``lines.json``: ``[{"label": "鷹-英", "tts": "貓頭英先認定了答案", "script": "貓頭鷹先認定了答案"}, …]`` —
``tts`` is what is sent to the voice, ``script`` the display text the read-back is compared with.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HF_HOME = Path("~/.local/share/voxcpm2/hf").expanduser()
MODEL = "mlx-community/VoxCPM2-8bit"
ASR_HUB = Path("~/.local/share/qwen3-tts/hf/hub").expanduser()
ASR_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"


def _asr_dir() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from content_farm.voice.local_worker import snapshot_dir  # noqa: PLC0415

    return str(snapshot_dir(str(ASR_HUB), ASR_MODEL))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--ref-text-file", type=Path, required=True)
    parser.add_argument("--lines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2])
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.stt.utils import load_model as load_asr
    from mlx_audio.tts.utils import load_model
    from opencc import OpenCC

    lines = json.loads(args.lines.read_text(encoding="utf-8"))
    ref_text = args.ref_text_file.read_text(encoding="utf-8").strip()
    args.out.mkdir(parents=True, exist_ok=True)
    tts, asr, s2t = load_model(MODEL), load_asr(_asr_dir()), OpenCC("s2t")
    rows = []
    for line in lines:
        for seed in args.seeds:
            mx.random.seed(seed)
            started = time.time()
            chunks = list(tts.generate(text=line["tts"], ref_audio=str(args.ref.expanduser()),
                                       prompt_audio=str(args.ref.expanduser()), prompt_text=ref_text))
            audio = np.concatenate([np.array(c.audio).reshape(-1) for c in chunks])
            wav = args.out / f"{line['label']}-s{seed}.wav"
            sf.write(wav, audio, chunks[0].sample_rate)
            heard = s2t.convert(asr.generate(str(wav), language="zh").text).strip()
            rows.append({"label": line["label"], "seed": seed, "tts": line["tts"], "script": line.get("script", ""),
                         "heard": heard, "gen_s": round(time.time() - started, 1)})
            print(rows[-1], flush=True)
            mx.clear_cache()
    (args.out / "trial.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
