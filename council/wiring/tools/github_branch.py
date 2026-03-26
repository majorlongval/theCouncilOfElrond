from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param

get_branch = HttpTool(
    name="Get Branch",
    description=(
        "Get branch info including the latest commit SHA. "
        "Use this to get the SHA of main before creating a new branch."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch}",
    method="GET",
    params={"branch": Param(description="Branch name, e.g. main")},
    auth=BearerToken(env="GITHUB_TOKEN"),
)

create_branch = HttpTool(
    name="Create Branch",
    description=(
        "Create a new branch. First use Get Branch to get main's latest SHA, "
        "then create a branch from it. The ref must be 'refs/heads/<branch-name>'."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/git/refs",
    method="POST",
    body=JsonBody(schema={"ref": "string", "sha": "string"}),
    auth=BearerToken(env="GITHUB_TOKEN"),
)

create_or_update_file = HttpTool(
    name="Create Or Update File",
    description=(
        "Create or update a file on a specific branch. "
        "Content must be base64-encoded. Include 'branch' in the body to target "
        "a non-default branch. Include 'sha' only when updating an existing file."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="PUT",
    params={
        "filepath": Param(description="Path to the file, e.g. agents/galadriel.toml"),
    },
    body=JsonBody(schema={
        "message": "string",
        "content": "string",
        "branch": "string",
        "sha": "string",
    }),
    auth=BearerToken(env="GITHUB_TOKEN"),
)

create_pull_request = HttpTool(
    name="Create Pull Request",
    description=(
        "Create a pull request. Provide title, body, head (your branch name), "
        "and base (usually 'main')."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/pulls",
    method="POST",
    body=JsonBody(schema={
        "title": "string",
        "body": "string",
        "head": "string",
        "base": "string",
    }),
    auth=BearerToken(env="GITHUB_TOKEN"),
)
