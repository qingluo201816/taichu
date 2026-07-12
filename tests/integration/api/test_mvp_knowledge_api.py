"""Mongo-era structured knowledge API contract tests."""

import tempfile
import unittest
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


class MVPKnowledgeApiTest(unittest.IsolatedAsyncioTestCase):
    """Verify public lifecycle routes with an in-memory repository boundary."""

    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        app = create_app(
            app_settings=Settings(
                project_assets_dir=Path(self.temporary_directory.name)
            ),
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temporary_directory.cleanup()

    async def test_draft_confirm_reject_and_list_filter_contract(self) -> None:
        created_response = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": _complete_character_data("秦阳"),
            },
        )
        self.assertEqual(created_response.status_code, 200)
        created = created_response.json()["card"]
        card_id = created["id"]
        self.assertEqual(created["lifecycle"], "draft")
        self.assertNotIn("status", created)

        protected_response = await self.client.patch(
            f"/api/knowledge/cards/{card_id}",
            json={"updates": {"lifecycle": "confirmed"}},
        )
        self.assertEqual(protected_response.status_code, 422)

        confirmed_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/confirm"
        )
        self.assertEqual(confirmed_response.status_code, 200)
        self.assertEqual(
            confirmed_response.json()["card"]["lifecycle"],
            "confirmed",
        )
        default_response = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=all"
        )
        self.assertEqual(default_response.json()["total"], 1)

        rejected_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/reject"
        )
        self.assertEqual(rejected_response.status_code, 200)
        self.assertEqual(
            rejected_response.json()["card"]["lifecycle"],
            "rejected",
        )
        default_after_reject = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=all"
        )
        rejected_list = await self.client.get(
            "/api/knowledge/cards?type=character&lifecycle=rejected"
        )
        self.assertEqual(default_after_reject.json()["cards"], [])
        self.assertEqual(rejected_list.json()["cards"][0]["id"], card_id)

        old_transition_response = await self.client.post(
            f"/api/knowledge/cards/{card_id}/mark-active"
        )
        self.assertEqual(old_transition_response.status_code, 404)

    async def test_confirmed_identity_conflict_returns_409(self) -> None:
        first_id = await self._create_character(
            "秦阳",
            aliases=["秦师兄"],
        )
        second_id = await self._create_character(
            "另一人",
            aliases=["秦阳"],
        )
        first_confirm = await self.client.post(
            f"/api/knowledge/cards/{first_id}/confirm"
        )
        conflict = await self.client.post(
            f"/api/knowledge/cards/{second_id}/confirm"
        )

        self.assertEqual(first_confirm.status_code, 200)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(
            conflict.json()["error"]["code"],
            "KNOWLEDGE_CONFLICT",
        )

    async def test_schema_and_create_reject_legacy_or_system_fields(self) -> None:
        schema_response = await self.client.get(
            "/api/knowledge/schemas/character"
        )
        self.assertEqual(schema_response.status_code, 200)
        fields = {
            field["field_key"]: field
            for field in schema_response.json()["schema"]["fields"]
        }
        self.assertIn("lifecycle", fields)
        self.assertNotIn("status", fields)
        self.assertTrue(fields["name"]["required_when_confirmed"])

        legacy_status = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": {
                    **_complete_character_data("秦阳"),
                    "status": "active",
                },
            },
        )
        supplied_id = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": {
                    **_complete_character_data("秦阳"),
                    "id": "character-fixed",
                },
            },
        )
        self.assertEqual(legacy_status.status_code, 422)
        self.assertEqual(supplied_id.status_code, 422)

    async def _create_character(
        self,
        name: str,
        *,
        aliases: list[str],
    ) -> str:
        response = await self.client.post(
            "/api/knowledge/cards",
            json={
                "type": "character",
                "data": {
                    **_complete_character_data(name),
                    "aliases": aliases,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        return str(response.json()["card"]["id"])


def _complete_character_data(name: str) -> dict[str, object]:
    return {
        "name": name,
        "aliases": [],
        "summary": f"{name}的事实摘要。",
        "source_origin": "manual",
        "source_note": "作者手动确认。",
        "role_type": "protagonist",
    }
