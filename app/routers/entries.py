from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db

router = APIRouter(tags=["entries"])


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
