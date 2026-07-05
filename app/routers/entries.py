from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(tags=["entries"])


@router.get("/snapshots/prefill", response_model=schemas.SnapshotPrefillResponse)
def get_snapshot_prefill_endpoint(db: Session = Depends(get_db)):
    return crud.get_snapshot_prefill(db)


@router.post("/snapshots", response_model=list[schemas.AccountEntryOut], status_code=status.HTTP_201_CREATED)
def create_snapshot(data: schemas.SnapshotCreate, db: Session = Depends(get_db)):
    try:
        return crud.create_snapshot(db, data)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    if not crud.delete_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": True}


@router.put("/entries/{entry_id}", response_model=schemas.AccountEntryOut)
def update_entry(entry_id: int, data: schemas.IndividualEntryCreate, db: Session = Depends(get_db)):
    try:
        return crud.update_entry(db, entry_id, data)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
