"""Fable banner v2 side panels: the fable channel's own model and style prefix (channels/fable.yaml), portrait panels
with the subject hugging the outer edge and plain cream paper toward the middle. Run through scripts/heavy."""
import json
import os
import sys
from pathlib import Path

from content_farm.explainer.illustrate import MODELS, IllustrationRequest, LocalMflux
from content_farm.production.channels import load_channel
from content_farm.production.voice_choice import env_file_defaults

RAW = Path("artifacts/brand-kit/raw")
LOG = Path("artifacts/brand-kit/generation_log.jsonl")
W, H = 768, 1152

LEFT = "composition: all the artwork hugs the LEFT edge of the picture, the right half is plain empty cream paper. "
RIGHT = "composition: all the artwork hugs the RIGHT edge of the picture, the left half is plain empty cream paper. "
PANELS = [
    ("fbv2_1L", 7101, LEFT + "a big autumn tree trunk and orange leafy branches coming in from the left edge, three small songbirds perched on the branches, a few falling leaves"),
    ("fbv2_1R", 7102, RIGHT + "an autumn oak branch with orange leaves and clusters of red berries coming in from the right edge, one small songbird perched on it, a few falling leaves"),
    ("fbv2_2L", 7201, LEFT + "a small original fox sitting at the foot of a big tree at the left edge, autumn leaves on the ground, a lantern beside it, warm autumn colours"),
    ("fbv2_2R", 7202, RIGHT + "a bush with red berries and sage green leaves at the right edge, two small songbirds on a branch, a few falling leaves"),
    ("fbv2_3L", 7301, LEFT + "a hanging branch of red berries and ochre leaves from the top-left corner, a small songbird, soft mushrooms and grass at the bottom-left"),
    ("fbv2_3R", 7302, RIGHT + "a tall autumn tree with a hollow in the trunk at the right edge, a tiny fox peeking out, orange leaves drifting down, small songbird on a branch"),
]


def main() -> int:
    channel = load_channel("fable")
    prefix = channel.ai_illustration.style_prefix.strip()
    env = {**env_file_defaults(Path("/Users/lileon/project/content-farm/.env")), **os.environ}
    provider = LocalMflux.from_env("z-image-turbo", env)
    spec = MODELS["z-image-turbo"]
    for panel_id, seed, scene in PANELS:
        out = RAW / f"{panel_id}.png"
        if out.is_file():
            continue
        prompt = f"{prefix} {scene}"
        record = provider.generate(IllustrationRequest(panel_id, prompt, seed, W, H), out)
        entry = {"id": panel_id, "model": spec.name, "license": spec.license, "seed": seed, "size": [W, H],
                 "prompt": prompt, "seconds": record.get("seconds"), "file": str(out)}
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"{panel_id}: {record.get('seconds')}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
