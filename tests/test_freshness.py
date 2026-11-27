from datetime import date

from aqi.data import validate
from tests.test_data import simulated_daily


def test_fresh_data_passes_freshness_check():
    rep = validate.validate(
        simulated_daily(60),
        max_age_days=3,
        today=date(2024, 3, 2),
    )

    assert rep.ok, rep.errors


def test_stale_data_fails_validation():
    rep = validate.validate(
        simulated_daily(60),
        max_age_days=3,
        today=date(2024, 3, 10),
    )

    assert not rep.ok
    assert "data is stale: newest day 2024-02-29 is 10 days old (max 3)" in rep.errors


def test_freshness_is_disabled_by_default():
    rep = validate.validate(simulated_daily(60))

    assert rep.ok, rep.errors


def test_check_freshness_message_and_boundary():
    assert validate.check_freshness(date(2024, 1, 1), date(2024, 1, 10), 3) == (
        "data is stale: newest day 2024-01-01 is 9 days old (max 3)"
    )
    assert validate.check_freshness(date(2024, 1, 1), date(2024, 1, 3), 3) is None
