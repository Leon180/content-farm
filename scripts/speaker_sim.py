"""Speaker similarity (SpeechBrain ECAPA, cosine) between wav files — "do these two channels sound like different people?"

Run with the spk-embed venv:

    ~/.local/share/spk-embed/.venv/bin/python scripts/speaker_sim.py out.json \
        technews=ref1.wav chipcat=ref2.wav cel=ref3.wav -- gen1.wav gen2.wav

Prints (and writes) the pairwise cosine between the labelled references and, per generated file, its similarity to
every reference. Same-person takes score ~0.8+; the chipcat/cel female voices scored 0.44 (REPORT-channel-voices §4).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 4 or "--" not in argv:
        print(__doc__)
        return 2
    import librosa
    import numpy as np
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    out = Path(argv[0])
    split = argv.index("--")
    labelled = [a.split("=", 1) for a in argv[1:split]]
    encoder = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                             savedir=str(Path.home() / ".local/share/spk-embed/ecapa"),
                                             run_opts={"device": "cpu"})

    def embed(path: str):
        wave, _ = librosa.load(str(Path(path).expanduser()), sr=16000, mono=True)
        with torch.no_grad():
            vector = encoder.encode_batch(torch.tensor(wave)[None]).squeeze().numpy()
        return vector / np.linalg.norm(vector)

    refs = {label: embed(path) for label, path in labelled}
    result = {"refs": {f"{a}|{b}": round(float(refs[a] @ refs[b]), 3) for a in refs for b in refs if a < b},
              "files": {}}
    for path in argv[split + 1:]:
        vector = embed(path)
        result["files"][Path(path).name] = {label: round(float(vector @ ref), 3) for label, ref in refs.items()}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
