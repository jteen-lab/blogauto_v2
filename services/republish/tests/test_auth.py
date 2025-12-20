"""
인증 시스템 테스트

테스트 항목:
- 사용자 등록
- 로그인/로그아웃
- JWT 토큰 검증
- 비밀번호 변경
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

from app.main import app
from app.core.database import db_manager
from app.core.config import settings
from app.models.user import User

# 테스트 설정
settings.environment = "testing"
settings.database_url = "sqlite+aiosqlite:///./test_blogauto.db"

@pytest_asyncio.fixture
async def async_client():
    """비동기 테스트 클라이언트"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest_asyncio.fixture
async def test_db():
    """테스트용 데이터베이스"""
    # 테스트 DB 초기화
    await db_manager.initialize()
    await db_manager.drop_tables()
    await db_manager.create_tables()

    yield

    # 정리
    await db_manager.close()

@pytest.fixture
def test_user_data():
    """테스트용 사용자 데이터"""
    return {
        "email": "test@example.com",
        "password": "TestPassword123",
        "full_name": "테스트 사용자"
    }

@pytest.fixture
def test_login_data():
    """테스트용 로그인 데이터"""
    return {
        "email": "test@example.com",
        "password": "TestPassword123"
    }

class TestUserRegistration:
    """사용자 등록 테스트"""

    @pytest.mark.asyncio
    async def test_register_success(self, async_client, test_db, test_user_data):
        """정상 회원가입 테스트"""
        response = await async_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 201
        data = response.json()

        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == test_user_data["email"]
        assert data["user"]["full_name"] == test_user_data["full_name"]
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, async_client, test_db, test_user_data):
        """중복 이메일 회원가입 테스트"""
        # 첫 번째 가입
        await async_client.post("/api/v1/auth/register", json=test_user_data)

        # 두 번째 가입 (같은 이메일)
        response = await async_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 400
        assert "이미 사용 중인 이메일" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_weak_password(self, async_client, test_db, test_user_data):
        """약한 비밀번호 회원가입 테스트"""
        test_user_data["password"] = "weak"

        response = await async_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, async_client, test_db, test_user_data):
        """잘못된 이메일 형식 테스트"""
        test_user_data["email"] = "invalid-email"

        response = await async_client.post("/api/v1/auth/register", json=test_user_data)

        assert response.status_code == 422

class TestUserLogin:
    """사용자 로그인 테스트"""

    @pytest.mark.asyncio
    async def test_login_success(self, async_client, test_db, test_user_data, test_login_data):
        """정상 로그인 테스트"""
        # 사용자 등록
        await async_client.post("/api/v1/auth/register", json=test_user_data)

        # 로그인
        response = await async_client.post("/api/v1/auth/login", json=test_login_data)

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == test_login_data["email"]

    @pytest.mark.asyncio
    async def test_login_invalid_email(self, async_client, test_db, test_user_data):
        """존재하지 않는 이메일 로그인 테스트"""
        # 사용자 등록
        await async_client.post("/api/v1/auth/register", json=test_user_data)

        # 잘못된 이메일로 로그인
        response = await async_client.post("/api/v1/auth/login", json={
            "email": "wrong@example.com",
            "password": "TestPassword123"
        })

        assert response.status_code == 401
        assert "이메일 또는 비밀번호" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, async_client, test_db, test_user_data):
        """잘못된 비밀번호 로그인 테스트"""
        # 사용자 등록
        await async_client.post("/api/v1/auth/register", json=test_user_data)

        # 잘못된 비밀번호로 로그인
        response = await async_client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "WrongPassword123"
        })

        assert response.status_code == 401
        assert "이메일 또는 비밀번호" in response.json()["detail"]

class TestUserAuthentication:
    """사용자 인증 테스트"""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, async_client, test_db, test_user_data):
        """현재 사용자 정보 조회 테스트"""
        # 사용자 등록 및 로그인
        register_response = await async_client.post("/api/v1/auth/register", json=test_user_data)
        token = register_response.json()["access_token"]

        # 헤더에 토큰 포함하여 사용자 정보 조회
        headers = {"Authorization": f"Bearer {token}"}
        response = await async_client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 200
        data = response.json()

        assert data["email"] == test_user_data["email"]
        assert data["full_name"] == test_user_data["full_name"]
        assert data["tier"] == "free"
        assert data["is_active"] == True

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self, async_client, test_db):
        """토큰 없이 사용자 정보 조회 테스트"""
        response = await async_client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert "인증 토큰이 필요" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, async_client, test_db):
        """잘못된 토큰으로 사용자 정보 조회 테스트"""
        headers = {"Authorization": "Bearer invalid-token"}
        response = await async_client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 401

class TestUserLogout:
    """사용자 로그아웃 테스트"""

    @pytest.mark.asyncio
    async def test_logout_success(self, async_client, test_db, test_user_data):
        """정상 로그아웃 테스트"""
        # 사용자 등록 및 로그인
        register_response = await async_client.post("/api/v1/auth/register", json=test_user_data)
        token = register_response.json()["access_token"]

        # 로그아웃
        headers = {"Authorization": f"Bearer {token}"}
        response = await async_client.post("/api/v1/auth/logout", headers=headers)

        assert response.status_code == 200
        assert "로그아웃되었습니다" in response.json()["message"]

        # 로그아웃 후 사용자 정보 조회 실패 확인
        response = await async_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401

class TestPasswordChange:
    """비밀번호 변경 테스트"""

    @pytest.mark.asyncio
    async def test_change_password_success(self, async_client, test_db, test_user_data):
        """정상 비밀번호 변경 테스트"""
        # 사용자 등록 및 로그인
        register_response = await async_client.post("/api/v1/auth/register", json=test_user_data)
        token = register_response.json()["access_token"]

        # 비밀번호 변경
        headers = {"Authorization": f"Bearer {token}"}
        password_data = {
            "current_password": "TestPassword123",
            "new_password": "NewPassword456"
        }

        response = await async_client.post("/api/v1/auth/change-password",
                                         headers=headers, json=password_data)

        assert response.status_code == 200
        assert "비밀번호가 변경되었습니다" in response.json()["message"]

        # 새 비밀번호로 로그인 확인
        login_response = await async_client.post("/api/v1/auth/login", json={
            "email": test_user_data["email"],
            "password": "NewPassword456"
        })
        assert login_response.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, async_client, test_db, test_user_data):
        """현재 비밀번호 틀림 테스트"""
        # 사용자 등록 및 로그인
        register_response = await async_client.post("/api/v1/auth/register", json=test_user_data)
        token = register_response.json()["access_token"]

        # 잘못된 현재 비밀번호로 변경 시도
        headers = {"Authorization": f"Bearer {token}"}
        password_data = {
            "current_password": "WrongPassword123",
            "new_password": "NewPassword456"
        }

        response = await async_client.post("/api/v1/auth/change-password",
                                         headers=headers, json=password_data)

        assert response.status_code == 400
        assert "현재 비밀번호가 올바르지" in response.json()["detail"]

if __name__ == "__main__":
    # 테스트 실행
    pytest.main([__file__, "-v"])