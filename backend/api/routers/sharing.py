from secrets import token_urlsafe
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.requests import Request
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import get_current_user
from services.book_service import get_book_for_user
from services.note_service import serialize_shared_book

router = APIRouter(tags=["sharing"])


@router.post("/books/{book_id}/share", summary="Create share QR link")
def create_share_link(
    book_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: db_models.User = Depends(get_current_user),
):
    book = get_book_for_user(db, book_id, user.id)
    link = db_models.ShareLink(book_id=book.id, token=token_urlsafe(18))
    db.add(link)
    db.commit()
    db.refresh(link)
    share_url = str(request.url_for("public_shared_book", token=link.token))
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote(share_url)}"
    verified = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == link.token).first() is not None
    return {"token": link.token, "share_url": share_url, "qr_url": qr_url, "verified": verified}


@router.get("/share/{token}", name="public_shared_book", summary="Open shared book")
def public_shared_book(token: str, db: Session = Depends(get_db)):
    link = db.query(db_models.ShareLink).filter(db_models.ShareLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    return serialize_shared_book(link.book)
