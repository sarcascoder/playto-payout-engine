import random


def simulate_bank() -> str:
    """Simulate a bank settlement call.

    70% success, 20% fail, 10% hang. The "hang" outcome returns immediately
    but does not transition the payout state — the watchdog detects payouts
    stuck in PROCESSING > 30s and re-enqueues them.
    """
    r = random.random()
    if r < 0.70:
        return "success"
    if r < 0.90:
        return "fail"
    return "hang"
