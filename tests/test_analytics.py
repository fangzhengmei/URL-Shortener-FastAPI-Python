# tests/test_analytics.py
# Test cases for analytics functionality

import json
import sys
import os
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shortener_app import models, crud, schemas
from shortener_app.constants import MIN_DAYS, MAX_DAYS, DEFAULT_DAYS
from shortener_app.database import Base
from shortener_app.geolocator import IPGeolocator, get_geolocator, get_geolocation
from shortener_app.main import app, get_db


TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestUserAgentParsing:
    def test_parse_desktop_chrome(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        result = crud.parse_user_agent(ua)
        assert result["device_type"] == "desktop"
        assert result["browser"] == "Chrome"
        assert result["os"] == "Windows"
        assert result["os_version"] == "10"

    def test_parse_mobile_android_chrome(self):
        ua = "Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        result = crud.parse_user_agent(ua)
        assert result["device_type"] == "mobile"
        assert result["os"] == "Android"

    def test_parse_mobile_iphone_safari(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        result = crud.parse_user_agent(ua)
        assert result["device_type"] == "mobile"
        assert result["browser"] == "Safari"
        assert result["os"] == "iOS"

    def test_parse_tablet_ipad(self):
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        result = crud.parse_user_agent(ua)
        assert result["device_type"] == "tablet"

    def test_parse_mac_safari(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        result = crud.parse_user_agent(ua)
        assert result["device_type"] == "desktop"
        assert result["browser"] == "Safari"
        assert result["os"] == "macOS"

    def test_parse_firefox_windows(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        result = crud.parse_user_agent(ua)
        assert result["browser"] == "Firefox"

    def test_parse_edge(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        result = crud.parse_user_agent(ua)
        assert result["browser"] == "Edge"

    def test_parse_empty_user_agent(self):
        result = crud.parse_user_agent("")
        assert result["device_type"] == "unknown"
        assert result["browser"] == "unknown"
        assert result["os"] == "unknown"

    def test_parse_none_user_agent(self):
        result = crud.parse_user_agent(None)
        assert result["device_type"] == "unknown"


class TestDaysParameterBounds:
    def test_min_days_constant(self):
        assert crud.MIN_DAYS == 1

    def test_max_days_constant(self):
        assert crud.MAX_DAYS == 365

    def test_default_days_constant(self):
        assert crud.DEFAULT_DAYS == 30

    def test_days_clamped_to_min(self, db_session: Session):
        test_url = models.URL(
            key="test123",
            secret_key="test123_secret",
            target_url="https://example.com"
        )
        db_session.add(test_url)
        db_session.commit()
        db_session.refresh(test_url)

        result = crud.get_daily_clicks(db_session, test_url.id, days=0)
        assert len(result) == crud.MIN_DAYS + 1

        result_neg = crud.get_daily_clicks(db_session, test_url.id, days=-5)
        assert len(result_neg) == crud.MIN_DAYS + 1

    def test_days_clamped_to_max(self, db_session: Session):
        test_url = models.URL(
            key="test123",
            secret_key="test123_secret",
            target_url="https://example.com"
        )
        db_session.add(test_url)
        db_session.commit()
        db_session.refresh(test_url)

        result = crud.get_daily_clicks(db_session, test_url.id, days=500)
        assert len(result) == crud.MAX_DAYS + 1

    def test_days_valid_range(self, db_session: Session):
        test_url = models.URL(
            key="test123",
            secret_key="test123_secret",
            target_url="https://example.com"
        )
        db_session.add(test_url)
        db_session.commit()
        db_session.refresh(test_url)

        result = crud.get_daily_clicks(db_session, test_url.id, days=7)
        assert len(result) == 8

        result_30 = crud.get_daily_clicks(db_session, test_url.id, days=30)
        assert len(result_30) == 31


class TestAnalyticsAPI:
    def create_test_url(self, client: TestClient) -> dict:
        response = client.post("/url", json={"target_url": "https://example.com"})
        assert response.status_code == 200
        return response.json()

    def test_analytics_invalid_secret_key(self, client: TestClient):
        response = client.get("/admin/invalid_secret/analytics")
        assert response.status_code == 404

    def test_analytics_days_too_small(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics?days=0")
        assert response.status_code == 422

    def test_analytics_days_negative(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics?days=-1")
        assert response.status_code == 422

    def test_analytics_days_too_large(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics?days=1000")
        assert response.status_code == 422

    def test_analytics_days_valid_min(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics?days=1")
        assert response.status_code == 200
        data = response.json()
        assert "analytics" in data
        assert len(data["analytics"]["daily_clicks"]) == 2

    def test_analytics_days_valid_max(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics?days=365")
        assert response.status_code == 200
        data = response.json()
        assert len(data["analytics"]["daily_clicks"]) == 366

    def test_analytics_default_days(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics")
        assert response.status_code == 200
        data = response.json()
        assert len(data["analytics"]["daily_clicks"]) == 31

    def test_analytics_daily_endpoint_days_validation(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response_zero = client.get(f"/admin/{secret_key}/analytics/daily?days=0")
        assert response_zero.status_code == 422
        
        response_neg = client.get(f"/admin/{secret_key}/analytics/daily?days=-5")
        assert response_neg.status_code == 422
        
        response_large = client.get(f"/admin/{secret_key}/analytics/daily?days=500")
        assert response_large.status_code == 422
        
        response_valid = client.get(f"/admin/{secret_key}/analytics/daily?days=7")
        assert response_valid.status_code == 200


class TestFullAnalyticsFlow:
    def create_test_url(self, client: TestClient) -> dict:
        response = client.post("/url", json={"target_url": "https://example.com"})
        assert response.status_code == 200
        return response.json()

    def test_click_creates_log(self, client: TestClient):
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        initial_response = client.get(f"/admin/{secret_key}/analytics")
        initial_data = initial_response.json()
        assert initial_data["clicks"] == 0
        assert initial_data["analytics"]["total_clicks"] == 0
        
        client.get(f"/{url_key}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"})
        
        after_click_response = client.get(f"/admin/{secret_key}/analytics")
        after_click_data = after_click_response.json()
        assert after_click_data["clicks"] == 1
        assert after_click_data["analytics"]["total_clicks"] == 1

    def test_device_stats_aggregation(self, client: TestClient, db_session: Session):
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
        
        for _ in range(3):
            client.get(f"/{url_key}", headers={"User-Agent": desktop_ua})
        
        for _ in range(2):
            client.get(f"/{url_key}", headers={"User-Agent": mobile_ua})
        
        response = client.get(f"/admin/{secret_key}/analytics/devices")
        data = response.json()
        stats = data["device_stats"]
        
        assert stats["desktop"]["count"] == 3
        assert stats["mobile"]["count"] == 2
        assert stats["desktop"]["percentage"] == 60.0
        assert stats["mobile"]["percentage"] == 40.0

    def test_all_analytics_endpoints(self, client: TestClient):
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        client.get(f"/{url_key}", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Referer": "https://google.com"
        })
        
        endpoints = [
            f"/admin/{secret_key}/analytics",
            f"/admin/{secret_key}/analytics/daily",
            f"/admin/{secret_key}/analytics/devices",
            f"/admin/{secret_key}/analytics/browsers",
            f"/admin/{secret_key}/analytics/os",
            f"/admin/{secret_key}/analytics/referers",
            f"/admin/{secret_key}/analytics/countries",
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, f"Endpoint {endpoint} failed with status {response.status_code}"

    def test_empty_stats_returns_valid_data(self, client: TestClient):
        url_info = self.create_test_url(client)
        secret_key = url_info["admin_url"].split("/")[-1]
        
        response = client.get(f"/admin/{secret_key}/analytics")
        data = response.json()
        
        assert data["clicks"] == 0
        assert data["analytics"]["total_clicks"] == 0
        assert len(data["analytics"]["daily_clicks"]) == 31
        assert data["analytics"]["device_stats"] == {}
        assert data["analytics"]["browser_stats"] == {}
        assert data["analytics"]["os_stats"] == {}
        assert data["analytics"]["referer_stats"] == []
        assert data["analytics"]["country_stats"] == {}


class TestRefererTracking:
    def create_test_url(self, client: TestClient) -> dict:
        response = client.post("/url", json={"target_url": "https://example.com"})
        assert response.status_code == 200
        return response.json()

    def test_referer_is_recorded(self, client: TestClient):
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        client.get(f"/{url_key}", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Referer": "https://twitter.com"
        })
        
        response = client.get(f"/admin/{secret_key}/analytics/referers")
        data = response.json()
        
        assert len(data["referer_stats"]) == 1
        assert data["referer_stats"][0]["referer"] == "https://twitter.com"
        assert data["referer_stats"][0]["count"] == 1

    def test_empty_referer_not_recorded(self, client: TestClient):
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        client.get(f"/{url_key}", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        })
        
        response = client.get(f"/admin/{secret_key}/analytics/referers")
        data = response.json()
        
        assert data["referer_stats"] == []


class TestIPGeolocation:
    def test_private_ip_detection_localhost(self):
        geolocator = IPGeolocator()
        assert geolocator._is_private_ip("127.0.0.1") == True
        assert geolocator._is_private_ip("::1") == True
        assert geolocator._is_private_ip("localhost") == True

    def test_private_ip_detection_10_range(self):
        geolocator = IPGeolocator()
        assert geolocator._is_private_ip("10.0.0.1") == True
        assert geolocator._is_private_ip("10.255.255.255") == True

    def test_private_ip_detection_172_range(self):
        geolocator = IPGeolocator()
        assert geolocator._is_private_ip("172.16.0.1") == True
        assert geolocator._is_private_ip("172.31.255.255") == True
        assert geolocator._is_private_ip("172.15.255.255") == False
        assert geolocator._is_private_ip("172.32.0.1") == False

    def test_private_ip_detection_192_168_range(self):
        geolocator = IPGeolocator()
        assert geolocator._is_private_ip("192.168.0.1") == True
        assert geolocator._is_private_ip("192.168.255.255") == True
        assert geolocator._is_private_ip("192.167.255.255") == False

    def test_public_ip_not_private(self):
        geolocator = IPGeolocator()
        assert geolocator._is_private_ip("8.8.8.8") == False
        assert geolocator._is_private_ip("1.1.1.1") == False

    def test_empty_ip_returns_none(self):
        result = get_geolocation("")
        assert result == (None, None, None)

    def test_none_ip_returns_none(self):
        result = get_geolocation(None)
        assert result == (None, None, None)


class TestGeolocationIntegration:
    def create_test_url(self, client: TestClient) -> dict:
        response = client.post("/url", json={"target_url": "https://example.com"})
        assert response.status_code == 200
        return response.json()

    @patch('shortener_app.geolocator.urlopen')
    def test_geolocation_api_mocked_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "success",
            "country": "United States",
            "countryCode": "US",
            "region": "CA",
            "regionName": "California",
            "city": "San Francisco"
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        geolocator = IPGeolocator()
        country, region, city = geolocator.lookup("8.8.8.8")
        
        assert country == "United States"
        assert region == "California"
        assert city == "San Francisco"

    @patch('shortener_app.geolocator.urlopen')
    def test_geolocation_api_mocked_failure(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "fail",
            "message": "invalid query"
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        geolocator = IPGeolocator()
        country, region, city = geolocator.lookup("invalid")
        
        assert country is None
        assert region is None
        assert city is None

    def test_geolocation_caching(self):
        geolocator = IPGeolocator(max_cache_size=10)
        
        with patch.object(geolocator, '_lookup_ip') as mock_lookup:
            mock_lookup.return_value = {
                'country': 'Test Country',
                'region': 'Test Region',
                'city': 'Test City'
            }
            
            geolocator.lookup("8.8.8.8")
            geolocator.lookup("8.8.8.8")
            geolocator.lookup("8.8.8.8")
            
            assert mock_lookup.call_count == 1
            
            cache_info = geolocator.cache_info()
            assert cache_info.hits == 2
            assert cache_info.misses == 1

    def test_geolocation_cache_clear(self):
        geolocator = IPGeolocator(max_cache_size=10)
        
        with patch.object(geolocator, '_lookup_ip') as mock_lookup:
            mock_lookup.return_value = {
                'country': 'Test Country',
                'region': 'Test Region',
                'city': 'Test City'
            }
            
            geolocator.lookup("8.8.8.8")
            geolocator.clear_cache()
            
            cache_info = geolocator.cache_info()
            assert cache_info.currsize == 0

    @patch('shortener_app.crud.get_geolocation')
    def test_click_log_with_geolocation(self, mock_get_geo, db_session: Session):
        mock_get_geo.return_value = ("United States", "California", "San Francisco")
        
        test_url = models.URL(
            key="test123",
            secret_key="test123_secret",
            target_url="https://example.com"
        )
        db_session.add(test_url)
        db_session.commit()
        db_session.refresh(test_url)
        
        click_log = crud.create_click_log(
            db=db_session,
            url_id=test_url.id,
            ip_address="8.8.8.8",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
        )
        
        assert click_log.country == "United States"
        assert click_log.region == "California"
        assert click_log.city == "San Francisco"
        mock_get_geo.assert_called_once_with("8.8.8.8")

    @patch('shortener_app.crud.get_geolocation')
    def test_country_stats_aggregation(self, mock_get_geo, client: TestClient, db_session: Session):
        mock_get_geo.side_effect = [
            ("United States", "California", "San Francisco"),
            ("United States", "New York", "New York City"),
            ("United Kingdom", "England", "London"),
            ("Canada", "Ontario", "Toronto"),
            ("United States", "California", "Los Angeles"),
        ]
        
        url_info = self.create_test_url(client)
        url_key = url_info["url"].split("/")[-1]
        secret_key = url_info["admin_url"].split("/")[-1]
        
        for _ in range(5):
            client.get(f"/{url_key}", headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            })
        
        response = client.get(f"/admin/{secret_key}/analytics/countries")
        data = response.json()
        stats = data["country_stats"]
        
        assert "United States" in stats
        assert stats["United States"]["count"] == 3
        assert "United Kingdom" in stats
        assert stats["United Kingdom"]["count"] == 1
        assert "Canada" in stats
        assert stats["Canada"]["count"] == 1
        
        total = sum(s["count"] for s in stats.values())
        assert total == 5
