"""cel-run1: an arbiter ruling that copies the whole dispute line still answers its dispute."""

from content_farm.review.arbitration import upheld


def test_ruling_with_claim_text_after_key_counts_as_answered():
    disputes = [{"item": "fact_checker-1#24"}, {"item": "fact_checker-2#3"}]
    rulings = {"rulings": [
        {"item": "fact_checker-1#24：指針的例子裡有…", "status": "ok", "note": "x"},
        {"item": "item fact_checker-2#3：另一條", "status": "wrong", "note": "y"},
    ]}
    assert upheld(rulings, disputes) == (["fact_checker-2#3"], [])


def test_missing_ruling_is_unanswered():
    assert upheld({"rulings": []}, [{"item": "fact_checker-1#1"}]) == ([], ["fact_checker-1#1"])
