"""
API routes for managing optional browser/file cookies for yt-dlp.
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.cookies_config import (
    clear_cookies,
    get_cookies_config,
    save_cookies_file,
    set_browser_cookies,
    SUPPORTED_BROWSERS,
)

router = APIRouter(prefix="/cookies", tags=["Cookies"])


class BrowserCookiesRequest(BaseModel):
    browser: str


@router.get("")
def get_cookies():
    return get_cookies_config()


@router.post("/browser")
def set_browser(payload: BrowserCookiesRequest):
    try:
        return set_browser_cookies(payload.browser)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_BROWSER", "message": str(e)},
        )


@router.post("/upload")
async def upload_cookies(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_FILE", "message": "Missing file name"},
        )
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:  # 5 MB cap on cookies file
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "FILE_TOO_LARGE", "message": "Cookies file must be under 5 MB"},
        )
    return save_cookies_file(content)


@router.delete("")
def delete_cookies():
    return clear_cookies()
