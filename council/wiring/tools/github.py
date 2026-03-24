from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param


list_issues = HttpTool(
    name="List Issues",
    description="List open issues on the GitHub repository. Returns all open issues with their titles and details.",
    url="https://api.github.com/repos/{owner}/{repo}/issues?state=open",
    method="GET",
    auth=BearerToken(env="GITHUB_TOKEN"),
)

read_file = HttpTool(
    name="Read File",
    description=(
        "Read a single file from the GitHub repository. "
        "You MUST provide the file path. For example, to read README.md set filepath to 'README.md'. "
        "Only reads ONE file at a time. Do NOT use this to list directories."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="GET",
    params={"filepath": Param(description="The path to the file to read, e.g. README.md or docs/design.md")},
    auth=BearerToken(env="GITHUB_TOKEN"),
    headers={"Accept": "application/vnd.github.raw+json"},
)

create_issue = HttpTool(
    name="Create Issue",
    description=(
        'Create a new GitHub issue. You MUST provide a JSON body with "title" (required) '
        'and "body" (optional) fields.'
    ),
    url="https://api.github.com/repos/{owner}/{repo}/issues",
    method="POST",
    body=JsonBody(schema={"title": "string", "body": "string"}),
    auth=BearerToken(env="GITHUB_TOKEN"),
)
