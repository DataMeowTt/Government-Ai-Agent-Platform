import pytest

from gold.tables.crisis_risk import build


def test_build_returns_expected_columns(sample_silver):
    df = build(sample_silver)
    expected = {
        "country_code", "country", "year",
        "SovDebtCrisis", "CurrencyCrisis", "BankingCrisis",
        "crisis_composite", "crisis_any",
        "REER_deviation", "spending_efficiency",
        "govdebt_GDP", "fiscal_balance_GDP", "rGDP_growth_YoY",
        "income_group", "development_group", "completeness_score",
    }
    assert expected.issubset(set(df.columns))


def test_build_crisis_flags_integer_type(sample_silver):
    df = build(sample_silver)
    for col in ["SovDebtCrisis", "CurrencyCrisis", "BankingCrisis", "crisis_any"]:
        non_null = df[col].dropna()
        if not non_null.empty:
            assert non_null.isin([0, 1]).all(), f"{col} contains values outside {{0, 1}}"


def test_build_crisis_composite_bounded(sample_silver):
    df = build(sample_silver)
    non_null = df["crisis_composite"].dropna()
    if not non_null.empty:
        assert non_null.isin([0, 1, 2, 3]).all()


def test_build_completeness_in_range(sample_silver):
    df = build(sample_silver)
    assert df["completeness_score"].between(0.0, 1.0).all()


def test_build_no_duplicate_country_year(sample_silver):
    df = build(sample_silver)
    assert not df.duplicated(subset=["country_code", "year"]).any()
