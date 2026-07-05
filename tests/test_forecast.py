from app.services.forecast import AccountTypeSipInput, compute_fire_plan, compute_projection


def test_projection_pure_compound_growth_matches_standard_cagr_formula():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=0, rate_percent=12.0)]
    result = compute_projection(inputs, {"test": 100000.0}, 0, 0, 0, years=5)
    assert abs(result["years"][4]["nominal_value"] - (100000.0 * (1.12**5))) < 1.0


def test_projection_additional_investment_only():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=0, rate_percent=10.0)]
    result = compute_projection(inputs, {"test": 0.0}, 0, 10000, 0, years=1)
    assert abs(result["years"][0]["nominal_value"] - 11000.0) < 1.0


def test_projection_step_up_with_zero_rate():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=1000, rate_percent=0.0)]
    result = compute_projection(inputs, {"test": 0.0}, 10.0, 0, 0, years=2)
    assert abs(result["years"][0]["nominal_value"] - 12000.0) < 1.0
    assert abs(result["years"][1]["nominal_value"] - 25200.0) < 1.0


def test_projection_additional_investment_allocated_by_sip_weight():
    inputs = [
        AccountTypeSipInput(account_type="A", monthly_sip=100, rate_percent=0.0),
        AccountTypeSipInput(account_type="B", monthly_sip=300, rate_percent=0.0),
    ]
    result = compute_projection(inputs, {"A": 0.0, "B": 0.0}, 0, 400, 0, years=1)
    assert abs(result["per_type_year_end"]["A"][0]["value"] - 1300.0) < 1.0
    assert abs(result["per_type_year_end"]["B"][0]["value"] - 3900.0) < 1.0


def test_projection_equal_split_when_no_weights_available():
    inputs = [
        AccountTypeSipInput(account_type="A", monthly_sip=0, rate_percent=0.0),
        AccountTypeSipInput(account_type="B", monthly_sip=0, rate_percent=0.0),
    ]
    result = compute_projection(inputs, {"A": 0.0, "B": 0.0}, 0, 1000, 0, years=1)
    assert abs(result["per_type_year_end"]["A"][0]["value"] - 500.0) < 1.0
    assert abs(result["per_type_year_end"]["B"][0]["value"] - 500.0) < 1.0


def test_projection_real_value_calculation():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=0, rate_percent=0.0)]
    result = compute_projection(inputs, {"test": 100000.0}, 0, 0, 6.0, years=3)
    assert abs(result["years"][2]["real_value"] - (100000.0 / (1.06**3))) < 1.0


def test_projection_returns_correct_number_of_years():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=1000, rate_percent=8.0)]
    result = compute_projection(inputs, {"test": 50000.0}, 5, 10000, 6, years=10)
    assert len(result["years"]) == 10
    assert result["years"][0]["year"] == 1
    assert result["years"][9]["year"] == 10


def test_projection_values_monotonically_increase_with_positive_inputs():
    inputs = [AccountTypeSipInput(account_type="test", monthly_sip=5000, rate_percent=10.0)]
    result = compute_projection(inputs, {"test": 100000.0}, 5, 20000, 6, years=10)
    values = [year["nominal_value"] for year in result["years"]]
    assert all(values[index] < values[index + 1] for index in range(len(values) - 1))


def test_fire_plan_starting_swp_inflation_adjustment():
    result = compute_fire_plan(10_000_000, 10, 50000, 6.0, 8.0)
    assert abs(result["starting_monthly_swp"] - (50000 * (1.06**10))) < 1.0


def test_fire_plan_growth_applied_before_withdrawal():
    starting_corpus = 10_000_000.0
    monthly_expense_today = 50_000.0
    inflation = 6.0
    growth_pct = 12.0
    monthly_rate = (1 + growth_pct / 100) ** (1 / 12) - 1

    ref_corpus = starting_corpus
    ref_swp = monthly_expense_today
    for _ in range(12):
        ref_corpus *= 1 + monthly_rate
        ref_corpus -= ref_swp

    result = compute_fire_plan(
        starting_corpus=starting_corpus,
        retirement_year=0,
        monthly_expense_today=monthly_expense_today,
        inflation_rate_percent=inflation,
        post_retirement_growth_percent=growth_pct,
        max_years=1,
    )
    actual_year1_value = result["rows"][0]["total_value"]
    assert abs(actual_year1_value - ref_corpus) < 1.0


def test_fire_plan_matches_real_reference_calculator_data():
    starting_corpus = 47784894.00
    monthly_swp = 179084.00
    growth_pct = 10.0
    monthly_rate = (1 + growth_pct / 100) ** (1 / 12) - 1

    corpus = starting_corpus
    corpus *= 1 + monthly_rate
    corpus -= monthly_swp

    expected_closing_balance = 47986853.46
    assert abs(corpus - expected_closing_balance) < 100.0


def test_fire_plan_zero_growth_zero_inflation_linear_depletion():
    result = compute_fire_plan(1_200_000, 0, 10000, 0.0, 0.0, max_years=5)
    assert result["starting_monthly_swp"] == 10000.0
    assert abs(result["rows"][0]["total_value"] - 1_080_000.0) < 1.0
    assert abs(result["rows"][4]["total_value"] - 600_000.0) < 1.0


def test_fire_plan_detects_depletion():
    result = compute_fire_plan(100_000, 0, 20000, 0.0, 0.0, max_years=10)
    assert result["sustainable"] is False
    assert result["depleted_at_year"] is not None
    assert result["depleted_at_year"] <= 1


def test_fire_plan_sustainable_with_high_growth_low_withdrawal():
    """A large corpus with low withdrawal and decent growth should be sustainable for 100 years."""
    result = compute_fire_plan(
        starting_corpus=50_000_000,
        retirement_year=10,
        monthly_expense_today=30_000,
        inflation_rate_percent=6.0,
        post_retirement_growth_percent=10.0,
        max_years=100,   # was 50
    )
    assert result["sustainable"] is True
    assert result["depleted_at_year"] is None
    assert len(result["rows"]) == 100   # was 50


def test_fire_plan_monthly_swp_increases_with_inflation_each_year():
    result = compute_fire_plan(50_000_000, 0, 50000, 6.0, 10.0, max_years=5)
    print(result)
    assert abs(result["rows"][1]["monthly_swp"] - (result["rows"][0]["monthly_swp"] * 1.06)) < 1.0

def test_fire_plan_finds_depletion_beyond_50_years():
    """
    A scenario tuned so the corpus depletes somewhere between year 50 and
    year 100 — this must be correctly detected, not masked as "sustainable"
    by an artificial 50-year cutoff.
    """
    result = compute_fire_plan(
        starting_corpus=30_000_000,
        retirement_year=5,
        monthly_expense_today=40_000,
        inflation_rate_percent=6.0,
        post_retirement_growth_percent=7.0,
        max_years=100,
    )
    assert result["sustainable"] is False
    assert result["depleted_at_year"] is not None
    assert result["depleted_at_year"] > 50, \
        "This test is specifically checking that depletion beyond year 50 is still detected"

