"""Bank simulator distribution test."""
from collections import Counter

from payouts.simulator import simulate_bank


def test_simulate_bank_returns_known_outcomes():
    valid = {"success", "fail", "hang"}
    for _ in range(100):
        assert simulate_bank() in valid


def test_simulate_bank_distribution_roughly_matches_spec():
    """Over 10k samples, distribution should be ~70/20/10 (±5%)."""
    counts = Counter(simulate_bank() for _ in range(10_000))
    assert 6500 <= counts["success"] <= 7500, counts
    assert 1500 <= counts["fail"]    <= 2500, counts
    assert  500 <= counts["hang"]    <= 1500, counts
