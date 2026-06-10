from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(tags=["accounts"])


@router.get("/accounts", response_model=list[schemas.AccountWithStats])
def list_accounts(
    include_excluded: bool = Query(True), db: Session = Depends(get_db)
):
    return crud.get_accounts(db, include_excluded)


@router.post("/accounts", response_model=schemas.AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(data: schemas.AccountCreate, db: Session = Depends(get_db)):
    return crud.create_account(db, data)


@router.get("/accounts/{account_id}", response_model=schemas.AccountWithStats)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = crud.get_account(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.put("/accounts/{account_id}", response_model=schemas.AccountOut)
def update_account(account_id: int, data: schemas.AccountUpdate, db: Session = Depends(get_db)):
    account = crud.update_account(db, account_id, data)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.delete("/accounts/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    if not crud.delete_account(db, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"deleted": True}


@router.get("/accounts/{account_id}/entries", response_model=list[schemas.AccountEntryOut])
def get_entries(account_id: int, db: Session = Depends(get_db)):
    if not crud.get_account(db, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return crud.get_entries_for_account(db, account_id)


@router.get("/accounts/{account_id}/chart-data", response_model=schemas.AccountChartData)
def get_chart_data(account_id: int, range: str = "all", db: Session = Depends(get_db)):
    if range.lower() not in {"3m", "6m", "1y", "3y", "5y", "all"}:
        raise HTTPException(status_code=422, detail="Invalid range")
    data = crud.get_account_chart_data(db, account_id, crud.range_to_days(range))
    if not data:
        raise HTTPException(status_code=404, detail="Account not found")
    return data


@router.post(
    "/accounts/{account_id}/entries",
    response_model=schemas.AccountEntryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_individual_entry(
    account_id: int, data: schemas.IndividualEntryCreate, db: Session = Depends(get_db)
):
    try:
        return crud.create_individual_entry(db, account_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/accounts/{account_id}/metrics",
    response_model=schemas.MetricOut,
    status_code=status.HTTP_201_CREATED,
)
def create_metric(account_id: int, data: schemas.MetricCreate, db: Session = Depends(get_db)):
    metric = crud.create_metric(db, account_id, data)
    if not metric:
        raise HTTPException(status_code=404, detail="Account not found")
    return metric


@router.put("/metrics/{metric_id}", response_model=schemas.MetricOut)
def update_metric(metric_id: int, data: schemas.MetricUpdate, db: Session = Depends(get_db)):
    metric = crud.update_metric(db, metric_id, data)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    return metric


@router.delete("/metrics/{metric_id}")
def delete_metric(metric_id: int, db: Session = Depends(get_db)):
    if not crud.delete_metric(db, metric_id):
        raise HTTPException(status_code=404, detail="Metric not found")
    return {"deleted": True}
