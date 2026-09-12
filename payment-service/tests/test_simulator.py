from app.simulator import decide_payment_outcome


def test_approves_when_under_threshold_and_not_forced():
    approved, reason = decide_payment_outcome(50_000, force_failure=False, threshold_cents=100_000)
    assert approved is True
    assert reason is None


def test_declines_when_amount_exceeds_threshold():
    approved, reason = decide_payment_outcome(150_000, force_failure=False, threshold_cents=100_000)
    assert approved is False
    assert reason is not None


def test_declines_when_force_failure_set_even_under_threshold():
    approved, reason = decide_payment_outcome(100, force_failure=True, threshold_cents=100_000)
    assert approved is False
    assert "force_payment_failure" in reason


def test_approves_at_exact_threshold():
    approved, _ = decide_payment_outcome(100_000, force_failure=False, threshold_cents=100_000)
    assert approved is True
