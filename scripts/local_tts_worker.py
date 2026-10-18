"""Local TTS / ASR worker — runs inside the TTS venv (mlx_audio), NOT the repo's .venv.

Started by ``content_farm.voice.local_worker`` as::

    <venv>/bin/python -I scripts/local_tts_worker.py

It speaks JSON lines: one request per stdin line, one reply per stdout line.
Anything the libraries print goes to stderr, so stdout stays a clean channel.
Models load once and stay loaded until ``quit`` (or stdin closes), so a whole
video is voiced with a single model load. Models are local snapshot
directories; the parent sets ``HF_HUB_OFFLINE=1`` so nothing is downloaded.

Requests::

    {"op": "load_tts", "kind": "voxcpm2" | "qwen3_tts", "model_dir": "..."}
    {"op": "synth", "text": "...", "ref_audio": "...", "ref_text": "...", "seed": 1, "out": "x.wav",
     "prompt_audio": "...", "prompt_text": "..."}   # prompt_*: optional (voxcpm2), continuation context
    {"op": "load_asr", "model_dir": "..."}
    {"op": "asr", "file": "x.wav"}          -> {"text": "<Traditional Chinese>"}
    {"op": "quit"}

Every reply has ``ok``; failures carry ``error`` and the worker keeps serving.
Self-contained on purpose: it must not import content_farm (different venv).
"""

import json
import os
import sys
import time
import traceback

_PROTO = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
os.dup2(2, 1)  # library prints (C or Python) land on stderr
sys.stdout = sys.stderr

_STATE: dict = {}


def _reply(payload: dict) -> None:
    _PROTO.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _PROTO.flush()


def _load_tts(req: dict) -> dict:
    from mlx_audio.tts.utils import load_model

    kind = req["kind"]
    if kind not in ("voxcpm2", "qwen3_tts"):
        raise ValueError(f"unknown tts kind {kind!r}")
    if _STATE.get("tts_dir") == req["model_dir"]:
        return {"load_s": 0.0}
    start = time.time()
    _STATE.update(tts=load_model(req["model_dir"]), tts_kind=kind, tts_dir=req["model_dir"])
    return {"load_s": round(time.time() - start, 1)}


def _synth(req: dict) -> dict:
    import mlx.core as mx
    import numpy as np
    import soundfile as sf

    model = _STATE.get("tts")
    if model is None:
        raise RuntimeError("synth before load_tts")
    mx.random.seed(int(req.get("seed", 0)))
    mx.reset_peak_memory()
    start = time.time()
    if _STATE["tts_kind"] == "qwen3_tts":
        from mlx_audio.utils import load_audio

        ref = load_audio(req["ref_audio"], sample_rate=model.sample_rate)
        results = model.generate(text=req["text"], ref_audio=ref, ref_text=req["ref_text"], lang_code="chinese")
    else:
        # prompt_audio / prompt_text: continue from this audio (default: the voice reference itself);
        # sentence-window re-voicing passes the previous sentence of the old take here.
        results = model.generate(text=req["text"], ref_audio=req["ref_audio"],
                                 prompt_audio=req.get("prompt_audio") or req["ref_audio"],
                                 prompt_text=req.get("prompt_text") or req["ref_text"])
    chunks = list(results)
    if not chunks:
        raise RuntimeError("model returned no audio")
    audio = np.concatenate([np.array(chunk.audio).reshape(-1) for chunk in chunks])
    rate = chunks[0].sample_rate
    sf.write(req["out"], audio, rate)
    mx.clear_cache()
    return {"gen_s": round(time.time() - start, 1), "audio_s": round(len(audio) / rate, 2), "sr": rate,
            "peak_mlx_gb": round(mx.get_peak_memory() / 1e9, 2)}


def _load_asr(req: dict) -> dict:
    from mlx_audio.stt.utils import load_model
    from opencc import OpenCC

    if _STATE.get("asr_dir") == req["model_dir"]:
        return {"load_s": 0.0}
    start = time.time()
    _STATE.update(asr=load_model(req["model_dir"]), asr_dir=req["model_dir"], s2t=OpenCC("s2t"))
    return {"load_s": round(time.time() - start, 1)}


def _asr(req: dict) -> dict:
    model = _STATE.get("asr")
    if model is None:
        raise RuntimeError("asr before load_asr")
    text = model.generate(req["file"], language="zh").text
    return {"text": _STATE["s2t"].convert(text).strip()}


_OPS = {"load_tts": _load_tts, "synth": _synth, "load_asr": _load_asr, "asr": _asr}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            if req.get("op") == "quit":
                _reply({"ok": True})
                return
            handler = _OPS.get(req.get("op"))
            if handler is None:
                raise ValueError(f"unknown op {req.get('op')!r}")
            _reply({"ok": True, **handler(req)})
        except Exception as exc:  # reported to the parent, which decides; the worker keeps serving
            traceback.print_exc(file=sys.stderr)
            _reply({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
