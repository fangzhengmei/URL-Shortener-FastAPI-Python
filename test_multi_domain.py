import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shortener_app.main import app, get_db
from shortener_app.models import Base
from shortener_app.config import get_settings, Settings


@pytest.fixture
def test_settings():
    return Settings(
        env_name="Test",
        base_url="http://localhost:8000",
        db_url="sqlite:///:memory:",
        domains=["localhost:8000", "127.0.0.1:8000", "s.example.com", "t.example.com"]
    )


@pytest.fixture
def client(test_settings):
    from unittest.mock import patch
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch('shortener_app.config.get_settings', return_value=test_settings):
        yield TestClient(app)
    
    app.dependency_overrides.clear()


class TestMultiDomain:
    def test_get_available_domains(self, client):
        response = client.get("/domains")
        assert response.status_code == 200
        domains = response.json()
        assert "localhost:8000" in domains
        assert "s.example.com" in domains

    def test_create_url_without_domain_uses_request_domain(self, client):
        response = client.post(
            "/url",
            json={"target_url": "https://example.com"},
            headers={"Host": "s.example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "s.example.com" in data["url"]
        assert data["domain"] == "s.example.com"

    def test_create_url_with_specific_domain(self, client):
        response = client.post(
            "/url",
            json={
                "target_url": "https://google.com",
                "domain": "t.example.com"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "t.example.com" in data["url"]
        assert data["domain"] == "t.example.com"

    def test_create_url_with_invalid_domain_fails(self, client):
        response = client.post(
            "/url",
            json={
                "target_url": "https://google.com",
                "domain": "invalid.com"
            }
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_same_key_different_domains_work_independently(self, client):
        response1 = client.post(
            "/url",
            json={
                "target_url": "https://example.com",
                "domain": "s.example.com"
            }
        )
        assert response1.status_code == 200
        key1 = response1.json()["key"]
        url1 = response1.json()["url"]

        response2 = client.post(
            "/url",
            json={
                "target_url": "https://google.com",
                "domain": "t.example.com"
            }
        )
        assert response2.status_code == 200
        key2 = response2.json()["key"]
        url2 = response2.json()["url"]

        print(f"Key1: {key1}, URL1: {url1}")
        print(f"Key2: {key2}, URL2: {url2}")

        assert response1.json()["domain"] == "s.example.com"
        assert response2.json()["domain"] == "t.example.com"

    def test_forward_to_target_with_correct_domain(self, client):
        create_response = client.post(
            "/url",
            json={
                "target_url": "https://example.com",
                "domain": "s.example.com"
            }
        )
        assert create_response.status_code == 200
        data = create_response.json()
        key = data["key"]

        redirect_response = client.get(
            f"/{key}",
            headers={"Host": "s.example.com"},
            follow_redirects=False
        )
        assert redirect_response.status_code == 307
        assert redirect_response.headers["location"] == "https://example.com"

    def test_forward_wrong_domain_returns_404(self, client):
        create_response = client.post(
            "/url",
            json={
                "target_url": "https://example.com",
                "domain": "s.example.com"
            }
        )
        assert create_response.status_code == 200
        key = create_response.json()["key"]

        response = client.get(
            f"/{key}",
            headers={"Host": "t.example.com"}
        )
        assert response.status_code == 404

    def test_admin_info_uses_correct_domain(self, client):
        create_response = client.post(
            "/url",
            json={
                "target_url": "https://example.com",
                "domain": "t.example.com"
            }
        )
        assert create_response.status_code == 200
        data = create_response.json()
        secret_key = data["admin_url"].split("/")[-1]

        admin_response = client.get(f"/admin/{secret_key}")
        assert admin_response.status_code == 200
        admin_data = admin_response.json()
        assert "t.example.com" in admin_data["url"]
        assert admin_data["domain"] == "t.example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])