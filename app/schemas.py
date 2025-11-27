# app/schemas.py
from pydantic import BaseModel
from typing import Optional

class HospitalCreate(BaseModel):
    name: str
    address: str
    phone: Optional[str] = None
    creation_batch_id: Optional[str] = None
