import time

import httpx


class N8nDeployer:
    """Deploys workflow JSON to n8n via its REST API.

    Stateful: holds an httpx.Client (connection pool + base URL) and an API key.
    Upserts by name — creates if absent, replaces via PUT if already present.
    """

    def __init__(self, client: httpx.Client, api_key: str):
        self._client = client
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

    def _find_workflow_by_name(self, name: str) -> str | None:
        """Return the ID of the first workflow matching `name`, or None.

        Fetches the first page (up to 100) — sufficient for typical council
        deployments where workflow count stays well below that ceiling.
        """
        resp = self._client.get("/api/v1/workflows", headers=self._headers(), params={"limit": 100})
        resp.raise_for_status()
        for wf in resp.json().get("data", []):
            if wf["name"] == name:
                return wf["id"]
        return None

    def deploy(self, workflow: dict, activate: bool = True) -> str:
        """Upsert a workflow and optionally activate it. Returns the workflow ID.

        Input:  workflow dict (n8n JSON format with at minimum a "name" key)
        Output: workflow ID string assigned by n8n

        POST /api/v1/workflows   — when no workflow with this name exists yet
        PUT  /api/v1/workflows/{id} — when a matching name is found (full replace)
        PATCH /api/v1/workflows/{id} — to flip active=True after upsert
        """
        name = workflow["name"]
        existing_id = self._find_workflow_by_name(name)

        if existing_id:
            resp = self._client.put(
                f"/api/v1/workflows/{existing_id}",
                headers=self._headers(),
                json=workflow,
            )
            resp.raise_for_status()
            workflow_id = existing_id
        else:
            resp = self._client.post(
                "/api/v1/workflows",
                headers=self._headers(),
                json=workflow,
            )
            resp.raise_for_status()
            workflow_id = resp.json()["id"]

        if activate:
            self._activate_with_retry(workflow_id)

        return workflow_id

    def _activate_with_retry(self, workflow_id: str, retries: int = 3, delay: float = 2.0) -> None:
        """Activate a workflow, retrying on failure.

        Sub-workflow references may fail validation if a dependency was just
        published. A short retry loop handles this race condition.
        """
        for attempt in range(retries):
            resp = self._client.post(
                f"/api/v1/workflows/{workflow_id}/activate",
                headers=self._headers(),
            )
            if resp.is_success:
                return
            if attempt < retries - 1:
                time.sleep(delay)
        # Final attempt failed — raise with error details
        resp.raise_for_status()
