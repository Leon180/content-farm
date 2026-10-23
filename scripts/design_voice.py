"""Design a reference voice with Qwen3-TTS VoiceDesign (local, Apache-2.0), several seeds -> several takes.

Run in the TTS venv, through the machine-wide queue:

    scripts/heavy --step voice --label "technews:voice-design" -- \
        /Users/lileon/.local/share/qwen3-tts/.venv/bin/python scripts/design_voice.py \
        --out <dir> --seeds 3000 3001 3002 --instruct-file instruct.txt --text-file ref.txt

Writes ``take<seed>.wav`` + ``takes.json`` (instruct, text, seconds, median F0) into ``--out``. Picking the take
(gender, accent, similarity to the other channels) is a separate, human-checked step (REPORT-technews §聲音).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

HF_HOME = Path("~/.local/share/qwen3-tts/hf").expanduser()
MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"


def median_f0(audio, sample_rate: int) -> float | None:
    import librosa
    import numpy as np

    f0, voiced, _ = librosa.pyin(audio.astype("float32"), fmin=70, fmax=400, sr=sample_rate)
    values = f0[voiced & ~np.isnan(f0)] if voiced is not None else []
    return round(float(np.median(values)), 1) if len(values) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--instruct-file", type=Path, required=True)
    parser.add_argument("--text-file", type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model

    instruct = args.instruct_file.read_text(encoding="utf-8").strip()
    text = args.text_file.read_text(encoding="utf-8").strip()
    args.out.mkdir(parents=True, exist_ok=True)
    model = load_model(MODEL)
    rows = []
    for seed in args.seeds:
        mx.random.seed(seed)
        started = time.time()
        chunks = list(model.generate_voice_design(text=text, instruct=instruct, language="chinese"))
        audio = np.concatenate([np.array(c.audio).reshape(-1) for c in chunks])
        rate = chunks[0].sample_rate
        path = args.out / f"take{seed}.wav"
        sf.write(path, audio, rate)
        rows.append({"seed": seed, "file": path.name, "audio_s": round(len(audio) / rate, 1),
                     "gen_s": round(time.time() - started, 1), "median_f0_hz": median_f0(audio, rate)})
        print(rows[-1], flush=True)
        mx.clear_cache()
    (args.out / "takes.json").write_text(json.dumps({"model": MODEL, "instruct": instruct, "text": text, "takes": rows},
                                                    ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
