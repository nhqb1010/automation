# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks daily_commit/__init__.py (DailyCommitTool): every page
#   action against a FAKE GitHub, with a fixed clock
#   read next → pyproject.toml
import base64
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr

from app.tools.daily_commit import DailyCommitTool
from app.tools.daily_commit.connection import (
    DailyCommitConnection,
    DailyCommitConnectionStore,
)
from app.tools.daily_commit.github_client import GitHubClient
from app.tools.daily_commit.template_sync import read_template_files
from tests.test_daily_commit_github_client import FakeGitHubServer

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
REPO = "/repos/me/notes"
REPO_ANSWER = {
    "full_name": "me/notes",
    "private": True,
    "html_url": "https://github.com/me/notes",
    "default_branch": "main",
}
EMPTY_REPO_HEAD = (409, {"message": "Git Repository is empty."})


def encode_file(text: str) -> dict[str, str]:
    # a "contents" answer for one file
    return {"content": base64.b64encode(text.encode()).decode(), "sha": "sha-1"}


def build_tool(server: FakeGitHubServer, connected: bool = True) -> DailyCommitTool:
    """
    LEARN: a DailyCommitTool wired to the fake GitHub
      dev-style connection (no Keychain), real GitHubClient, fake transport
    """
    store = DailyCommitConnectionStore(
        is_installed=False,
        dev_repository="me/notes" if connected else None,
        dev_token=SecretStr("tok") if connected else None,
    )

    def open_fake_client(connection: DailyCommitConnection) -> GitHubClient:
        return GitHubClient(
            repository=connection.repository,
            token=connection.token.get_secret_value(),
            transport=server,
        )

    return DailyCommitTool(
        connection_store=store, open_client=open_fake_client, read_clock=lambda: NOW
    )


def build_set_up_repo_replies() -> dict[tuple[str, str], tuple[int, Any]]:
    # a repo already set up: 2 posts, the workflow active, one run today
    template = read_template_files()
    return {
        ("GET", REPO): (200, REPO_ANSWER),
        ("GET", f"{REPO}/git/ref/heads/main"): (200, {"object": {"sha": "head1"}}),
        ("GET", f"{REPO}/contents/days?ref=main"): (200, [{"name": "2026"}]),
        ("GET", f"{REPO}/contents/days/2026?ref=main"): (
            200,
            [{"name": "11-02.md"}, {"name": "11-03.md"}],
        ),
        ("GET", f"{REPO}/actions/workflows/daily.yml"): (
            200,
            {"state": "active", "html_url": "https://github.com/w"},
        ),
        ("GET", f"{REPO}/actions/workflows/daily.yml/runs?per_page=100"): (
            200,
            {
                "workflow_runs": [
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "event": "schedule",
                        "created_at": "2026-11-03T03:00:00Z",
                        "run_started_at": "2026-11-03T03:00:02Z",
                        "updated_at": "2026-11-03T03:00:20Z",
                        "html_url": "https://github.com/run/1",
                    }
                ]
            },
        ),
        ("GET", f"{REPO}/contents/.github/workflows/daily.yml?ref=main"): (
            200,
            encode_file(template[".github/workflows/daily.yml"]),
        ),
        ("GET", f"{REPO}/contents/daily.py?ref=main"): (
            200,
            encode_file("old script\n"),
        ),
        ("GET", f"{REPO}/contents/content.txt?ref=main"): (
            200,
            encode_file("my lines\n"),
        ),
        # today's post file (read by the files step)
        ("GET", f"{REPO}/contents/days/2026/11-03.md?ref=main"): (
            200,
            encode_file("# Tue 3 Nov 2026\n"),
        ),
    }


class TestDailyCommitToolReadDailyCommitRepo:
    def test_daily_commit_tool_read_daily_commit_repo_not_connected(self) -> None:
        server = FakeGitHubServer({})

        section = build_tool(server, connected=False).read_daily_commit_repo()

        assert section.connection.source == "none"
        assert section.repo is None
        assert section.problem is None
        assert server.requests == []

    def test_daily_commit_tool_read_daily_commit_repo_empty_repo(self) -> None:
        server = FakeGitHubServer(
            {
                ("GET", REPO): (200, REPO_ANSWER),
                ("GET", f"{REPO}/git/ref/heads/main"): EMPTY_REPO_HEAD,
            }
        )

        section = build_tool(server).read_daily_commit_repo()

        assert section.repo is not None
        assert section.repo.private is True
        assert section.repo.has_commits is False

    def test_daily_commit_tool_read_daily_commit_repo_bad_token_is_a_problem(
        self,
    ) -> None:
        server = FakeGitHubServer(
            {("GET", REPO): (401, {"message": "Bad credentials"})}
        )

        section = build_tool(server).read_daily_commit_repo()

        assert section.repo is None
        assert section.problem is not None
        assert "Bad credentials" in section.problem


class TestDailyCommitToolReadDailyCommitPosts:
    def test_daily_commit_tool_read_daily_commit_posts_set_up_repo(self) -> None:
        server = FakeGitHubServer(build_set_up_repo_replies())

        section = build_tool(server).read_daily_commit_posts(
            branch="main", has_commits=True
        )

        assert section.today_posted is True
        assert section.current_streak == 2
        assert section.longest_streak == 2
        assert section.total_posts == 2
        assert len(section.calendar) == 84

    def test_daily_commit_tool_read_daily_commit_posts_empty_needs_no_calls(
        self,
    ) -> None:
        server = FakeGitHubServer({})

        section = build_tool(server, connected=False).read_daily_commit_posts()

        assert section.total_posts == 0
        assert len(section.calendar) == 84
        assert server.requests == []


