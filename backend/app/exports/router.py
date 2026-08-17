"""Placeholder router for the exports module.

This module is structured (router/service/repository/models/schemas) but not
yet implemented — see architecture.md for its target scope. Wired into
/api/v1 now so the route table and dev split are stable across the team.
"""
from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def not_implemented() -> dict:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="'exports' module is not implemented yet (Phase 1 skeleton only)",
    )
