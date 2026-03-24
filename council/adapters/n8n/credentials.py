import httpx


class N8nCredentialManager:
    """Creates and manages n8n credentials via REST API.

    Follows an idempotent ensure pattern: looks up by name first,
    only POSTs if no credential with that name exists.
    """

    def __init__(self, client: httpx.Client, api_key: str):
        self._client = client
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

    def ensure_credential(self, name: str, cred_type: str, data: dict) -> str:
        """Create a credential if it doesn't exist. Returns the credential ID."""
        existing_id = self._find_by_name(name)
        if existing_id:
            return existing_id

        resp = self._client.post(
            "/api/v1/credentials",
            headers=self._headers(),
            json={"name": name, "type": cred_type, "data": data},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _find_by_name(self, name: str) -> str | None:
        """Return the ID of an existing credential matching the given name, or None."""
        resp = self._client.get("/api/v1/credentials", headers=self._headers())
        resp.raise_for_status()
        for cred in resp.json().get("data", []):
            if cred["name"] == name:
                return cred["id"]
        return None
