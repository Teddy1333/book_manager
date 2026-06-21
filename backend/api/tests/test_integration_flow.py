import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import db_models
from database.db_manager import engine as main_engine, get_db
from dependencies.auth import get_password_hash
from main import app


class BookFlowIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_url = f"sqlite:///{self.temp_dir.name}/integration.db"
        self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        db_models.Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.session_local()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        db_models.Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()
        main_engine.dispose()
        self.temp_dir.cleanup()

    def test_google_lookup_falls_back_to_open_library(self):
        fallback_match = {
            "title": "Twilight",
            "author": "Stephenie Meyer",
            "isbn": "9780316015844",
            "publisher": "Little, Brown",
            "pages": "498",
            "description": None,
            "cover_url": None,
            "source": "open_library",
            "tags": [],
        }

        with patch("services.search_service.google_books_search", return_value=[]), \
             patch("services.search_service.open_library_search", return_value=[fallback_match]):
            response = self.client.get("/lookup/google", params={"q": "twilight", "limit": 5})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [fallback_match])

    def test_book_photo_recognition_uses_uploaded_bytes(self):
        match = {
            "title": "Twilight",
            "author": "Stephenie Meyer",
            "isbn": "9780316015844",
            "publisher": "Little, Brown",
            "pages": "498",
            "description": None,
            "cover_url": None,
            "source": "open_library",
            "tags": [],
        }

        with patch("routers.lookup.ai_ocr", return_value="twilight"), \
             patch("routers.lookup.lookup_google_matches", return_value=[match]):
            response = self.client.post(
                "/books/photo/recognize",
                content=b"fake-image-bytes",
                headers={"Content-Type": "application/octet-stream"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ocr_text"], "twilight")
        self.assertEqual(response.json()["matches"], [match])

    def test_import_shared_book_copies_notes(self):
        owner = db_models.User(username="owner", hashed_password="hash")
        recipient = db_models.User(username="recipient", hashed_password=get_password_hash("pw"))
        db = self.session_local()
        try:
            db.add_all([owner, recipient])
            db.commit()
            source_book = db_models.Book(
                title="Shared Book",
                author="Reader",
                isbn="9780316015844",
                pages="498",
                owner_id=owner.id,
            )
            db.add(source_book)
            db.flush()
            db.add(db_models.Note(book_id=source_book.id, owner_id=owner.id, text="Shared note", page=12))
            link = db_models.ShareLink(book_id=source_book.id, token="shared-token")
            db.add(link)
            db.commit()
        finally:
            db.close()

        token_response = self.client.post("/token", data={"username": "recipient", "password": "pw"})
        auth_headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

        public_response = self.client.get("/share/shared-token")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.json()["notes"][0]["text"], "Shared note")

        import_response = self.client.post(
            "/books/import/share",
            json={"url": "http://127.0.0.1:8000/share/shared-token"},
            headers=auth_headers,
        )
        self.assertEqual(import_response.status_code, 201)
        imported = import_response.json()
        self.assertEqual(imported["title"], "Shared Book")
        self.assertEqual(imported["notes"][0]["text"], "Shared note")
        self.assertEqual(imported["notes"][0]["page"], 12)

    def test_signup_search_add_book_add_progress_from_photo(self):
        username = "integration_user"
        password = "strong-password"
        book_match = {
            "title": "Pod Igoto",
            "author": "Ivan Vazov",
            "isbn": "9789540900010",
            "publisher": "Bulgarian Writer",
            "pages": "432",
            "description": "Historical fiction test book for the integration flow.",
            "cover_url": None,
            "source": "google_books",
            "tags": ["Bulgarian fiction"],
        }
        external_isbn_match = {
            "title": "Bai Ganyo",
            "author": "Aleko Konstantinov",
            "isbn": "9789540900027",
            "publisher": "Bulgarian Writer",
            "pages": "220",
            "description": "Satirical fiction test book.",
            "cover_url": None,
            "source": "google_books",
            "tags": ["Bulgarian fiction", "Satire"],
        }

        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

        self.assertEqual(
            self.client.post("/signup", params={"username": username, "password": password}).status_code, 200
        )

        token_response = self.client.post("/token", data={"username": username, "password": password})
        self.assertEqual(token_response.status_code, 200)
        auth_headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

        with patch("services.search_service.google_books_search", return_value=[book_match]):
            search_response = self.client.get("/lookup/google", params={"q": "Pod Igoto"})
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()[0]["title"], book_match["title"])

        create_response = self.client.post("/books", json=search_response.json()[0], headers=auth_headers)
        self.assertEqual(create_response.status_code, 201)
        created_book = create_response.json()

        self.assertEqual(
            self.client.post("/books", json=search_response.json()[0], headers=auth_headers).status_code, 409
        )

        with patch("routers.progress.ai_ocr", return_value="Page 128"):
            progress_response = self.client.post(
                f"/books/{created_book['id']}/progress/photo",
                content=b"fake-image-bytes",
                headers={**auth_headers, "Content-Type": "application/octet-stream"},
            )
        self.assertEqual(progress_response.status_code, 201)
        progress = progress_response.json()
        self.assertEqual(progress["current_page"], 128)
        self.assertEqual(progress["total_pages"], 432)
        self.assertEqual(progress["source"], "photo")

        book_response = self.client.get(f"/books/{created_book['id']}", headers=auth_headers)
        self.assertEqual(book_response.json()["latest_progress"]["current_page"], 128)
        self.assertEqual(book_response.json()["latest_progress"]["percentage"], 29.63)

        tags_response = self.client.get("/tags", headers=auth_headers)
        self.assertEqual(tags_response.json()[0]["name"], "bulgarian fiction")

        isbn_response = self.client.get(f"/lookup/isbn/{book_match['isbn']}")
        self.assertEqual(isbn_response.json()["source"], "local")

        stats = self.client.get("/user/stats", headers=auth_headers).json()
        self.assertEqual(stats["books_count"], 1)
        self.assertEqual(stats["total_read_pages"], 128)
        self.assertEqual(stats["top_genres"][0]["tag"], "bulgarian fiction")
        self.assertEqual(len(stats["last_7_days"]), 7)

        with patch("services.search_service.google_books_search", return_value=[external_isbn_match]):
            import_response = self.client.post(
                f"/books/import/isbn/{external_isbn_match['isbn']}", headers=auth_headers
            )
        self.assertEqual(import_response.status_code, 201)
        self.assertEqual(import_response.json()["title"], external_isbn_match["title"])

        share_response = self.client.post(f"/books/{created_book['id']}/share", headers=auth_headers)
        self.assertEqual(share_response.status_code, 200)
        share = share_response.json()
        self.assertTrue(share["verified"])
        self.assertIn("/share/", share["share_url"])
        self.assertIn("api.qrserver.com", share["qr_url"])

        public_response = self.client.get(f"/share/{share['token']}")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.json()["id"], created_book["id"])


if __name__ == "__main__":
    unittest.main()
