"""Yokai launch art: banner side panels, ink avatar, kyubi thumbnail key art.

Same model (Z-Image-Turbo) and the channel's own style_prefix as the kyubi video (channels/yokai.yaml).
Run through scripts/heavy:  PYTHONPATH=src python artifacts/yokai-launch/src/gen_yokai_art.py [group ...]
groups: banner, avatar, thumb (default: all). Existing outputs are skipped.
"""
import json
import os
import sys
from pathlib import Path

from content_farm.explainer.illustrate import MODELS, IllustrationRequest, LocalMflux
from content_farm.production.channels import load_channel
from content_farm.production.voice_choice import env_file_defaults

OUT = Path("artifacts/yokai-launch")
RAW = OUT / "raw"
LOG = OUT / "generation_log.jsonl"

_UNUSED_LEFT = "composition: all the artwork hugs the LEFT edge of the picture, the right half is plain empty aged rice paper. "
_UNUSED_RIGHT = "composition: all the artwork hugs the RIGHT edge of the picture, the left half is plain empty aged rice paper. "
NINE = "exactly nine separate bushy tails clearly fanned out behind it, each tail distinct and countable"

# (id, seed, width, height, scene)
# Banner: no text anywhere (Leon 2026-10-25), so the subject itself must sit in the central safe band
# (60% wide x 30% tall of the frame); mountains / mist / moon fill the sides.
BAND = ("wide panoramic composition, the main subject sits small and compact in the exact centre of the picture, "
        "occupying only the middle 55% of the width and the middle 30% of the height, "
        "the sides and the top and bottom are only soft mist, distant mountains and empty paper. ")
BANNER = [
    ("ykc1", 8601, 1664, 928, BAND + f"a nine-tailed fox in profile standing on a rocky ledge in front of a large pale full moon, {NINE}, layered misty ink-wash mountains far behind, mostly grey ink with a touch of orange wash"),
    ("ykc2", 8602, 1664, 928, BAND + "an old handscroll half unrolled on a stone table in the centre with pale ink mountains painted on it, a faint nine-tailed fox shadow rising like smoke above the scroll, ink brush beside it, misty mountains far behind"),
    ("ykc3", 8603, 1664, 928, BAND + f"a red fox with nine tails sitting on a boulder in tall pampas grass under a thin crescent moon, {NINE}, misty night, layered ink-wash mountains far behind"),
]
BANNER2B = [  # Leon picked option 2 (scroll + fox) on 2026-10-25: same composition, a clearly nine-tailed, larger fox
    (f"ykc2b{n}", seed, 1664, 928, BAND + "an old handscroll half unrolled on a stone table in the centre with pale ink mountains painted on it, "
     "a large fox sitting upright on the scroll facing left, its nine long bushy tails fanned wide behind it in a big half-circle like a peacock, "
     "every tail separate and clearly countable, the fox and its tails fill the whole central band, ink brush beside the scroll, misty mountains far behind")
    for n, seed in enumerate((8611, 8612, 8613, 8614), start=1)
]
AVATAR = [
    ("ykav1", 8401, 1024, 1024, "centered square composition with generous empty paper margin, a bold black ink silhouette of a nine-tailed fox sitting and facing forward, nine tails fanned out symmetrically behind it like a lotus, one large pale full moon behind the fox, minimal, plain rice paper background"),
    ("ykav2", 8402, 1024, 1024, "centered square composition with generous empty paper margin, a bold black ink silhouette of a nine-tailed fox sitting and facing forward, nine tails fanned out symmetrically behind it like a lotus, one large pale full moon behind the fox, minimal, plain rice paper background"),
]
THUMB = [
    ("ykth_a", 8501, 1280, 720, "extreme close-up of a fox face looking straight at the viewer with amber eyes, the face is huge and fills the right two thirds of the frame, nine tails fanned out behind the head, the left third is calm empty paper, single subject, high contrast ink"),
    ("ykth_b", 8502, 1280, 720, f"a huge nine-tailed fox in profile filling the right two thirds of the frame, {NINE}, the left third is calm empty paper, single subject, bold ink strokes with orange wash"),
    ("ykth_c", 8503, 1280, 720, "a giant grey boulder split in two by a dark crack standing in a barren volcanic field with pale steam, the boulder fills the right two thirds of the frame, the faint shadow of a many-tailed fox in the mist behind it, the left third is calm empty paper, single subject, bold ink strokes"),
]
GROUPS = {"banner2b": BANNER2B, "banner": BANNER, "avatar": AVATAR, "thumb": THUMB}


def main(argv: list[str]) -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    wanted = argv or ["banner2b", "banner", "avatar", "thumb"]
    channel = load_channel("yokai")
    prefix = channel.ai_illustration.style_prefix.strip()
    env = {**env_file_defaults(Path("/Users/lileon/project/content-farm/.env")), **os.environ}
    provider = LocalMflux.from_env("z-image-turbo", env)
    spec = MODELS["z-image-turbo"]
    for group in wanted:
        for item_id, seed, width, height, scene in GROUPS[group]:
            out = RAW / f"{item_id}.png"
            if out.is_file():
                continue
            prompt = f"{prefix} {scene}"
            record = provider.generate(IllustrationRequest(item_id, prompt, seed, width, height), out)
            entry = {"id": item_id, "model": spec.name, "license": spec.license, "seed": seed, "size": [width, height],
                     "prompt": prompt, "seconds": record.get("seconds"), "file": str(out)}
            with LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            print(f"{item_id}: {record.get('seconds')}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
