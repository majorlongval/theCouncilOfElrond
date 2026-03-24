import json

import httpx
import pytest

from council.adapters.n8n.deployer import N8nDeployer


class MockTransport(httpx.BaseTransport):
    """Records requests and returns canned responses."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: dict[str, httpx.Response] = {}

    def add_response(self, method: str, path: str, status_code: int, json_data: dict):
        key = f"{method} {path}"
        self.responses[key] = httpx.Response(status_code, json=json_data)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.path}"
        if key in self.responses:
            return self.responses[key]
        # Default: return empty list for GET workflows
        if "workflows" in str(request.url) and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={"message": "not found"})


@pytest.fixture
def transport():
    return MockTransport()


@pytest.fixture
def deployer(transport):
    client = httpx.Client(transport=transport, base_url="http://n8n:5678")
    return N8nDeployer(client=client, api_key="test-key")


def test_deploy_creates_new_workflow(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "abc123"})
    transport.add_response("PATCH", "/api/v1/workflows/abc123", 200, {"id": "abc123", "active": True})

    workflow = {"name": "Test Workflow", "nodes": [], "connections": {}, "settings": {}}
    result = deployer.deploy(workflow)

    assert result == "abc123"
    post_req = next(r for r in transport.requests if r.method == "POST")
    body = json.loads(post_req.content)
    assert body["name"] == "Test Workflow"


def test_deploy_updates_existing_workflow(deployer, transport):
    transport.add_response("GET", "/api/v1/workflows", 200, {
        "data": [{"id": "existing-id", "name": "Test Workflow"}]
    })
    transport.add_response("PUT", "/api/v1/workflows/existing-id", 200, {"id": "existing-id"})
    transport.add_response("PATCH", "/api/v1/workflows/existing-id", 200, {"id": "existing-id", "active": True})

    workflow = {"name": "Test Workflow", "nodes": [], "connections": {}, "settings": {}}
    result = deployer.deploy(workflow)

    assert result == "existing-id"
    put_req = next(r for r in transport.requests if r.method == "PUT")
    assert "existing-id" in str(put_req.url)


def test_deploy_activates_workflow(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "new-id"})
    transport.add_response("PATCH", "/api/v1/workflows/new-id", 200, {"id": "new-id", "active": True})

    workflow = {"name": "Test", "nodes": [], "connections": {}, "settings": {}}
    deployer.deploy(workflow, activate=True)

    patch_req = next(r for r in transport.requests if r.method == "PATCH")
    body = json.loads(patch_req.content)
    assert body["active"] is True


def test_deployer_sends_api_key_header(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "abc"})
    transport.add_response("PATCH", "/api/v1/workflows/abc", 200, {"id": "abc"})

    deployer.deploy({"name": "Test", "nodes": [], "connections": {}, "settings": {}})

    for req in transport.requests:
        assert req.headers["X-N8N-API-KEY"] == "test-key"
