"""Clone a channel's reference voice with VoxCPM2 (local) on a few test lines -> wav files for listening.

Run in the TTS venv through the queue (scripts/heavy), e.g.:

    scripts/heavy --step voice --label "technews:clone-trial" -- \
        /Users/lileon/.local/share/qwen3-tts/.venv/bin/python scripts/voice_clone_trial.py \
        --ref ~/.local/share/content-farm-voices/technews-ref.wav --ref-text-file ref.txt \
        --out ~/Downloads/voice-trial/technews --prefix technews

Same call the pipeline's voxcpm2 provider makes (ref_audio + prompt_audio + prompt_text).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

HF_HOME = Path("~/.local/share/voxcpm2/hf").expanduser()
MODEL = "mlx-community/VoxCPM2-8bit"
TEST_LINES = (
    "高通在法院贏了 Arm，但賠償金只有兩美元，這背後其實是一場授權條款的攻防戰。",
    "研究團隊用一個三億六千萬參數的小模型，模擬出終端機的輸出，準確率比預期高出不少。",
    "先講結論：這項更新不影響一般用戶，但如果你是開發者，今天就該檢查一下設定。",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", type=Path, required=True)
    parser.add_argument("--ref-text-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model

    ref_text = args.ref_text_file.read_text(encoding="utf-8").strip()
    args.out.mkdir(parents=True, exist_ok=True)
    model = load_model(MODEL)
    rows = []
    for number, line in enumerate(TEST_LINES, start=1):
        mx.random.seed(7919 + number)
        started = time.time()
        chunks = list(model.generate(text=line, ref_audio=str(args.ref.expanduser()),
                                     prompt_audio=str(args.ref.expanduser()), prompt_text=ref_text))
        audio = np.concatenate([np.array(c.audio).reshape(-1) for c in chunks])
        rate = chunks[0].sample_rate
        name = f"{args.prefix}-line{number}.wav"
        sf.write(args.out / name, audio, rate)
        rows.append({"file": name, "text": line, "audio_s": round(len(audio) / rate, 2),
                     "chars_per_s": round(len(line) / (len(audio) / rate), 2), "gen_s": round(time.time() - started, 1)})
        print(rows[-1], flush=True)
        mx.clear_cache()
    (args.out / "trial.json").write_text(json.dumps({"model": MODEL, "lines": rows}, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
