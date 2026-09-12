"""Deterministic payment simulation.

No real payment gateway is involved - the outcome must be reproducible on
demand for a demo, not random. It fails when the order amount crosses a
configurable threshold, or when the order explicitly asked to force a
failure (used to reliably trigger the compensation saga in a demo without
needing a naturally large order).
"""


def decide_payment_outcome(
    amount_cents: int, force_failure: bool, threshold_cents: int
) -> tuple[bool, str | None]:
    if force_failure:
        return False, "force_payment_failure was set on the order"
    if amount_cents > threshold_cents:
        return False, f"amount_cents {amount_cents} exceeds threshold {threshold_cents}"
    return True, None
