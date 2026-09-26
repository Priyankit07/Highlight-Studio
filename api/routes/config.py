"""
Configuration schema route.
"""
from __future__ import annotations

from fastapi import APIRouter
from api.models import get_config_schema

router = APIRouter(tags=["Config"])


@router.get("/config/schema")
def config_schema():
    """
    Returns field definitions, constraints, groups, and defaults generated from Pydantic model.
    Single source of truth for the frontend forms.
    """
    return {
        "fields": get_config_schema()
    }
