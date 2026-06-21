from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy.orm import Session

from database import db_models
from database.db_manager import get_db
from dependencies.auth import ALGORITHM, SECRET_KEY, get_password_hash, verify_password

router = APIRouter(tags=["auth"])


@router.post("/signup", summary="Create user account")
def signup(username: str, password: str, db: Session = Depends(get_db)):
    if db.query(db_models.User).filter(db_models.User.username == username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    new_user = db_models.User(username=username, hashed_password=get_password_hash(password))
    db.add(new_user)
    db.commit()
    return {"status": "User created"}


@router.post("/token", summary="Login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(db_models.User).filter(db_models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong username or password")
    access_token = jwt.encode({"sub": user.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": access_token, "token_type": "bearer"}
