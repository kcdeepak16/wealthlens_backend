from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.forecast import (
    AccountTypeSipInput,
    compute_fire_plan,
    compute_projection,
    compute_weighted_rate,
)

router = APIRouter(tags=["forecast"])


def _latest_value_for_type(db: Session, accounts: list[models.Account], account_type: str) -> float:
    total = 0.0
    for account in [item for item in accounts if item.type == account_type]:
        latest = db.scalar(
            select(models.AccountEntry)
            .where(models.AccountEntry.account_id == account.id)
            .order_by(models.AccountEntry.date_of_entry.desc(), models.AccountEntry.id.desc())
            .limit(1)
        )
        if latest:
            total += float(latest.current_value)
    return round(total, 2)


@router.get("/forecast/config", response_model=schemas.ForecastConfigResponse)
def get_forecast_config(db: Session = Depends(get_db)):
    accounts = list(
        db.scalars(
            select(models.Account)
            .where(models.Account.consider_for_networth.is_(True))
            .order_by(models.Account.type)
        ).all()
    )
    types_present = sorted({account.type for account in accounts})

    account_type_configs = []
    for account_type in types_present:
        latest_profit = db.scalar(
            select(models.AccountTypeProfit)
            .where(models.AccountTypeProfit.account_type == account_type)
            .order_by(models.AccountTypeProfit.date_of_entry.desc(), models.AccountTypeProfit.id.desc())
            .limit(1)
        )
        account_type_configs.append(
            schemas.ForecastAccountTypeConfig(
                account_type=account_type,
                current_value=_latest_value_for_type(db, accounts, account_type),
                default_rate_percent=float(latest_profit.profit_percentage)
                if latest_profit
                else 0.0,
                has_profit_history=latest_profit is not None,
            )
        )

    saved = db.scalar(select(models.ForecastSettings).limit(1))
    return schemas.ForecastConfigResponse(
        account_types=account_type_configs,
        default_inflation_rate=6.0,
        saved_inputs=saved.config if saved else None,
    )


@router.post("/forecast/projection", response_model=schemas.ForecastProjectionResponse)
def post_forecast_projection(
    request: schemas.ForecastProjectionRequest, db: Session = Depends(get_db)
):
    accounts = list(
        db.scalars(select(models.Account).where(models.Account.consider_for_networth.is_(True))).all()
    )
    current_values = {
        item.account_type: _latest_value_for_type(db, accounts, item.account_type)
        for item in request.account_types
    }
    sip_inputs = [
        AccountTypeSipInput(
            account_type=item.account_type,
            monthly_sip=item.monthly_sip,
            rate_percent=item.rate_percent,
        )
        for item in request.account_types
    ]
    result = compute_projection(
        account_type_inputs=sip_inputs,
        current_values=current_values,
        step_up_percent=request.step_up_percent,
        additional_investment=request.additional_investment,
        inflation_rate_percent=request.inflation_rate_percent,
        years=request.years,
    )

    current_year = date.today().year
    year_points = [
        schemas.ForecastYearPoint(
            year=item["year"],
            calendar_year=current_year + item["year"],
            nominal_value=item["nominal_value"],
            real_value=item["real_value"],
            suggested_post_retirement_rate=compute_weighted_rate(
                sip_inputs, result["per_type_year_end"], item["year"]
            ),
        )
        for item in result["years"]
    ]

    saved = db.scalar(select(models.ForecastSettings).limit(1))
    if saved:
        saved.config = request.model_dump()
    else:
        db.add(models.ForecastSettings(config=request.model_dump()))
    db.commit()

    return schemas.ForecastProjectionResponse(years=year_points)


@router.post("/forecast/fire", response_model=schemas.FirePlanResponse)
def post_forecast_fire(request: schemas.FirePlanRequest):
    return schemas.FirePlanResponse(
        **compute_fire_plan(
            starting_corpus=request.starting_corpus,
            retirement_year=request.retirement_year,
            monthly_expense_today=request.monthly_expense_today,
            inflation_rate_percent=request.inflation_rate_percent,
            post_retirement_growth_percent=request.post_retirement_growth_percent,
            max_years=request.max_years,
        )
    )
