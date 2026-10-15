"""晶片貓 — a VTuber-style overlay for explainer videos.

Layers (each replaceable on its own):

* ``params``  — Live2D-style parameter names and the pose table
* ``idle`` / ``physics`` / ``lipsync`` / ``cues`` → ``motion`` — the
  deterministic parameter timeline (one dict per video frame)
* ``assets/rig.html`` — the layered SVG puppet that draws a parameter dict
* ``render`` — Playwright capture → alpha video; ``overlay`` — ffmpeg compose
"""
