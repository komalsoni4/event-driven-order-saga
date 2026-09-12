from saga_shared.rabbitmq import compute_retry_decision


def test_retries_with_exponential_backoff_before_max():
    assert compute_retry_decision(0, max_retries=3, base_delay_ms=5000) == ("retry", 5000)
    assert compute_retry_decision(1, max_retries=3, base_delay_ms=5000) == ("retry", 10000)
    assert compute_retry_decision(2, max_retries=3, base_delay_ms=5000) == ("retry", 20000)


def test_parks_once_max_retries_reached():
    assert compute_retry_decision(3, max_retries=3, base_delay_ms=5000) == ("park", None)
    assert compute_retry_decision(4, max_retries=3, base_delay_ms=5000) == ("park", None)


def test_zero_max_retries_parks_immediately():
    assert compute_retry_decision(0, max_retries=0, base_delay_ms=5000) == ("park", None)
