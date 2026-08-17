"""Integration test verifying backward compatibility loading pre-existing schedule database snapshots via REST API."""

import os
import shutil
import jwt
from pathlib import Path
from alembic import command
from alembic.config import Config
import pytest
from aiohttp.test_utils import TestClient, TestServer

from supernote.server.app import create_app
from supernote.server.config import ServerConfig
from supernote.server.services.user import JWT_ALGORITHM
from supernote.client.auth import AbstractAuth
from supernote.client.client import Client
from supernote.client.schedule import ScheduleClient

FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "fixtures"
SCHEDULE_FIXTURE_PATH = FIXTURES_DIR / "db_v1_schedule.sqlite"


@pytest.fixture
def schedule_test_db(tmp_path: Path) -> Path:
    """Copy the pre-populated v1 schedule fixture database to a temp path for testing."""
    target_path = tmp_path / "test_schedule_compat.sqlite"
    shutil.copy2(SCHEDULE_FIXTURE_PATH, target_path)

    # Apply alembic migrations to head using sync driver for reliable file flush
    sync_url = f"sqlite:///{target_path}"
    async_url = f"sqlite+aiosqlite:///{target_path}"
    os.environ["SUPERNOTE_DB_URL"] = async_url

    alembic_cfg = Config("/workspaces/supernote/supernote/alembic.ini")
    alembic_cfg.set_main_option("script_location", "/workspaces/supernote/supernote/alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")

    return target_path


async def test_load_existing_schedule_database_via_api(schedule_test_db: Path) -> None:
    """Verify that existing pre-upgrade schedule task groups and items are read correctly via Supernote REST API."""
    db_url = f"sqlite+aiosqlite:///{schedule_test_db}"
    os.environ["SUPERNOTE_DB_URL"] = db_url
    config = ServerConfig()
    app = create_app(config)

    server = TestServer(app)
    await server.start_server()

    # Generate auth token for the test user
    test_user = "test@example.com"
    secret = config.auth.secret_key
    token = jwt.encode({"sub": test_user}, secret, algorithm=JWT_ALGORITHM)
    await app["coordination_service"].set_value(f"session:{token}", f"{test_user}|", ttl=3600)

    class TokenAuth(AbstractAuth):
        async def async_get_access_token(self) -> str:
            return token

    client = TestClient(server)
    await client.start_server()
    base_url = str(client.make_url(""))

    supernote_client = Client(client.session, auth=TokenAuth(), host=base_url)
    schedule_client = ScheduleClient(supernote_client)

    try:
        # 1. List Task Groups via API
        groups = [g async for g in schedule_client.list_groups()]
        assert len(groups) >= 1
        inbox_group = next((g for g in groups if g.title == "Inbox Tasks"), None)
        assert inbox_group is not None
        group_id = inbox_group.task_list_id

        # 2. List Tasks in Group via API
        tasks_vo = await schedule_client.get_tasks_all(group_id=str(group_id))
        assert tasks_vo.success is True
        titles = {t.title for t in tasks_vo.schedule_task}
        assert "Buy Milk Before Upgrade" in titles
        assert "Schedule Dentist Appointment" in titles

    finally:
        await client.close()
        await server.close()
