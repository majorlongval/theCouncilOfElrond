from council.wiring.tools.models import BearerToken, HttpTool, Param

read_pr = HttpTool(
    name="Read PR",
    description=(
        "Read a pull request from the GitHub repository. "
        "Returns PR metadata including title, body, diff, and review status."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
    method="GET",
    params={"pr_number": Param(description="The PR number to read, e.g. 42")},
    auth=BearerToken(env="GITHUB_TOKEN"),
)

merge_pr = HttpTool(
    name="Merge PR",
    description="Merge a pull request. Only use after the user has approved the PR.",
    url="https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge",
    method="PUT",
    params={"pr_number": Param(description="The PR number to merge, e.g. 42")},
    auth=BearerToken(env="GITHUB_TOKEN"),
)
