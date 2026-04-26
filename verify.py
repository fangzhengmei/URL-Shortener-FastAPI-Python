import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from shortener_app.models import Base
Base.metadata.create_all(bind=engine)

from shortener_app import models, schemas
from shortener_app.config import Settings

test_settings = Settings(
    env_name="Test",
    base_url="http://localhost:8000",
    db_url="sqlite:///:memory:",
    domains=["localhost:8000", "127.0.0.1:8000", "s.example.com", "t.example.com"]
)

import shortener_app.config
old_get_settings = shortener_app.config.get_settings.cache_clear
shortener_app.config.get_settings.cache_clear()
shortener_app.config.get_settings.cache_clear()

from shortener_app import crud

def run_tests():
    db = TestingSessionLocal()
    
    print("="*50)
    print("Test 1: Create URL with domain s.example.com")
    print("="*50)
    
    url1 = schemas.URLBase(
        target_url="https://example.com",
        domain="s.example.com"
    )
    db_url1 = crud.create_db_url(db, url1, domain="s.example.com")
    print(f"Created URL: key={db_url1.key}, domain={db_url1.domain}")
    print(f"target_url={db_url1.target_url}")
    assert db_url1.domain == "s.example.com"
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 2: Create URL with domain t.example.com")
    print("="*50)
    
    url2 = schemas.URLBase(
        target_url="https://google.com",
        domain="t.example.com"
    )
    db_url2 = crud.create_db_url(db, url2, domain="t.example.com")
    print(f"Created URL: key={db_url2.key}, domain={db_url2.domain}")
    print(f"target_url={db_url2.target_url}")
    assert db_url2.domain == "t.example.com"
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 3: Lookup URL with correct domain")
    print("="*50)
    
    found = crud.get_db_url_by_key(db, db_url1.key, "s.example.com")
    assert found is not None
    assert found.target_url == "https://example.com"
    print(f"Found URL: key={found.key}, domain={found.domain}, target={found.target_url}")
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 4: Lookup URL with wrong domain (should return None)")
    print("="*50)
    
    not_found = crud.get_db_url_by_key(db, db_url1.key, "t.example.com")
    assert not_found is None
    print(f"Correctly returned None when looking up with wrong domain")
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 5: Same key can exist in different domains")
    print("="*50)
    
    from shortener_app import keygen
    
    key = "TEST123"
    
    test_url1 = models.URL(
        domain="domain-a.com",
        key=key,
        secret_key=f"{key}_a1234567",
        target_url="https://site-a.com",
        is_active=True,
        clicks=0
    )
    db.add(test_url1)
    db.commit()
    db.refresh(test_url1)
    print(f"Created URL: domain-a.com/{key} -> https://site-a.com")
    
    test_url2 = models.URL(
        domain="domain-b.com",
        key=key,
        secret_key=f"{key}_b1234567",
        target_url="https://site-b.com",
        is_active=True,
        clicks=0
    )
    db.add(test_url2)
    db.commit()
    db.refresh(test_url2)
    print(f"Created URL: domain-b.com/{key} -> https://site-b.com")
    
    found_a = crud.get_db_url_by_key(db, key, "domain-a.com")
    found_b = crud.get_db_url_by_key(db, key, "domain-b.com")
    
    assert found_a.target_url == "https://site-a.com"
    assert found_b.target_url == "https://site-b.com"
    print(f"Lookup domain-a.com/{key} -> {found_a.target_url}")
    print(f"Lookup domain-b.com/{key} -> {found_b.target_url}")
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 6: Verify admin info returns correct domain URL")
    print("="*50)
    
    from shortener_app.main import get_admin_info
    
    url_local = schemas.URLBase(
        target_url="https://test.com",
        domain="localhost:8000"
    )
    db_url_local = crud.create_db_url(db, url_local, domain="localhost:8000")
    
    info = get_admin_info(db_url_local)
    print(f"URL: {info.url}")
    print(f"Domain in URL: {'localhost:8000' in info.url}")
    assert "localhost:8000" in info.url
    print("✓ Passed\n")
    
    print("="*50)
    print("Test 7: Verify get_admin_info with request_domain parameter")
    print("="*50)
    
    info2 = get_admin_info(db_url1, request_domain="127.0.0.1:8000")
    print(f"URL: {info2.url}")
    print(f"Using request_domain: 127.0.0.1:8000")
    assert "127.0.0.1:8000" in info2.url
    print("✓ Passed\n")
    
    db.close()
    print("="*50)
    print("All tests passed! ✓")
    print("="*50)

if __name__ == "__main__":
    run_tests()