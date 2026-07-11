from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
import re

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import models, schemas


def _label_for_type(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _slugify_account_type(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or "account_type"


def ensure_account_types(db: Session) -> None:
    existing = set(db.scalars(select(models.AccountType.value)).all())
    changed = False
    if not existing:
        for value, label in schemas.DEFAULT_ACCOUNT_TYPES:
            db.add(models.AccountType(value=value, label=label))
        existing = {value for value, _ in schemas.DEFAULT_ACCOUNT_TYPES}
        changed = True

    account_types = set(db.scalars(select(models.Account.type).distinct()).all())
    for account_type in account_types - existing:
        db.add(models.AccountType(value=account_type, label=_label_for_type(account_type)))
        changed = True

    if changed:
        db.commit()


def get_account_types(db: Session) -> list[models.AccountType]:
    ensure_account_types(db)
    return list(db.scalars(select(models.AccountType).order_by(models.AccountType.label)).all())


def _account_type_exists(db: Session, value: str) -> bool:
    ensure_account_types(db)
    return db.get(models.AccountType, value) is not None


def create_account_type(db: Session, data: schemas.AccountTypeCreate) -> models.AccountType:
    ensure_account_types(db)
    base = _slugify_account_type(data.label)
    value = base
    index = 2
    while db.get(models.AccountType, value) is not None:
        value = f"{base}_{index}"
        index += 1
    account_type = models.AccountType(value=value, label=data.label)
    db.add(account_type)
    db.commit()
    db.refresh(account_type)
    return account_type


def update_account_type(
    db: Session, value: str, data: schemas.AccountTypeUpdate
) -> models.AccountType | None:
    ensure_account_types(db)
    account_type = db.get(models.AccountType, value)
    if not account_type:
        return None
    account_type.label = data.label
    db.commit()
    db.refresh(account_type)
    return account_type


def delete_account_type(db: Session, value: str) -> bool:
    ensure_account_types(db)
    account_type = db.get(models.AccountType, value)
    if not account_type:
        return False
    in_use = db.scalar(select(models.Account.id).where(models.Account.type == value).limit(1))
    if in_use:
        raise ValueError("Account type is used by one or more accounts")
    db.delete(account_type)
    db.commit()
    return True


def range_to_days(range_str: str) -> int | None:
    return {"3m": 90, "6m": 180, "1y": 365, "3y": 1095, "5y": 1825, "all": None}.get(
        range_str.lower()
    )


def _account_query():
    return select(models.Account).options(selectinload(models.Account.metrics))


def _account_stats(account: models.Account, db: Session) -> schemas.AccountWithStats:
    entries = list(
        db.scalars(
            select(models.AccountEntry)
            .where(models.AccountEntry.account_id == account.id)
            .order_by(models.AccountEntry.date_of_entry.desc(), models.AccountEntry.id.desc())
            .limit(6)
        )
    )
    current = entries[0].current_value if entries else None
    previous = entries[1].current_value if len(entries) > 1 else None
    change = current - previous if current is not None and previous is not None else None
    percent = (
        float(change / abs(previous) * 100)
        if change is not None and previous not in (None, Decimal("0"))
        else None
    )
    return schemas.AccountWithStats(
        id=account.id,
        name=account.name,
        type=account.type,
        date_of_start=account.date_of_start,
        consider_for_networth=account.consider_for_networth,
        metrics=[schemas.MetricOut.model_validate(metric) for metric in account.metrics],
        current_value=current,
        previous_value=previous,
        change_absolute=change,
        change_percent=percent,
        sparkline=[float(entry.current_value) for entry in reversed(entries)],
    )


def get_accounts(db: Session, include_excluded: bool = True) -> list[schemas.AccountWithStats]:
    query = _account_query().order_by(models.Account.name)
    if not include_excluded:
        query = query.where(models.Account.consider_for_networth.is_(True))
    return [_account_stats(account, db) for account in db.scalars(query).all()]


def get_account(db: Session, account_id: int) -> schemas.AccountWithStats | None:
    account = db.scalar(_account_query().where(models.Account.id == account_id))
    return _account_stats(account, db) if account else None


def create_account(db: Session, data: schemas.AccountCreate) -> models.Account:
    if not _account_type_exists(db, data.type):
        raise ValueError("Account type does not exist")
    account = models.Account(**data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(
    db: Session, account_id: int, data: schemas.AccountUpdate
) -> models.Account | None:
    account = db.get(models.Account, account_id)
    if not account:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "type" and not _account_type_exists(db, value):
            raise ValueError("Account type does not exist")
        setattr(account, key, value.strip() if key == "name" and value else value)
    db.commit()
    db.refresh(account)
    return account


def delete_account(db: Session, account_id: int) -> bool:
    account = db.get(models.Account, account_id)
    if not account:
        return False
    db.delete(account)
    db.commit()
    return True


def create_metric(db: Session, account_id: int, data: schemas.MetricCreate) -> models.Metric | None:
    if not db.get(models.Account, account_id):
        return None
    metric = models.Metric(account_id=account_id, **data.model_dump())
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric


def update_metric(db: Session, metric_id: int, data: schemas.MetricUpdate) -> models.Metric | None:
    metric = db.get(models.Metric, metric_id)
    if not metric:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(metric, key, value.strip() if key == "name" and value else value)
    db.commit()
    db.refresh(metric)
    return metric


def delete_metric(db: Session, metric_id: int) -> bool:
    metric = db.get(models.Metric, metric_id)
    if not metric:
        return False
    db.delete(metric)
    db.commit()
    return True


def _validate_metric_entries(
    db: Session, account_id: int, metric_entries: list[schemas.MetricEntryIn]
) -> None:
    metric_ids = [entry.metric_id for entry in metric_entries]
    if len(metric_ids) != len(set(metric_ids)):
        raise ValueError("Metric entries must not contain duplicates")
    if not metric_ids:
        return
    valid_ids = set(
        db.scalars(
            select(models.Metric.id).where(
                models.Metric.account_id == account_id, models.Metric.id.in_(metric_ids)
            )
        ).all()
    )
    if valid_ids != set(metric_ids):
        raise ValueError("One or more metrics do not belong to this account")


def _add_entry(
    db: Session,
    account_id: int,
    date_of_entry: date,
    current_value: Decimal,
    metric_entries: list[schemas.MetricEntryIn],
) -> models.AccountEntry:
    _validate_metric_entries(db, account_id, metric_entries)
    entry = models.AccountEntry(
        account_id=account_id, date_of_entry=date_of_entry, current_value=current_value
    )
    db.add(entry)
    db.flush()
    db.add_all(
        [
            models.MetricEntry(
                account_entry_id=entry.id, metric_id=item.metric_id, value=item.value
            )
            for item in metric_entries
        ]
    )
    return entry


def create_snapshot(db: Session, data: schemas.SnapshotCreate) -> list[models.AccountEntry]:
    required_ids = set(
        db.scalars(
            select(models.Account.id).where(models.Account.consider_for_networth.is_(True))
        ).all()
    )
    supplied_ids = [item.account_id for item in data.accounts]
    if len(supplied_ids) != len(set(supplied_ids)):
        raise ValueError("Each account may appear only once")
    if set(supplied_ids) != required_ids:
        raise ValueError("Snapshot must include every net worth account")
    if required_ids:
        duplicate = db.scalar(
            select(models.AccountEntry.id).where(
                models.AccountEntry.date_of_entry == data.date_of_entry,
                models.AccountEntry.account_id.in_(required_ids),
            )
        )
        if duplicate:
            raise FileExistsError("A snapshot already exists for this date")
    try:
        entries = [
            _add_entry(
                db,
                item.account_id,
                data.date_of_entry,
                item.current_value,
                item.metric_entries,
            )
            for item in data.accounts
        ]
        for profit in data.account_type_profits:
            existing = db.scalar(
                select(models.AccountTypeProfit.id).where(
                    models.AccountTypeProfit.account_type == profit.account_type,
                    models.AccountTypeProfit.date_of_entry == data.date_of_entry,
                )
            )
            if not existing:
                db.add(
                    models.AccountTypeProfit(
                        account_type=profit.account_type,
                        date_of_entry=data.date_of_entry,
                        profit_percentage=profit.profit_percentage,
                    )
                )
        db.commit()
        for entry in entries:
            db.refresh(entry)
        return entries
    except IntegrityError as exc:
        db.rollback()
        raise FileExistsError("A snapshot already exists for this date") from exc
    except Exception:
        db.rollback()
        raise


def create_individual_entry(
    db: Session, account_id: int, data: schemas.IndividualEntryCreate
) -> models.AccountEntry:
    account = db.get(models.Account, account_id)
    if not account:
        raise LookupError("Account not found")
    if account.consider_for_networth:
        raise PermissionError("Net worth accounts must be entered through a snapshot")
    if db.scalar(
        select(models.AccountEntry.id).where(
            models.AccountEntry.account_id == account_id,
            models.AccountEntry.date_of_entry == data.date_of_entry,
        )
    ):
        raise FileExistsError("An entry already exists for this date")
    try:
        entry = _add_entry(
            db, account_id, data.date_of_entry, data.current_value, data.metric_entries
        )
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError as exc:
        db.rollback()
        raise FileExistsError("An entry already exists for this date") from exc
    except Exception:
        db.rollback()
        raise


def get_snapshot_prefill(db: Session) -> dict:
    accounts = list(
        db.scalars(
            select(models.Account)
            .options(selectinload(models.Account.metrics))
            .where(models.Account.consider_for_networth.is_(True))
            .order_by(models.Account.name)
        ).all()
    )

    account_prefills = []
    for account in accounts:
        latest_entry = db.scalar(
            select(models.AccountEntry)
            .where(models.AccountEntry.account_id == account.id)
            .order_by(models.AccountEntry.date_of_entry.desc(), models.AccountEntry.id.desc())
            .limit(1)
        )
        metric_prefills = []
        for metric in account.metrics:
            last_metric_entry = db.scalar(
                select(models.MetricEntry)
                .join(models.AccountEntry)
                .where(
                    models.AccountEntry.account_id == account.id,
                    models.MetricEntry.metric_id == metric.id,
                )
                .order_by(models.AccountEntry.date_of_entry.desc(), models.AccountEntry.id.desc())
                .limit(1)
            )
            metric_prefills.append(
                {
                    "metric_id": metric.id,
                    "last_value": last_metric_entry.value if last_metric_entry else None,
                }
            )
        account_prefills.append(
            {
                "account_id": account.id,
                "last_current_value": latest_entry.current_value if latest_entry else None,
                "metrics": metric_prefills,
            }
        )

    distinct_types = list(db.scalars(select(models.Account.type).distinct()).all())
    type_profit_prefills = []
    for account_type in distinct_types:
        latest_profit = db.scalar(
            select(models.AccountTypeProfit)
            .where(models.AccountTypeProfit.account_type == account_type)
            .order_by(models.AccountTypeProfit.date_of_entry.desc(), models.AccountTypeProfit.id.desc())
            .limit(1)
        )
        type_profit_prefills.append(
            {
                "account_type": account_type,
                "last_profit_percentage": latest_profit.profit_percentage if latest_profit else None,
            }
        )

    return {"accounts": account_prefills, "account_type_profits": type_profit_prefills}


def get_entries_for_account(db: Session, account_id: int) -> list[models.AccountEntry]:
    return list(
        db.scalars(
            select(models.AccountEntry)
            .options(selectinload(models.AccountEntry.metric_entries))
            .where(models.AccountEntry.account_id == account_id)
            .order_by(models.AccountEntry.date_of_entry.desc(), models.AccountEntry.id.desc())
        ).all()
    )


def delete_entry(db: Session, entry_id: int) -> bool:
    entry = db.get(models.AccountEntry, entry_id)
    if not entry:
        return False
    db.delete(entry)
    db.commit()
    return True


def update_entry(db: Session, entry_id: int, data: schemas.IndividualEntryCreate) -> models.AccountEntry:
    entry = db.get(models.AccountEntry, entry_id)
    if not entry:
        raise LookupError("Entry not found")
    account = db.get(models.Account, entry.account_id)
    if not account:
        raise LookupError("Account not found")

    # Check for duplicate date for same account
    duplicate = db.scalar(
        select(models.AccountEntry.id).where(
            models.AccountEntry.account_id == entry.account_id,
            models.AccountEntry.date_of_entry == data.date_of_entry,
            models.AccountEntry.id != entry_id,
        )
    )
    if duplicate:
        raise FileExistsError("An entry already exists for this date")

    # Validate metric entries belong to this account
    _validate_metric_entries(db, account.id, data.metric_entries)

    try:
        entry.date_of_entry = data.date_of_entry
        entry.current_value = data.current_value
        # remove existing metric entries
        db.execute(delete(models.MetricEntry).where(models.MetricEntry.account_entry_id == entry_id))
        db.flush()
        # add provided metric entries
        db.add_all([
            models.MetricEntry(account_entry_id=entry.id, metric_id=item.metric_id, value=item.value)
            for item in data.metric_entries
        ])
        db.commit()
        db.refresh(entry)
        return entry
    except IntegrityError as exc:
        db.rollback()
        raise FileExistsError("An entry already exists for this date") from exc
    except Exception:
        db.rollback()
        raise


def get_account_chart_data(
    db: Session, account_id: int, range_days: int | None
) -> schemas.AccountChartData | None:
    account = db.scalar(_account_query().where(models.Account.id == account_id))
    if not account:
        return None
    query = (
        select(models.AccountEntry)
        .options(selectinload(models.AccountEntry.metric_entries))
        .where(models.AccountEntry.account_id == account_id)
        .order_by(models.AccountEntry.date_of_entry)
    )
    if range_days is not None:
        query = query.where(models.AccountEntry.date_of_entry >= date.today() - timedelta(days=range_days))
    entries = list(db.scalars(query).all())
    value_series = [
        schemas.ChartDataPoint(date=entry.date_of_entry, value=float(entry.current_value))
        for entry in entries
    ]
    metric_series = []
    for metric in account.metrics:
        by_entry = {
            entry.id: next(
                (float(item.value) for item in entry.metric_entries if item.metric_id == metric.id),
                None,
            )
            for entry in entries
        }
        metric_series.append(
            schemas.MetricChartSeries(
                metric_id=metric.id,
                metric_name=metric.name,
                is_percentage=metric.is_percentage,
                data=[
                    schemas.ChartDataPoint(date=entry.date_of_entry, value=by_entry[entry.id])
                    for entry in entries
                ],
            )
        )
    return schemas.AccountChartData(value_series=value_series, metric_series=metric_series)


def get_networth_history(db: Session, range_days: int | None) -> list[schemas.NetWorthPoint]:
    account_ids = set(
        db.scalars(
            select(models.Account.id).where(models.Account.consider_for_networth.is_(True))
        ).all()
    )
    if not account_ids:
        return []
    rows = db.execute(
        select(
            models.AccountEntry.date_of_entry,
            func.sum(models.AccountEntry.current_value),
        )
        .where(models.AccountEntry.account_id.in_(account_ids))
        .group_by(models.AccountEntry.date_of_entry)
        .order_by(models.AccountEntry.date_of_entry)
    ).all()
    if range_days is not None:
        cutoff = date.today() - timedelta(days=range_days)
        rows = [row for row in rows if row[0] >= cutoff]
    return [schemas.NetWorthPoint(date=row[0], net_worth=float(row[1])) for row in rows]


def get_summary(db: Session) -> schemas.SummaryResponse:
    history = get_networth_history(db, None)
    current = history[-1].net_worth if history else 0.0
    previous = history[-2].net_worth if len(history) > 1 else None
    change = current - previous if previous is not None else None
    change_percent = change / abs(previous) * 100 if change is not None and previous else None
    latest_date = history[-1].date if history else None

    type_totals: dict[str, float] = defaultdict(float)
    if latest_date:
        rows = db.execute(
            select(models.Account.type, models.AccountEntry.current_value)
            .join(models.AccountEntry, models.AccountEntry.account_id == models.Account.id)
            .where(
                models.Account.consider_for_networth.is_(True),
                models.AccountEntry.date_of_entry == latest_date,
            )
        ).all()
        for account_type, value in rows:
            type_totals[account_type] += float(value)
    breakdown = [
        schemas.PortfolioBreakdownItem(
            type=account_type,
            total_value=value,
            percentage=(value / current * 100) if current else 0,
        )
        for account_type, value in sorted(type_totals.items(), key=lambda item: item[1], reverse=True)
    ]

    monthly_growth = None
    if len(history) > 1:
        recent = [point for point in history if point.date >= history[-1].date - timedelta(days=90)]
        if len(recent) > 1:
            months = max((recent[-1].date - recent[0].date).days / 30.44, 1)
            monthly_growth = (recent[-1].net_worth - recent[0].net_worth) / months

    best_type = None
    best_pct = None
    if len(history) > 1:
        dates = [history[-2].date, history[-1].date]
        rows = db.execute(
            select(models.Account.type, models.AccountEntry.date_of_entry, func.sum(models.AccountEntry.current_value))
            .join(models.AccountEntry, models.AccountEntry.account_id == models.Account.id)
            .where(
                models.Account.consider_for_networth.is_(True),
                models.AccountEntry.date_of_entry.in_(dates),
            )
            .group_by(models.Account.type, models.AccountEntry.date_of_entry)
        ).all()
        values: dict[str, dict[date, float]] = defaultdict(dict)
        for account_type, entry_date, total in rows:
            values[account_type][entry_date] = float(total)
        for account_type, totals in values.items():
            if all(item in totals for item in dates) and totals[dates[0]] != 0:
                pct = (totals[dates[1]] - totals[dates[0]]) / abs(totals[dates[0]]) * 100
                if best_pct is None or pct > best_pct:
                    best_type, best_pct = account_type, pct

    earliest = db.scalar(select(func.min(models.Account.date_of_start)))
    age = (date.today() - earliest).days if earliest else None
    gaps = [
        (history[index].date - history[index - 1].date).days
        for index in range(1, len(history))
    ]
    metrics = schemas.SummaryMetrics(
        monthly_growth_3m=monthly_growth,
        best_performer_type=best_type,
        best_performer_pct=best_pct,
        portfolio_age_days=age,
        entries_logged=len(history),
        avg_entry_gap_days=sum(gaps) / len(gaps) if gaps else None,
    )
    excluded = [
        account for account in get_accounts(db, include_excluded=True) if not account.consider_for_networth
    ]
    return schemas.SummaryResponse(
        current_net_worth=current,
        previous_net_worth=previous,
        change_absolute=change,
        change_percent=change_percent,
        last_entry_date=latest_date,
        breakdown_by_type=breakdown,
        summary_metrics=metrics,
        excluded_accounts=excluded,
    )
