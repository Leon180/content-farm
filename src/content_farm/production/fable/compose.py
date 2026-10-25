"""ffmpeg building blocks for the fable render: ping-pong loops, picture segments, diagram segments, the final pass.

Every segment is encoded with the same settings (H.264, yuv420p, 30 fps), so the final pass can join them with the
concat filter; the picture-book → diagram change is one ``xfade`` (circleopen) at the reveal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from content_farm.production.fable.cards import PAPER, Geometry

FPS = 30
TRANSITION_SECONDS = 0.7
FFMPEG_TIMEOUT = 900
ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


class ComposeError(RuntimeError):
    pass


def run(args: list[str], cwd: Path) -> None:
    try:
        proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], cwd=cwd,
                              capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ComposeError(f"ffmpeg failed to run: {exc}") from exc
    if proc.returncode != 0:
        raise ComposeError(f"ffmpeg exit {proc.returncode}: {proc.stderr[-800:]}")


def pingpong(clip: Path, out: Path, cwd: Path) -> Path:
    """The parallax clip played forward then backward (a seamless loop); cached by file name, rebuilt when the
    clip is newer (a redrawn picture used to keep showing its old loop: owl-fix 2026-10-24)."""
    if not out.is_file() or out.stat().st_mtime < clip.stat().st_mtime:
        run(["-i", str(clip.resolve()), "-filter_complex", "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[v]",
             "-map", "[v]", *ENCODE, str(out.resolve())], cwd)
    return out


def _fit(size: tuple[int, int]) -> str:
    width, height = size
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def picture_segment(loop: Path, size: tuple[int, int], seconds: float, out: Path, cwd: Path) -> Path:
    run(["-stream_loop", "-1", "-i", str(loop.resolve()), "-t", f"{seconds:.3f}", "-vf", _fit(size), *ENCODE,
         str(out.resolve())], cwd)
    return out


def diagram_filter(geo: Geometry, steps: list[float], fade: tuple[float, float] | None) -> str:
    """Picture window on a paper canvas, then the panel overlays: overlay *k* shows from ``steps[k]``."""
    (wx, wy, ww, wh), (width, height) = geo.window, geo.size
    cx, cy = (width - ww) // 2, (height - wh) // 2
    chain = [f"[0:v]{_fit(geo.size)},crop={ww}:{wh}:{cx}:{cy},pad={width}:{height}:{wx}:{wy}:color={PAPER}[b0]"]
    for k, start in enumerate(steps):
        end = steps[k + 1] if k + 1 < len(steps) else None
        overlay = f"[{k + 1}:v]format=rgba" + (f",fade=t=in:st={fade[0]:.2f}:d={fade[1]:.2f}:alpha=1" if fade and k == 0 else "")
        enable = f"between(t,{start:.3f},{end:.3f})" if end is not None else f"gte(t,{start:.3f})"
        chain.append(f"{overlay}[o{k}];[b{k}][o{k}]overlay=0:0:enable='{enable}'[b{k + 1}]")
    chain.append(f"[b{len(steps)}]format=yuv420p[v]")
    return ";".join(chain)


def diagram_segment(loop: Path, geo: Geometry, overlays: list[tuple[Path, float]], seconds: float, out: Path,
                    cwd: Path, fade: tuple[float, float] | None = None) -> Path:
    args = ["-stream_loop", "-1", "-i", str(loop.resolve())]
    for png, _ in overlays:
        args += ["-loop", "1", "-framerate", str(FPS), "-i", str(png.resolve())]
    script = cwd / f"{out.stem}.filter.txt"
    script.write_text(diagram_filter(geo, [start for _, start in overlays], fade), encoding="utf-8")
    run([*args, "-t", f"{seconds:.3f}", "-filter_complex_script", str(script.resolve()), "-map", "[v]", *ENCODE,
         str(out.resolve())], cwd)
    return out


def join_filter(count: int, reveal: int | None, pre_seconds: float) -> str:
    """concat all segments; with a reveal at segment ``reveal`` the pre / post halves meet in an xfade."""
    def concat(indices: range, label: str) -> str:
        return "".join(f"[{i}:v]" for i in indices) + f"concat=n={len(indices)}:v=1:a=0[{label}]"

    if reveal is None or reveal == 0:
        return concat(range(count), "x") + ";[x]ass=subs.ass[v]"
    offset = pre_seconds - TRANSITION_SECONDS
    return (concat(range(reveal), "pre") + ";" + concat(range(reveal, count), "post")
            + f";[pre][post]xfade=transition=circleopen:duration={TRANSITION_SECONDS}:offset={offset:.3f}[x];[x]ass=subs.ass[v]")


def assemble(segments: list[Path], reveal: int | None, pre_seconds: float, audio: Path, total: float, out: Path,
             cwd: Path) -> Path:
    inputs = [arg for seg in segments for arg in ("-i", str(seg.resolve()))]
    script = cwd / "join.filter.txt"
    graph = join_filter(len(segments), reveal, pre_seconds) + f";[{len(segments)}:a]apad=whole_dur={total:.3f}[a]"
    script.write_text(graph, encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    run([*inputs, "-i", str(audio.resolve()), "-filter_complex_script", str(script.resolve()), "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out.resolve())], cwd)
    return out


def concat_audio(scene_files: list[Path], out: Path, cwd: Path) -> Path:
    inputs = [arg for f in scene_files for arg in ("-i", str(f.resolve()))]
    graph = "".join(f"[{i}:a]" for i in range(len(scene_files))) + f"concat=n={len(scene_files)}:v=0:a=1[a]"
    run([*inputs, "-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_s16le", str(out.resolve())], cwd)
    return out


def ass_text(cues: list, size: tuple[int, int], font: str, font_px: int, margin_v: int, outline: int) -> str:
    """Bottom-centred white subtitles with a dark outline; ``cues`` have ``start``, ``end``, ``text``."""
    from content_farm.production.shorts_render import _ass_time

    width, height = size
    header = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n"
              "WrapStyle: 2\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
              "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
              "Alignment, MarginL, MarginR, MarginV, Encoding\n"
              f"Style: Default,{font},{font_px},&H00FFFFFF,&H00FFFFFF,&H00141414,&H00141414,1,0,0,0,100,100,0,0,1,"
              f"{outline},4,2,60,60,{margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
              "MarginV, Effect, Text\n")
    events = [f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,," +
              c.text.replace("{", "(").replace("}", ")").replace("\n", "\\N") for c in cues]
    return header + "\n".join(events) + "\n"
