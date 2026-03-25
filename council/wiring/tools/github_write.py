from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param

update_file = HttpTool(
    name="Update File",
    description=(
        "Update (or create) a file in the GitHub repository. "
        "You MUST first read the file with Read File to get its current SHA. "
        "Provide filepath, sha, message (commit message), and content (base64-encoded)."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="PUT",
    params={
        "filepath": Param(description="Path to the file, e.g. memories/decisions.md"),
    },
    body=JsonBody(schema={
        "message": "string",
        "content": "string",
        "sha": "string",
    }),
    auth=BearerToken(env="GITHUB_TOKEN"),
)
