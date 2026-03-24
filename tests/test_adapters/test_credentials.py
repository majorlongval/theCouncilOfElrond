import json

import httpx
import pytest

from council.adapters.n8n.credentials import N8nCredentialManager


class MockTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._existing_creds: list[dict] = []

    def set_existing(self, creds: list[dict]):
        self._existing_creds = creds

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and "credentials" in str(request.url):
            return httpx.Response(200, json={"data": self._existing_creds})
        if request.method == "POST" and "credentials" in str(request.url):
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "new-cred-id", "name": body["name"]})
        return httpx.Response(404)


@pytest.fixture
def transport():
    return MockTransport()


@pytest.fixture
def manager(transport):
    client = httpx.Client(transport=transport, base_url="http://n8n:5678")
    return N8nCredentialManager(client=client, api_key="test-key")


def test_ensure_telegram_credential(manager, transport):
    cred_id = manager.ensure_credential(
        name="Telegram account",
        cred_type="telegramApi",
        data={"accessToken": "bot-token-123"},
    )
    assert cred_id == "new-cred-id"


def test_returns_existing_credential_id(manager, transport):
    transport.set_existing([{"id": "existing-id", "name": "Telegram account"}])
    cred_id = manager.ensure_credential(
        name="Telegram account",
        cred_type="telegramApi",
        data={"accessToken": "bot-token-123"},
    )
    assert cred_id == "existing-id"
    # Should NOT have made a POST request
    post_reqs = [r for r in transport.requests if r.method == "POST"]
    assert len(post_reqs) == 0


def test_ensure_openai_credential_for_litellm(manager, transport):
    cred_id = manager.ensure_credential(
        name="LiteLLM Proxy",
        cred_type="openAiApi",
        data={"apiKey": "sk-council-local"},
    )
    assert cred_id == "new-cred-id"
    post_req = next(r for r in transport.requests if r.method == "POST")
    body = json.loads(post_req.content)
    assert body["type"] == "openAiApi"
    assert body["data"]["apiKey"] == "sk-council-local"
