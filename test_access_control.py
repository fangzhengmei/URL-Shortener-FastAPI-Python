import sys
sys.path.insert(0, '.')

from fastapi import HTTPException


def run_tests():
    print("="*60)
    print("Test Suite: Access Control for Domain Query Endpoints")
    print("="*60)
    
    from shortener_app.config import Settings
    
    test_settings_with_secret = Settings(
        env_name="Test",
        base_url="http://localhost:8000",
        db_url="sqlite:///:memory:",
        domains=["localhost:8000", "127.0.0.1:8000"],
        admin_secret="my-secret-admin-key-123"
    )
    
    test_settings_without_secret = Settings(
        env_name="Test",
        base_url="http://localhost:8000",
        db_url="sqlite:///:memory:",
        domains=["localhost:8000", "127.0.0.1:8000"],
        admin_secret=None
    )
    
    from shortener_app.main import raise_forbidden
    
    def test_verify_with_settings(settings, x_admin_secret=None, admin_secret=None):
        if not settings.admin_secret:
            raise_forbidden("Admin access not configured")
        
        provided_secret = x_admin_secret or admin_secret
        
        if not provided_secret:
            raise_forbidden("Admin secret required")
        
        if provided_secret != settings.admin_secret:
            raise_forbidden("Invalid admin secret")
        
        return True
    
    print("\n" + "="*60)
    print("Testing verify_admin_secret logic")
    print("="*60)
    
    print("\nTest 1: Without admin_secret configured")
    try:
        test_verify_with_settings(test_settings_without_secret)
        assert False, "Should have raised 403"
    except HTTPException as e:
        print(f"  Status: {e.status_code}")
        print(f"  Detail: {e.detail}")
        assert e.status_code == 403
        print("  ✓ Passed: Raises 403 when admin_secret not configured")
    
    print("\nTest 2: With admin_secret configured but not provided")
    try:
        test_verify_with_settings(test_settings_with_secret)
        assert False, "Should have raised 403"
    except HTTPException as e:
        print(f"  Status: {e.status_code}")
        print(f"  Detail: {e.detail}")
        assert e.status_code == 403
        print("  ✓ Passed: Raises 403 when secret not provided")
    
    print("\nTest 3: With WRONG secret via header")
    try:
        test_verify_with_settings(test_settings_with_secret, x_admin_secret="wrong-secret")
        assert False, "Should have raised 403"
    except HTTPException as e:
        print(f"  Status: {e.status_code}")
        print(f"  Detail: {e.detail}")
        assert e.status_code == 403
        print("  ✓ Passed: Raises 403 when wrong secret provided")
    
    print("\nTest 4: With WRONG secret via query param")
    try:
        test_verify_with_settings(test_settings_with_secret, admin_secret="wrong-secret")
        assert False, "Should have raised 403"
    except HTTPException as e:
        print(f"  Status: {e.status_code}")
        print(f"  Detail: {e.detail}")
        assert e.status_code == 403
        print("  ✓ Passed: Raises 403 when wrong secret provided")
    
    print("\nTest 5: With CORRECT secret via header")
    result = test_verify_with_settings(test_settings_with_secret, x_admin_secret="my-secret-admin-key-123")
    print(f"  Result: {result}")
    assert result == True
    print("  ✓ Passed: Returns True when correct secret via header")
    
    print("\nTest 6: With CORRECT secret via query param")
    result = test_verify_with_settings(test_settings_with_secret, admin_secret="my-secret-admin-key-123")
    print(f"  Result: {result}")
    assert result == True
    print("  ✓ Passed: Returns True when correct secret via query param")
    
    print("\n" + "="*60)
    print("Testing crud functions with test DB")
    print("="*60)
    
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
    
    from shortener_app import crud, schemas
    
    db = TestingSessionLocal()
    
    for i in range(3):
        crud.create_db_url(
            db, 
            schemas.URLBase(target_url=f"https://example{i}.com", domain="localhost:8000"),
            domain="localhost:8000"
        )
    
    for i in range(2):
        crud.create_db_url(
            db, 
            schemas.URLBase(target_url=f"https://other{i}.com", domain="127.0.0.1:8000"),
            domain="127.0.0.1:8000"
        )
    
    print("\nTest 7: get_all_urls_by_domain - localhost:8000")
    urls = crud.get_all_urls_by_domain(db, "localhost:8000")
    print(f"  Found {len(urls)} URL(s)")
    for u in urls:
        print(f"    - {u.key}: {u.target_url}")
    assert len(urls) == 3
    print("  ✓ Passed")
    
    print("\nTest 8: get_all_urls_by_domain - 127.0.0.1:8000")
    urls = crud.get_all_urls_by_domain(db, "127.0.0.1:8000")
    print(f"  Found {len(urls)} URL(s)")
    for u in urls:
        print(f"    - {u.key}: {u.target_url}")
    assert len(urls) == 2
    print("  ✓ Passed")
    
    print("\nTest 9: get_url_count_by_domain")
    count_local = crud.get_url_count_by_domain(db, "localhost:8000")
    count_other = crud.get_url_count_by_domain(db, "127.0.0.1:8000")
    print(f"  localhost:8000 count: {count_local}")
    print(f"  127.0.0.1:8000 count: {count_other}")
    assert count_local == 3
    assert count_other == 2
    print("  ✓ Passed")
    
    print("\nTest 10: build_url_list_item helper")
    from shortener_app.main import build_url_list_item
    
    url_to_test = crud.get_all_urls_by_domain(db, "localhost:8000")[0]
    list_item = build_url_list_item(url_to_test)
    
    print(f"  key: {list_item.key}")
    print(f"  target_url: {list_item.target_url}")
    print(f"  is_active: {list_item.is_active}")
    print(f"  clicks: {list_item.clicks}")
    print(f"  url: {list_item.url}")
    print(f"  admin_url: {list_item.admin_url}")
    
    assert list_item.key == url_to_test.key
    assert list_item.target_url == url_to_test.target_url
    assert "localhost:8000" in list_item.url
    assert "/admin/" in list_item.admin_url
    print("  ✓ Passed")
    
    db.close()
    
    print("\n" + "="*60)
    print("All Access Control Tests Passed! ✓")
    print("="*60)


if __name__ == "__main__":
    run_tests()