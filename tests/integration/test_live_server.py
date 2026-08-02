"""End-to-end integration tests using out-of-process live server runner."""

import hashlib

import aiohttp
import pytest

from supernote.client import Supernote
from supernote.testing.server_runner import ServerHandle

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_fresh_live_server_e2e(live_server: ServerHandle) -> None:
    """Verify fresh live server health, admin user registration, SDK login, and CLI commands."""
    assert await live_server.is_healthy()

    user_email = "testuser@example.com"
    user_password = "password123"
    password_md5 = hashlib.md5(user_password.encode("utf-8")).hexdigest()

    # 1. Register user via Admin API
    async with aiohttp.ClientSession() as session:
        admin_client = live_server.create_admin_client(session)
        await admin_client.register(user_email, password_md5, "Test User")

    # 2. Verify SDK login and folder listing
    async with await Supernote.login(
        user_email, user_password, host=live_server.base_url
    ) as sn:
        assert sn.token is not None
        files = await sn.device.list_folder("/")
        assert files is not None

    # 3. Execute `supernote cloud login` CLI command via subprocess
    login_result = await live_server.run_cli(
        "cloud",
        "login",
        user_email,
        "--password",
        user_password,
        "--url",
        live_server.base_url,
    )
    assert login_result.returncode == 0, f"Login failed: {login_result.stderr}"
    assert "Login successful" in login_result.stdout

    # 4. Execute `supernote cloud ls` CLI command using cached credentials
    ls_result = await live_server.run_cli("cloud", "ls")
    assert ls_result.returncode == 0, f"ls failed: {ls_result.stderr}"


@pytest.mark.asyncio
async def test_migrated_live_server_e2e(
    populated_migrated_live_server: ServerHandle,
) -> None:
    """Verify live server starts with legacy v1 DB, migrates to head, and serves pre-existing users."""
    assert await populated_migrated_live_server.is_healthy()
    assert populated_migrated_live_server.db_path.exists()

    # Pre-seeded user login (verifying pre-existing v1 account works after migration)
    seed_email = "seed_user@example.com"
    seed_password = "seedpassword123"
    async with await Supernote.login(
        seed_email, seed_password, host=populated_migrated_live_server.base_url
    ) as sn:
        assert sn.token is not None
        files = await sn.device.list_folder("/")
        assert files is not None
