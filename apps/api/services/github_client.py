"""Async GitHub REST API client for file retrieval, branching, commits, and PR creation."""

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubClientError(RuntimeError):
    """Raised when a GitHub API operation fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    """Non-blocking async GitHub client backed by `httpx.AsyncClient`."""

    def __init__(
        self,
        token: str,
        base_url: str = GITHUB_API_BASE,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN must be configured for GitHubClient")
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=20.0,
            transport=self._transport,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        async with self._client() as client:
            response = await client.request(method, path, params=params, json=json_body)
        if response.status_code >= 400:
            logger.error(
                "GitHub API request failed",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "body": response.text[:500],
                },
            )
            raise GitHubClientError(
                f"GitHub API {method} {path} failed with status "
                f"{response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        return response.json()  # type: ignore[no-any-return]

    async def fetch_file_contents(
        self,
        repo_owner: str,
        repo_name: str,
        file_path: str,
        ref: str = "main",
    ) -> str:
        """Fetch UTF-8 decoded file contents from a GitHub repository."""
        clean_path = file_path.lstrip("/")
        data = await self._request(
            "GET",
            f"/repos/{repo_owner}/{repo_name}/contents/{clean_path}",
            params={"ref": ref},
        )
        encoded = data.get("content")
        if not isinstance(encoded, str):
            raise GitHubClientError(
                f"File '{clean_path}' at ref '{ref}' did not return base64 content"
            )
        return base64.b64decode(encoded).decode("utf-8")

    async def create_branch(
        self,
        repo_owner: str,
        repo_name: str,
        branch_name: str,
        base_branch: str = "main",
    ) -> str:
        """Create a new branch from `base_branch` and return its HEAD commit SHA."""
        ref_data = await self._request(
            "GET",
            f"/repos/{repo_owner}/{repo_name}/git/ref/heads/{base_branch}",
        )
        obj = ref_data.get("object")
        if not isinstance(obj, dict) or not isinstance(obj.get("sha"), str):
            raise GitHubClientError(f"Unable to resolve base branch '{base_branch}' SHA")

        base_sha: str = obj["sha"]
        await self._request(
            "POST",
            f"/repos/{repo_owner}/{repo_name}/git/refs",
            json_body={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            },
        )
        return base_sha

    async def commit_patched_files(
        self,
        repo_owner: str,
        repo_name: str,
        branch_name: str,
        files: dict[str, str],
        commit_message: str,
    ) -> str:
        """Atomically commit one or more modified files onto `branch_name`.

        Returns the newly created commit SHA.
        """
        if not files:
            raise ValueError("files mapping must not be empty")
        if branch_name in {"main", "master"}:
            raise GitHubClientError("Direct commits to protected base branches are forbidden")

        ref_data = await self._request(
            "GET",
            f"/repos/{repo_owner}/{repo_name}/git/ref/heads/{branch_name}",
        )
        head_sha = ref_data["object"]["sha"]  # type: ignore[index]

        commit_data = await self._request(
            "GET",
            f"/repos/{repo_owner}/{repo_name}/git/commits/{head_sha}",
        )
        base_tree_sha = commit_data["tree"]["sha"]  # type: ignore[index]

        tree_entries: list[dict[str, str]] = []
        for path, content in files.items():
            blob_data = await self._request(
                "POST",
                f"/repos/{repo_owner}/{repo_name}/git/blobs",
                json_body={"content": content, "encoding": "utf-8"},
            )
            tree_entries.append(
                {
                    "path": path.lstrip("/"),
                    "mode": "100644",
                    "type": "blob",
                    "sha": str(blob_data["sha"]),
                }
            )

        new_tree = await self._request(
            "POST",
            f"/repos/{repo_owner}/{repo_name}/git/trees",
            json_body={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        new_commit = await self._request(
            "POST",
            f"/repos/{repo_owner}/{repo_name}/git/commits",
            json_body={
                "message": commit_message,
                "tree": str(new_tree["sha"]),
                "parents": [str(head_sha)],
            },
        )
        new_commit_sha = str(new_commit["sha"])
        await self._request(
            "PATCH",
            f"/repos/{repo_owner}/{repo_name}/git/refs/heads/{branch_name}",
            json_body={"sha": new_commit_sha},
        )
        return new_commit_sha

    async def open_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        """Open a GitHub Pull Request and return its HTML URL."""
        pr_data = await self._request(
            "POST",
            f"/repos/{repo_owner}/{repo_name}/pulls",
            json_body={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
        html_url = pr_data.get("html_url")
        if not isinstance(html_url, str):
            raise GitHubClientError("GitHub PR creation response missing html_url")
        return html_url
