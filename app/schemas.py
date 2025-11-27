"""Pydantic schema definitions used by the hospital bulk processor.

This module defines the small request/response models used by the application.
Schemas are intentionally minimal and typed to ensure consistent payloads
when creating hospitals or validating incoming data.

Docstring style matches the concise/PEP257 style used in app/main.py.
"""
from pydantic import BaseModel
from typing import Optional

class HospitalCreate(BaseModel):
    """Schema for creating a hospital record sent to the external API.

    Attributes:
        name: Human-readable hospital name.
        address: Postal address of the hospital.
        phone: Optional phone number (free-form).
        creation_batch_id: Optional batch UUID associated with the creation request.
    """
    name: str
    address: str
    phone: Optional[str] = None
    creation_batch_id: Optional[str] = None
