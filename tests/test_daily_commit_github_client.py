# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/github_client.py against a FAKE GitHub
#   (a function that answers like GitHub would) → never the internet
#   read next → tests/test_daily_commit_connection.py
import base64
import json
from typing import Any

import pytest

from app.tools.daily_commit.github_client import (
    GITHUB_API_URL,
    GitHubApiError,
    GitHubClient,
    GitHubRequest,
    GitHubResponse,
    read_github_error_message,
)

NOT_FOUND = (404, {"message": "Not Found"})


class FakeGitHubServer:
    """
    LEARN: stands in for api.github.com

    replies → (method, path) → (status, JSON body); anything else → 404
    requests → every request the client sent, to check afterwards
    __call__ → the object can be called like a function (it IS the transport)
    """

    def __init__(self, replies: dict[tuple[str, str], tuple[int, Any]]) -> None:
        self.replies = replies
        self.requests: list[GitHubRequest] = []

    def __call__(self, request: GitHubRequest) -> GitHubResponse:
        self.requests.append(request)
        path = request.url.removeprefix(GITHUB_API_URL)
        status, body = self.replies.get((request.method, path), NOT_FOUND)
        return GitHubResponse(
            status=status, body=b"" if body is None else json.dumps(body).encode()
        )

    def sent_json(self, index: int) -> dict[str, Any]:
        # the JSON body of the request number "index"
        body = self.requests[index].body
        assert body is not None
        return json.loads(body)