class TestDailyCommitToolReadDailyCommitWorkflow:
    def test_daily_commit_tool_read_daily_commit_workflow_active(self) -> None:
        server = FakeGitHubServer(build_set_up_repo_replies())

        section = build_tool(server).read_daily_commit_workflow(is_private=True)

        assert section.workflow.state == "active"
        assert len(section.workflow.recent_runs) == 1
        assert section.minutes.used_minutes == 1

    def test_daily_commit_tool_read_daily_commit_workflow_missing(self) -> None:
        server = FakeGitHubServer({})

        section = build_tool(server).read_daily_commit_workflow(is_private=True)

        assert section.workflow.state == "missing"
        assert section.minutes.used_minutes == 0


class TestDailyCommitToolReadDailyCommitFiles:
    def test_daily_commit_tool_read_daily_commit_files_set_up_repo(self) -> None:
        server = FakeGitHubServer(build_set_up_repo_replies())

        section = build_tool(server).read_daily_commit_files(
            branch="main", has_commits=True
        )

        assert {file.path: file.status for file in section.files} == {
            ".github/workflows/daily.yml": "same",
            "daily.py": "changed",
            "content.txt": "kept",
        }
        # today is posted → the preview is tomorrow's line, from content.txt
        assert section.next_post.is_today is False
        assert section.next_post.line == "my lines"
        assert section.next_post.line_count == 1

    def test_daily_commit_tool_read_daily_commit_files_empty_repo(self) -> None:
        server = FakeGitHubServer({})

        section = build_tool(server).read_daily_commit_files(
            branch="main", has_commits=False
        )

        assert {file.status for file in section.files} == {"new"}
        assert section.next_post.is_today is True
        assert server.requests == []


class TestDailyCommitToolApplyTemplateSync:
    def test_daily_commit_tool_apply_template_sync_empty_repo_creates_each_file(
        self,
    ) -> None:
        replies = {
            ("GET", REPO): (200, REPO_ANSWER),
            ("GET", f"{REPO}/git/ref/heads/main"): EMPTY_REPO_HEAD,
        }
        for path in read_template_files():
            replies[("PUT", f"{REPO}/contents/{path}")] = (
                201,
                {"commit": {"html_url": "https://github.com/c/1"}},
            )

        server = FakeGitHubServer(replies)

        result = build_tool(server).apply_template_sync()

        puts = [request.url for request in server.requests if request.method == "PUT"]
        assert result.committed_paths == list(read_template_files())
        assert len(puts) == 3

    def test_daily_commit_tool_apply_template_sync_updates_in_one_commit(self) -> None:
        replies = build_set_up_repo_replies()
        replies[("GET", f"{REPO}/git/commits/head1")] = (200, {"tree": {"sha": "t1"}})
        replies[("POST", f"{REPO}/git/trees")] = (201, {"sha": "t2"})
        replies[("POST", f"{REPO}/git/commits")] = (
            201,
            {"sha": "c2", "html_url": "https://github.com/c/2"},
        )
        replies[("PATCH", f"{REPO}/git/refs/heads/main")] = (200, {})
        server = FakeGitHubServer(replies)

        result = build_tool(server).apply_template_sync()

        # only daily.py changed; the workflow is the same, content.txt is kept
        assert result.committed_paths == ["daily.py"]
        assert result.commit_url == "https://github.com/c/2"


class TestDailyCommitToolRunDailyCommitNow:
    def test_daily_commit_tool_run_daily_commit_now_cleans_message(self) -> None:
        replies = build_set_up_repo_replies()
        replies[("POST", f"{REPO}/actions/workflows/daily.yml/dispatches")] = (
            204,
            None,
        )
        server = FakeGitHubServer(replies)

        build_tool(server).run_daily_commit_now(message="  hello\n  world  ")

        dispatch = server.sent_json(len(server.requests) - 1)
        assert dispatch == {"ref": "main", "inputs": {"message": "hello world"}}

    def test_daily_commit_tool_run_daily_commit_now_not_connected_raises(self) -> None:
        with pytest.raises(RuntimeError, match="Not connected"):
            build_tool(FakeGitHubServer({}), connected=False).run_daily_commit_now()


class TestDailyCommitToolSetDailyCommitPaused:
    def test_daily_commit_tool_set_daily_commit_paused_disables_workflow(self) -> None:
        server = FakeGitHubServer(
            {("PUT", f"{REPO}/actions/workflows/daily.yml/disable"): (204, None)}
        )

        result = build_tool(server).set_daily_commit_paused(paused=True)

        assert server.requests[0].url.endswith("/disable")
        assert result.message.startswith("Paused")


class TestDailyCommitToolSaveContentFile:
    def test_daily_commit_tool_save_content_file_adds_final_newline(self) -> None:
        server = FakeGitHubServer(
            {
                ("PUT", f"{REPO}/contents/content.txt"): (
                    200,
                    {"commit": {"html_url": "https://github.com/c/3"}},
                )
            }
        )

        build_tool(server).save_content_file(text="a\nb\n\n\n", sha="sha-1")

        body = server.sent_json(0)
        assert base64.b64decode(body["content"]).decode() == "a\nb\n"
        assert body["sha"] == "sha-1"


class TestDailyCommitToolTestDailyCommitConnection:
    def test_daily_commit_tool_test_daily_commit_connection_not_connected(self) -> None:
        report = build_tool(
            FakeGitHubServer({}), connected=False
        ).test_daily_commit_connection()

        assert report.ok is False
        assert report.checks == [("Repo and token found", False)]

    def test_daily_commit_tool_test_daily_commit_connection_all_good(self) -> None:
        server = FakeGitHubServer(build_set_up_repo_replies())

        report = build_tool(server).test_daily_commit_connection()

        assert report.ok is True
        assert len(report.checks) == 3
