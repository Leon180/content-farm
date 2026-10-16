"""Run FastWan2.2-TI2V-5B (DMD 3-step) through mlx-video's Wan pipeline.

Upstream mlx-video (87db56a) has no DMD sampler, so this swaps its Euler scheduler for one that follows
the model card: sigmas [1.0, 0.757, 0.522, 0.0], guide 1, renoise. Each step predicts x0 from the
flow velocity and, unless it is the last step, re-noises x0 to the next sigma with fresh noise.

Usage: python fastwan_generate.py <model_dir> <output.mp4> <prompt> [--image start.png]
       [--width 832] [--height 480] [--num-frames 69] [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlx.core as mx
import numpy as np

import mlx_video.models.wan_2.scheduler as wan_scheduler
from mlx_video.models.wan_2.generate import generate_video


def dmd_scheduler_class(sigmas: list[float]):
    class DMDScheduler:
        def __init__(self, num_train_timesteps: int = 1000):
            self.num_train_timesteps = num_train_timesteps

        def set_timesteps(self, num_steps: int, shift: float = 1.0):
            if num_steps != len(sigmas) - 1:
                raise ValueError(f"DMD schedule has {len(sigmas) - 1} steps, got --steps {num_steps}")
            self.sigmas = mx.array(np.array(sigmas, dtype=np.float32))
            self.timesteps = mx.array(np.array(sigmas[:-1], dtype=np.float32) * self.num_train_timesteps)
            self._step_index = 0

        def step(self, model_output: mx.array, timestep, sample: mx.array) -> mx.array:
            sigma, sigma_next = sigmas[self._step_index], sigmas[self._step_index + 1]
            x0 = sample - sigma * model_output
            self._step_index += 1
            if sigma_next == 0.0:
                return x0
            return (1.0 - sigma_next) * x0 + sigma_next * mx.random.normal(sample.shape)

        def reset(self):
            self._step_index = 0

    return DMDScheduler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir")
    parser.add_argument("output")
    parser.add_argument("prompt")
    parser.add_argument("--image")
    parser.add_argument("--width", type=int, default=832)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--num-frames", type=int, default=69)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    config = json.loads((Path(args.model_dir) / "config.json").read_text(encoding="utf-8"))
    dmd = config.get("fastwan_dmd")
    if not dmd or not dmd.get("renoise"):
        raise SystemExit(f"{args.model_dir}/config.json has no fastwan_dmd renoise block")
    wan_scheduler.FlowMatchEulerScheduler = dmd_scheduler_class([float(s) for s in dmd["sigmas"]])
    generate_video(model_dir=args.model_dir, prompt=args.prompt, image=args.image, width=args.width,
                   height=args.height, num_frames=args.num_frames, steps=len(dmd["sigmas"]) - 1,
                   guide_scale=1.0, seed=args.seed, output_path=args.output, scheduler="euler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
