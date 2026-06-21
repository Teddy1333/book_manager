from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from database.db_manager import Base


book_tags = Table(
    "book_tags",
    Base.metadata,
    Column("book_id", ForeignKey("books.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    books = relationship("Book", back_populates="owner")
    notes = relationship("Note", back_populates="owner")


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    author = Column(String)
    isbn = Column(String, nullable=True)
    publisher = Column(String, nullable=True)
    pages = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    cover_url = Column(String, nullable=True)
    source = Column(String, default="manual")
    owner_id = Column(Integer, ForeignKey("users.id"))

    owner = relationship("User", back_populates="books")
    tags = relationship("Tag", secondary=book_tags, back_populates="books")
    progress_entries = relationship(
        "ReadingProgress", back_populates="book", cascade="all, delete-orphan"
    )
    notes = relationship("Note", back_populates="book", cascade="all, delete-orphan")
    share_links = relationship("ShareLink", back_populates="book", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    books = relationship("Book", secondary=book_tags, back_populates="tags")


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    current_page = Column(Integer, nullable=False)
    total_pages = Column(Integer, nullable=True)
    source = Column(String, default="manual")
    created_at = Column(DateTime, default=utc_now, nullable=False)

    book = relationship("Book", back_populates="progress_entries")


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    page = Column(Integer, nullable=True)
    note_type = Column(String, default="manual")
    image_path = Column(String, nullable=True)
    audio_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    book = relationship("Book", back_populates="notes")
    owner = relationship("User", back_populates="notes")


class ShareLink(Base):
    __tablename__ = "share_links"

    id = Column(Integer, primary_key=True, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    book = relationship("Book", back_populates="share_links")