def encode_file_content(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def build_client(server: FakeGitHubServer) -> GitHubClient:
    return GitHubClient(repository="me/notes", token="secret-token", transport=server)


class TestDailyCommitGithubClientSetup:
    def test_daily_commit_github_client_setup_rejects_bad_repository_name(self) -> None:
        with pytest.raises(ValueError, match="owner/name"):
            GitHubClient(
                repository="not a repo",
                token="t",
                transport=FakeGitHubServer({}),
            )

    def test_daily_commit_github_client_setup_sends_token_in_header_only(self) -> None:
        server = FakeGitHubServer({("GET", "/repos/me/notes"): (200, {"x": 1})})

        build_client(server).read_repository()

        request = server.requests[0]
        assert request.headers["Authorization"] == "Bearer secret-token"
        assert "secret-token" not in request.url


class TestDailyCommitGithubClientErrors:
    def test_daily_commit_github_client_errors_raise_with_github_message(self) -> None:
        server = FakeGitHubServer(
            {("GET", "/repos/me/notes"): (401, {"message": "Bad credentials"})}
        )

        with pytest.raises(GitHubApiError) as caught:
            build_client(server).read_repository()

        assert caught.value.status == 401
        assert caught.value.message == "Bad credentials"

    def test_daily_commit_github_client_errors_unreadable_body(self) -> None:
        assert read_github_error_message(b"<html>") == "unknown error"


class TestDailyCommitGithubClientFiles:
    def test_daily_commit_github_client_files_read_file_decodes_content(self) -> None:
        server = FakeGitHubServer(
            {
                ("GET", "/repos/me/notes/contents/content.txt?ref=main"): (
                    200,
                    {"content": encode_file_content("hello ✓\n"), "sha": "abc"},
                )
            }
        )

        remote = build_client(server).read_file(path="content.txt", branch="main")

        assert remote is not None
        assert remote.text == "hello ✓\n"
        assert remote.sha == "abc"

    def test_daily_commit_github_client_files_read_file_missing_is_none(self) -> None:
        server = FakeGitHubServer({})

        assert build_client(server).read_file(path="x.txt", branch="main") is None

    def test_daily_commit_github_client_files_list_folder_names(self) -> None:
        server = FakeGitHubServer(
            {
                ("GET", "/repos/me/notes/contents/days?ref=main"): (
                    200,
                    [{"name": "2025"}, {"name": "2026"}],
                )
            }
        )

        names = build_client(server).list_folder_names(path="days", branch="main")

        assert names == ["2025", "2026"]

    def test_daily_commit_github_client_files_empty_repo_head_is_none(self) -> None:
        server = FakeGitHubServer(
            {
                ("GET", "/repos/me/notes/git/ref/heads/main"): (
                    409,
                    {"message": "Git Repository is empty."},
                )
            }
        )

        assert build_client(server).read_branch_head_sha("main") is None

    def test_daily_commit_github_client_files_write_file_sends_base64_and_sha(
        self,
    ) -> None:
        server = FakeGitHubServer(
            {
                ("PUT", "/repos/me/notes/contents/content.txt"): (
                    200,
                    {"commit": {"html_url": "https://github.com/me/notes/commit/1"}},
                )
            }
        )

        url = build_client(server).write_file(
            path="content.txt", text="new\n", message="update", sha="old-sha"
        )

        body = server.sent_json(0)
        assert url == "https://github.com/me/notes/commit/1"
        assert base64.b64decode(body["content"]).decode() == "new\n"
        assert body["sha"] == "old-sha"

    def test_daily_commit_github_client_files_commit_files_in_one_commit(self) -> None:
        server = FakeGitHubServer(
            {
                ("GET", "/repos/me/notes/git/commits/head1"): (
                    200,
                    {"tree": {"sha": "tree1"}},
                ),
                ("POST", "/repos/me/notes/git/trees"): (200, {"sha": "tree2"}),
                ("POST", "/repos/me/notes/git/commits"): (
                    201,
                    {"sha": "commit2", "html_url": "https://github.com/c/2"},
                ),
                ("PATCH", "/repos/me/notes/git/refs/heads/main"): (200, {}),
            }
        )

        url = build_client(server).commit_files(
            files={"a.txt": "A", "b.txt": "B"},
            message="two files",
            branch="main",
            head_sha="head1",
        )

        tree_body = server.sent_json(1)
        commit_body = server.sent_json(2)
        ref_body = server.sent_json(3)
        assert url == "https://github.com/c/2"
        assert tree_body["base_tree"] == "tree1"
        assert [entry["path"] for entry in tree_body["tree"]] == ["a.txt", "b.txt"]
        assert commit_body["parents"] == ["head1"]
        assert ref_body == {"sha": "commit2", "force": False}


class TestDailyCommitGithubClientWorkflow:
    def test_daily_commit_github_client_workflow_missing_is_none(self) -> None:
        server = FakeGitHubServer({})

        assert build_client(server).read_workflow("daily.yml") is None

    def test_daily_commit_github_client_workflow_pause_uses_disable(self) -> None:
        server = FakeGitHubServer(
            {
                ("PUT", "/repos/me/notes/actions/workflows/daily.yml/disable"): (
                    204,
                    None,
                )
            }
        )

        build_client(server).set_workflow_enabled(file_name="daily.yml", enabled=False)

        assert server.requests[0].url.endswith("/daily.yml/disable")

    def test_daily_commit_github_client_workflow_start_run_sends_message(self) -> None:
        server = FakeGitHubServer(
            {
                ("POST", "/repos/me/notes/actions/workflows/daily.yml/dispatches"): (
                    204,
                    None,
                )
            }
        )

        build_client(server).start_workflow_run(
            file_name="daily.yml", branch="main", message="hi"
        )

        assert server.sent_json(0) == {"ref": "main", "inputs": {"message": "hi"}}

    def test_daily_commit_github_client_workflow_list_runs(self) -> None:
        server = FakeGitHubServer(
            {
                (
                    "GET",
                    "/repos/me/notes/actions/workflows/daily.yml/runs?per_page=100",
                ): (
                    200,
                    {"workflow_runs": [{"id": 1}, {"id": 2}]},
                )
            }
        )

        runs = build_client(server).list_workflow_runs("daily.yml")

        assert [run["id"] for run in runs] == [1, 2]
