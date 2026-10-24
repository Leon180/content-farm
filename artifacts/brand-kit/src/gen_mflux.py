"""Generate brand-kit symbol art / banner backgrounds with local mflux (z-image-turbo, one process per image).

Run through scripts/heavy. Appends one record per image to artifacts/brand-kit/generation_log.jsonl and
skips images that already exist. Usage: gen_mflux.py [--only <id-prefix>]
"""
import argparse
import json
import os
import sys
from pathlib import Path

from content_farm.explainer.illustrate import IllustrationRequest, LocalMflux, MODELS
from content_farm.production.voice_choice import env_file_defaults

ROOT = Path("artifacts/brand-kit")
RAW = ROOT / "raw"
LOG = ROOT / "generation_log.jsonl"
ENV = Path("/Users/lileon/project/content-farm/.env")

STYLE = ("flat vector illustration, bold simple shapes, centered single emblem, strong silhouette, "
         "limited palette, clean edges, illustration not a photograph, no text, no letters, no logos, no people. ")
BG_STYLE = ("wide flat illustration background, soft shapes, large empty calm area in the center, "
            "limited palette, illustration not a photograph, no text, no letters, no logos, no people. ")

IMAGES = [
    # id, size, seed, prompt
    ("yokai_a1", (1024, 1024), 1101, STYLE + "A nine-tailed fox silhouette in vermilion red with nine fanned tails, on a deep warm black background, a faint golden moon behind it."),
    ("yokai_a2", (1024, 1024), 1102, STYLE + "A square red cinnabar seal stamp on aged ink-black paper, carved with an abstract fox head and a single tail curl, gold hairline border."),
    ("yokai_a3", (1024, 1024), 1103, STYLE + "A single glowing paper lantern with a small fox-ear silhouette cut into it, warm gold light, on a dark ink background, ink-wash feeling."),
    ("deepsea_a1", (1024, 1024), 1301, STYLE + "A glowing jellyfish silhouette with long thin tentacles, bioluminescent cyan, on a very dark navy water background, a few small light specks."),
    ("deepsea_a2", (1024, 1024), 1302, STYLE + "An anglerfish silhouette with a single glowing lure, cyan glow, on a very dark navy background, simple shapes."),
    ("deepsea_a3", (1024, 1024), 1303, STYLE + "A submarine porthole circle with a glowing cyan light inside and tiny drifting particles, dark navy background, simple concentric shapes."),
    ("fable_a1", (1024, 1024), 1401, STYLE + "An open picture-book with a small glowing oil lamp resting on it, warm ochre and terracotta, soft cream background, storybook gouache feeling."),
    ("fable_a2", (1024, 1024), 1402, STYLE + "A small original fox sitting under a lantern, side view, simple shapes, ochre terracotta and sage green, cream background, storybook gouache feeling, animal only."),
    ("fable_a3", (1024, 1024), 1403, STYLE + "A crescent moon cradling an open book with a tiny star above it, sage green and ochre on cream, soft storybook gouache feeling."),
    # banner backgrounds
    ("yokai_b1", (1664, 928), 2101, BG_STYLE + "Dark ink-black night, old Chinese-style mountains in the distance, nine thin fox tails of red mist curling at the left edge, a golden moon on the right."),
    ("yokai_b2", (1664, 928), 2102, BG_STYLE + "Aged ink-black paper texture with faint red seal-stamp marks and thin gold lines scattered at the edges, a tiny fox silhouette in the far corner."),
    ("deepsea_b1", (1664, 928), 2301, BG_STYLE + "Very dark navy deep ocean, soft cyan bioluminescent jellyfish silhouettes drifting at the far left and right edges, light specks."),
    ("deepsea_b2", (1664, 928), 2302, BG_STYLE + "Very dark navy underwater, faint cyan light rays from above, a small anglerfish lure glow at the right edge, drifting particles."),
    ("fable_b1", (1664, 928), 2401, BG_STYLE + "Warm cream storybook meadow in soft gouache, ochre hills and sage green trees at the edges, a small lantern glow on the left, empty center."),
    ("fable_b2", (1664, 928), 2402, BG_STYLE + "Cream paper with a terracotta and sage green gouache border of leaves and stars, a small open book at the lower left, empty center."),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    env = {**env_file_defaults(ENV), **os.environ}
    provider = LocalMflux.from_env("z-image-turbo", env)
    spec = MODELS["z-image-turbo"]
    RAW.mkdir(parents=True, exist_ok=True)
    for image_id, (width, height), seed, prompt in IMAGES:
        out = RAW / f"{image_id}.png"
        if not image_id.startswith(args.only) or out.is_file():
            continue
        record = provider.generate(IllustrationRequest(image_id, prompt, seed, width, height), out)
        entry = {"id": image_id, "model": spec.name, "license": spec.license, "seed": seed,
                 "size": [width, height], "prompt": prompt, "seconds": record.get("seconds"), "file": str(out)}
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"{image_id}: {record.get('seconds')}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
