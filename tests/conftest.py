from __future__ import annotations

import sys
import shutil
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def make_auth_headers():
    from agent_framework.api.auth_api import auth_manager, storage
    from agent_framework.core.auth import UserRole

    def _make(*, role: UserRole = UserRole.MEMBER):
        suffix = uuid.uuid4().hex
        user = auth_manager.register_user(
            username=f"user_{suffix}",
            email=f"user_{suffix}@example.com",
            password="test-password-123",
            full_name="Test User",
        )
        if role != UserRole.MEMBER:
            user.role = role
            storage.update_user(user)
        token = auth_manager.generate_token(user)
        return {"Authorization": f"Bearer {token}"}, user

    return _make


@pytest.fixture
def workspace_tmp_dir():
    path = ROOT / ".tmp" / f"pytest_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_gateway_service():
    from agent_framework.gateway.service import set_gateway_service

    set_gateway_service(None)
    try:
        yield
    finally:
        set_gateway_service(None)
