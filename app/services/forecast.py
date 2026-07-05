from dataclasses import dataclass


@dataclass
class AccountTypeSipInput:
    account_type: str
    monthly_sip: float
    rate_percent: float


def compute_projection(
    account_type_inputs: list[AccountTypeSipInput],
    current_values: dict,
    step_up_percent: float,
    additional_investment: float,
    inflation_rate_percent: float,
    years: int = 10,
) -> dict:
    months = years * 12

    total_sip = sum(a.monthly_sip for a in account_type_inputs)
    if total_sip > 0:
        weights = {a.account_type: a.monthly_sip / total_sip for a in account_type_inputs}
    else:
        total_current = sum(current_values.get(a.account_type, 0.0) for a in account_type_inputs)
        if total_current > 0:
            weights = {
                a.account_type: current_values.get(a.account_type, 0.0) / total_current
                for a in account_type_inputs
            }
        else:
            n = len(account_type_inputs)
            weights = {a.account_type: (1.0 / n if n else 0.0) for a in account_type_inputs}

    state = {}
    for a in account_type_inputs:
        state[a.account_type] = {
            "value": current_values.get(a.account_type, 0.0),
            "monthly_rate": (1 + a.rate_percent / 100) ** (1 / 12) - 1,
            "current_monthly_sip": a.monthly_sip,
            "current_additional_investment": additional_investment
            * weights.get(a.account_type, 0.0),
        }

    year_results = []
    per_type_year_end = {a.account_type: [] for a in account_type_inputs}

    for month in range(1, months + 1):
        year_number = (month - 1) // 12 + 1
        is_year_start = (month - 1) % 12 == 0

        for s in state.values():
            if is_year_start and month > 1:
                s["current_monthly_sip"] *= 1 + step_up_percent / 100
                s["current_additional_investment"] *= 1 + step_up_percent / 100
            if is_year_start:
                s["value"] += s["current_additional_investment"]
            s["value"] += s["current_monthly_sip"]
            s["value"] *= 1 + s["monthly_rate"]

        if month % 12 == 0:
            nominal_total = sum(s["value"] for s in state.values())
            real_total = nominal_total / ((1 + inflation_rate_percent / 100) ** year_number)
            year_results.append(
                {
                    "year": year_number,
                    "nominal_value": round(nominal_total, 2),
                    "real_value": round(real_total, 2),
                }
            )
            for acc_type, s in state.items():
                per_type_year_end[acc_type].append(
                    {"year": year_number, "value": round(s["value"], 2)}
                )

    return {"years": year_results, "per_type_year_end": per_type_year_end}


def compute_weighted_rate(
    account_type_inputs: list[AccountTypeSipInput],
    per_type_year_end: dict,
    year: int,
) -> float:
    rate_by_type = {a.account_type: a.rate_percent for a in account_type_inputs}
    total_value = 0.0
    weighted_sum = 0.0
    for acc_type, yearly_values in per_type_year_end.items():
        entry = next((v for v in yearly_values if v["year"] == year), None)
        if entry:
            total_value += entry["value"]
            weighted_sum += entry["value"] * rate_by_type.get(acc_type, 0.0)
    if total_value == 0:
        return 0.0
    return round(weighted_sum / total_value, 2)


def compute_fire_plan(
    starting_corpus: float,
    retirement_year: int,
    monthly_expense_today: float,
    inflation_rate_percent: float,
    post_retirement_growth_percent: float,
    max_years: int = 100,   # was 50 — raised so depletion is found even if it takes longer
) -> dict:
    """
    Simulates month-by-month SWP withdrawals post retirement.

    Runs until the corpus depletes, or until max_years is reached — max_years
    is a safety ceiling only, not a target horizon. It should be generous
    enough that hitting it effectively means "sustainable indefinitely" for
    any realistic retirement scenario, not an artificial cutoff that could
    mask a real depletion point.
    """

    monthly_growth_rate = (1 + post_retirement_growth_percent / 100) ** (1 / 12) - 1
    starting_monthly_swp = monthly_expense_today * (
        (1 + inflation_rate_percent / 100) ** retirement_year
    )

    corpus = starting_corpus
    monthly_swp = starting_monthly_swp
    rows = []
    depleted_at_year = None

    for month in range(1, max_years * 12 + 1):
        year_number = (month - 1) // 12 + 1
        is_year_start = (month - 1) % 12 == 0
        if is_year_start and month > 1:
            monthly_swp *= 1 + inflation_rate_percent / 100

        corpus *= 1 + monthly_growth_rate
        corpus -= monthly_swp
        if corpus <= 0:
            depleted_at_year = year_number
            rows.append(
                {
                    "year": year_number,
                    "monthly_swp": round(monthly_swp, 2),
                    "total_value": 0.0,
                }
            )
            break

        if month % 12 == 0:
            rows.append(
                {
                    "year": year_number,
                    "monthly_swp": round(monthly_swp, 2),
                    "total_value": round(corpus, 2),
                }
            )

    return {
        "starting_monthly_swp": round(starting_monthly_swp, 2),
        "starting_corpus": round(starting_corpus, 2),
        "rows": rows,
        "depleted_at_year": depleted_at_year,
        "sustainable": depleted_at_year is None,
    }
