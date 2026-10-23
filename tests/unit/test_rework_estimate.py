from content_farm.production import rework_estimate as est

DECK = {"sections": [{"slides": [{"id": f"s{i}"} for i in range(10)]}]}
FIXES = {"steps": {"deck": {"rerender": {"scenes": ["s1", "s2"]}}, "media": {"rerender": {"scenes": ["s2", "s3"]}}}}
LOG = [
    {"step": "media", "exit_code": 0, "seconds": 1000},
    {"step": "media", "exit_code": 0, "seconds": 20},
    {"step": "media", "exit_code": 1, "seconds": 5000},          # a failed run is not a cost sample
    {"step": "mix", "exit_code": 0, "seconds": 60},
    {"step": "mix", "exit_code": 0, "seconds": 30},
    {"step": "deck", "exit_code": 0, "seconds": 1},              # not part of the chain
]


def test_scenes_are_the_union_over_every_step():
    assert est.affected_scenes(FIXES) == {"s1", "s2", "s3"}
    assert est.slide_count(DECK) == 10


def test_scene_scaled_steps_follow_the_share_and_flat_steps_stay_at_the_floor():
    rows = {r.step: r for r in est.estimate(FIXES, DECK, LOG)}
    assert (rows["media"].full_s, rows["media"].floor_s) == (1000, 20)
    assert rows["media"].incremental_s == round(20 + 980 * 0.3, 1)
    assert rows["mix"].incremental_s == 30
    assert "deck" not in rows


def test_chain_order_is_kept():
    log = [{"step": s, "exit_code": 0, "seconds": 10} for s in ("mix", "slides", "media")]
    assert [r.step for r in est.estimate(FIXES, DECK, log)] == ["slides", "media", "mix"]
