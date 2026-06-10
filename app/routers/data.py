from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db

router = APIRouter(tags=["data"])


@router.delete("/data/all")
def clear_all_data(db: Session = Depends(get_db)):
    crud.clear_all_data(db)
    return {"deleted": True}
