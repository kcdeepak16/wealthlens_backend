from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=schemas.SummaryResponse)
def get_summary(db: Session = Depends(get_db)):
    return crud.get_summary(db)


@router.get("/networth/history", response_model=list[schemas.NetWorthPoint])
def get_history(range: str = "all", db: Session = Depends(get_db)):
    if range.lower() not in {"3m", "6m", "1y", "3y", "5y", "all"}:
        raise HTTPException(status_code=422, detail="Invalid range")
    return crud.get_networth_history(db, crud.range_to_days(range))
