"""Channel Wan policy (Leon 2026-10-24): a negative prompt against warped faces, and environment-only prompts."""

from __future__ import annotations

from content_farm.explainer import wan
from content_farm.production.channels import WanPolicy, load_channel
from tests.unit.test_explainer_motion import _paths


def test_policy_sets_the_negative_prompt_and_drops_the_still_prompt(tmp_path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    policy = WanPolicy(negative_prompt="face distortion, morphing", motion_only=True)
    request = wan.request_for("s1", image, {"prompt": "a giant squid with a huge eye", "seed": 7},
                              "slow push-in through marine snow", "", policy)
    assert request.prompt == "slow push-in through marine snow"
    argv = wan.argv(_paths(tmp_path), request, tmp_path / "o.mp4")
    assert argv[argv.index("--negative-prompt") + 1] == "face distortion, morphing"


def test_no_policy_uses_the_default_negative_prompt_and_a_different_cache_key(tmp_path) -> None:
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    plain = wan.request_for("s1", image, {"prompt": "a fox", "seed": 7}, "tails sway")
    argv = wan.argv(_paths(tmp_path), plain, tmp_path / "o.mp4")
    assert argv[argv.index("--negative-prompt") + 1] == wan.NEGATIVE_PROMPT   # revisual's default; a policy overrides it
    with_policy = wan.request_for("s1", image, {"prompt": "a fox", "seed": 7}, "tails sway", "",
                                  WanPolicy(negative_prompt="face distortion, morphing"))
    assert wan.key_for(plain, "h") != wan.key_for(with_policy, "h")


def test_deepsea_channel_uses_the_policy() -> None:
    policy = load_channel("deepsea").wan
    assert policy.motion_only and policy.negative_prompt == "face distortion, morphing"
    assert load_channel("cel").wan == WanPolicy()
