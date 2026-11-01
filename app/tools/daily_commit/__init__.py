# LEARN: YOU ARE HERE
#   tool registry makes this tool at startup ▶ page ▶ bridge.call("daily_commit", …)
#   ▶ THIS FILE ▶ connection.py (token) ▶ github_client.py (GitHub)
#   ▶ streak_stats.py / template_sync.py (the sums) ▶ models ▶ JSON ▶ page
#   read next → app/tools/daily_commit/models.py
"""
Daily Commit: one small commit a day, made by GitHub, controlled from here.

LEARN: the same plug-in shape as the other tools (see app/tools/base.py)
  info / settings_model / actions / ui_dir → sidebar, Settings, page

LEARN: the app is only the control panel
  GitHub runs the daily schedule (daily.yml) → the Mac can be off
  this tool reads what happened and offers the buttons

  page asks                  this file does
  read_daily_commit_repo / _posts / _workflow / _files ──▶ the page's 4 loading steps
  preview_template_sync ──▶  compare template vs repo → diffs (no writing)
  apply_template_sync   ──▶  commit the new / changed files (one commit)
  read_content_file     ──▶  content.txt for the editor
  save_content_file     ──▶  commit your edited content.txt
  run_daily_commit_now        ──▶  start the workflow now (optional message)
  set_daily_commit_paused     ──▶  GitHub's disable / enable switch
  test_daily_commit_connection / connect_… / disconnect_…  → the Connection card

LEARN: every action makes a fresh GitHubClient from the saved connection
  → Connect / Disconnect take effect at once, nothing is cached
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from app.tools.base import Tool, ToolInfo
from app.tools.daily_commit.connection import (
    DailyCommitConnection,
    DailyCommitConnectionStore,
)
from app.tools.daily_commit.github_client import GitHubApiError, GitHubClient
from app.tools.daily_commit.models import (
    ActionResult,
    ConnectionInfo,
    ConnectionReport,
    ContentFile,
    RepoInfo,
    FilesSection,
    PostsSection,
    RepoSection,
    WorkflowSection,
    TemplateSyncPlan,
    TemplateSyncResult,
    WorkflowInfo,
    WorkflowState,
)
from app.tools.daily_commit.streak_stats import (
    build_streak_calendar,
    count_current_streak,
    count_longest_streak,
    estimate_actions_minutes,
    read_posted_days,
    summarize_workflow_run,
)
from app.tools.daily_commit.template_sync import (
    TEMPLATE_PATHS,
    WORKFLOW_FILE_NAME,
    CONTENT_PATH,
    list_template_file_states,
    pick_files_to_commit,
    plan_template_sync,
    preview_next_post,
    read_template_files,
)

logger = logging.getLogger(__name__)

DAYS_FOLDER = "days"
RECENT_RUN_COUNT = 5
# a typed message becomes one line of a post → one line, kept short
MAX_MESSAGE_LENGTH = 280

# LEARN: type aliases for the two things tests replace
#   OpenGitHubClient → builds a client from a connection (tests: a fake)
#   ReadClock → "what time is it?" (tests: a fixed time)
type OpenGitHubClient = Callable[[DailyCommitConnection], GitHubClient]
type ReadClock = Callable[[], datetime]


class DailyCommitNotConnectedError(RuntimeError):
    """A GitHub action was asked for, but no repo + token is set."""


def open_github_client(connection: DailyCommitConnection) -> GitHubClient:
    # the real client; the token's text is only read here
    # called by → DailyCommitTool, at the start of each action
    return GitHubClient(
        repository=connection.repository, token=connection.token.get_secret_value()
    )


def read_utc_now() -> datetime:
    # UTC, the clock GitHub's contribution days use
    return datetime.now(UTC)


def clean_run_message(message: str) -> str:
    """
    LEARN: "  hello\\nworld  " → "hello world" (one line, ≤ 280 characters)

    called by → DailyCommitTool.run_daily_commit_now
    .split() with no argument → split on any spaces / line breaks
    " ".join(…) → glue the words back with single spaces
    """
    return " ".join(message.split())[:MAX_MESSAGE_LENGTH]


class DailyCommitTool(Tool):
    """
    LEARN: the Daily Commit tool, as the hub sees it

    made by → app/tools/__init__.py (the registry), once at startup
    called by → app/bridge.py, when the Daily Commit page asks for an action
    """

    info = ToolInfo(
        id="daily_commit",
        name="Daily Commit",
        icon="flame",
        description="One small commit a day, run by GitHub.",
    )
    actions = frozenset(
        {
            "read_daily_commit_repo",
            "read_daily_commit_posts",
            "read_daily_commit_workflow",
            "read_daily_commit_files",
            "preview_template_sync",
            "apply_template_sync",
            "read_content_file",
            "save_content_file",
            "run_daily_commit_now",
            "set_daily_commit_paused",
            "test_daily_commit_connection",
            "connect_daily_commit_repository",
            "disconnect_daily_commit_repository",
        }
    )
    ui_dir = Path(__file__).parent / "ui"

    def __init__(
        self,
        connection_store: DailyCommitConnectionStore,
        open_client: OpenGitHubClient = open_github_client,
        read_clock: ReadClock = read_utc_now,
    ) -> None:
        self._connection_store = connection_store
        self._open_client = open_client
        self._read_clock = read_clock

    # ---------- shared helpers (underscore → hidden from the page) ----------

    def _open_connected_client(self) -> GitHubClient:
        # called by → every GitHub action; not connected → a clear error
        connection = self._connection_store.read_daily_commit_connection()
        if connection is None:
            raise DailyCommitNotConnectedError("Not connected to a notes repo yet")

        return self._open_client(connection)

    def _read_repo_info(self, client: GitHubClient) -> RepoInfo:
        # the repo's details + whether it has any commit yet
        repo = client.read_repository()
        branch = repo.get("default_branch") or "main"
        return RepoInfo(
            full_name=repo["full_name"],
            private=bool(repo.get("private")),
            html_url=repo["html_url"],
            default_branch=branch,
            has_commits=client.read_branch_head_sha(branch) is not None,
        )

    def _read_repo_template_copies(
        self, client: GitHubClient, branch: str, has_commits: bool
    ) -> dict[str, str | None]:
        """
        LEARN: the repo's copy of each template file (None = missing)

        an empty repo has no files → skip the calls, all None
        """
        if not has_commits:
            return dict.fromkeys(TEMPLATE_PATHS)

        copies: dict[str, str | None] = {}
        for path in TEMPLATE_PATHS:
            remote = client.read_file(path=path, branch=branch)
            copies[path] = remote.text if remote else None

        return copies

    def _read_posted_days(self, client: GitHubClient, branch: str) -> set[date]:
        """
        LEARN: every day with a post file, from the days/ folder

          days/            → ["2026", "2027"]        (one call)
          days/2026/       → ["11-02.md", …]          (one call per year)
        """
        years = client.list_folder_names(path=DAYS_FOLDER, branch=branch)
        names_by_year = {
            year: client.list_folder_names(path=f"{DAYS_FOLDER}/{year}", branch=branch)
            for year in years
        }
        return read_posted_days(names_by_year)

    def _read_workflow_info(
        self, client: GitHubClient
    ) -> tuple[WorkflowInfo, list[dict]]:
        """
        LEARN: is daily.yml active / paused / missing + its runs

        gives back → (the info for the page, every run for the minutes sum)
        tuple[A, B] = a pair of values given back together
        """
        workflow = client.read_workflow(WORKFLOW_FILE_NAME)
        if workflow is None:
            return WorkflowInfo(state="missing", html_url=None, recent_runs=[]), []

        state: WorkflowState = (
            "active" if workflow.get("state") == "active" else "paused"
        )
        raw_runs = client.list_workflow_runs(WORKFLOW_FILE_NAME)
        recent = [summarize_workflow_run(run) for run in raw_runs[:RECENT_RUN_COUNT]]
        return (
            WorkflowInfo(
                state=state, html_url=workflow.get("html_url"), recent_runs=recent
            ),
            raw_runs,
        )

    # ---------- the page's four loading steps (sections) ----------
    #
    # LEARN: the page loads in 4 parts; the last 3 run AT THE SAME TIME
    #   (pywebview gives every page call its own thread)
    #
    #   1. read_daily_commit_repo ─┬─▶ 2. read_daily_commit_posts
    #      (branch, empty or not)  ├─▶ 3. read_daily_commit_workflow
    #                              └─▶ 4. read_daily_commit_files
    #
    #   → each part is a real step on the loading screen, and the page is
    #     ready sooner than with one long call doing everything in turn

    def read_daily_commit_repo(self) -> RepoSection:
        """
        LEARN: step 1: which repo, and can it be reached?

        called by → view.js, first, on open and on every refresh
        not connected → repo None, no problem
        GitHub said no (bad token, offline) → repo None + the reason
        """
        today = self._read_clock().date()
        info = self._connection_store.describe_daily_commit_connection()
        connection = self._connection_store.read_daily_commit_connection()
        if connection is None:
            return RepoSection(connection=info, repo=None, problem=None, today=today)

        try:
            repo = self._read_repo_info(self._open_client(connection))
        except (GitHubApiError, ValueError) as error:
            logger.warning(f"Daily Commit repo unreachable {error=}")
            return RepoSection(
                connection=info, repo=None, problem=str(error), today=today
            )

        return RepoSection(connection=info, repo=repo, problem=None, today=today)

    def read_daily_commit_posts(
        self, branch: str = "main", has_commits: bool = False
    ) -> PostsSection:
        """
        LEARN: step 2: posted days → today, streaks, the 12-week calendar

        branch / has_commits → from step 1 (an empty repo → no calls at all,
          an empty calendar; also used while not connected)
        """
        today = self._read_clock().date()
        posted: set[date] = set()
        if has_commits:
            posted = self._read_posted_days(
                client=self._open_connected_client(), branch=branch
            )

        return PostsSection(
            today_posted=today in posted,
            current_streak=count_current_streak(posted=posted, today=today),
            longest_streak=count_longest_streak(posted),
            total_posts=len(posted),
            calendar=build_streak_calendar(posted=posted, today=today),
        )

    def read_daily_commit_workflow(self, is_private: bool = True) -> WorkflowSection:
        """
        LEARN: step 3: workflow state, recent runs, Actions minutes

        is_private → from step 1 (public repos: minutes are free)
        """
        client = self._open_connected_client()
        workflow, raw_runs = self._read_workflow_info(client)
        runs = [summarize_workflow_run(run) for run in raw_runs]
        return WorkflowSection(
            workflow=workflow,
            minutes=estimate_actions_minutes(
                runs=runs, now=self._read_clock(), is_private=is_private
            ),
        )

    def read_daily_commit_files(
        self, branch: str = "main", has_commits: bool = False
    ) -> FilesSection:
        """
        LEARN: step 4: template files' status + the next post's line

        today's post file is checked here too (one small call), so this
        step doesn't have to wait for step 2
        """
        now = self._read_clock()
        client = self._open_connected_client()
        copies = self._read_repo_template_copies(
            client=client, branch=branch, has_commits=has_commits
        )
        template_files = read_template_files()
        plan = plan_template_sync(template_files=template_files, repo_files=copies)
        today_post = f"{DAYS_FOLDER}/{now:%Y}/{now:%m-%d}.md"
        today_posted = (
            has_commits and client.read_file(path=today_post, branch=branch) is not None
        )
        # the repo's content.txt, or the template's while it isn't there yet
        content_text = copies.get(CONTENT_PATH) or template_files[CONTENT_PATH]
        return FilesSection(
            files=list_template_file_states(plan),
            next_post=preview_next_post(
                content_text=content_text, now=now, today_posted=today_posted
            ),
        )

    # ---------- actions (the page may call these) ----------

    def preview_template_sync(self) -> TemplateSyncPlan:
        """
        LEARN: [ Set up / update repo ] step 1: show what WOULD change

        called by → view.js; nothing is written to GitHub here
        """
        client = self._open_connected_client()
        repo = self._read_repo_info(client)
        copies = self._read_repo_template_copies(
            client=client, branch=repo.default_branch, has_commits=repo.has_commits
        )
        return plan_template_sync(
            template_files=read_template_files(), repo_files=copies
        )

    def apply_template_sync(self) -> TemplateSyncResult:
        """
        LEARN: step 2, after you pressed [ Apply ]: commit the changes

        called by → view.js, only from the preview's confirm button
        the plan is worked out AGAIN here (the repo may have changed since
          the preview) → only what's still different gets committed

        empty repo  → one "create file" call per file (the first one makes
                      the repo's first commit; the Git Data API needs one)
        otherwise   → all files in ONE commit
        """
        client = self._open_connected_client()
        repo = self._read_repo_info(client)
        copies = self._read_repo_template_copies(
            client=client, branch=repo.default_branch, has_commits=repo.has_commits
        )
        template_files = read_template_files()
        plan = plan_template_sync(template_files=template_files, repo_files=copies)
        files = pick_files_to_commit(plan=plan, template_files=template_files)
        if not files:
            return TemplateSyncResult(committed_paths=[], commit_url=None)

        is_first_setup = all(copies.get(path) is None for path in files)
        message = (
            "daily commit: set up the workflow"
            if is_first_setup
            else "daily commit: update the workflow files"
        )
        head_sha = client.read_branch_head_sha(repo.default_branch)
        if head_sha is None:
            commit_url = None
            for path, text in files.items():
                commit_url = client.write_file(
                    path=path, text=text, message=message, sha=None
                )

        else:
            commit_url = client.commit_files(
                files=files,
                message=message,
                branch=repo.default_branch,
                head_sha=head_sha,
            )

        logger.info(f"Daily Commit template committed {list(files)=} {commit_url=}")
        return TemplateSyncResult(committed_paths=list(files), commit_url=commit_url)

    def read_content_file(self) -> ContentFile:
        """called by → view.js, [ Edit content ] ▶ the editor's text + sha."""
        client = self._open_connected_client()
        repo = self._read_repo_info(client)
        remote = client.read_file(path=CONTENT_PATH, branch=repo.default_branch)
        if remote is None:
            return ContentFile(text=read_template_files()[CONTENT_PATH], sha=None)

        return ContentFile(text=remote.text, sha=remote.sha)

    def save_content_file(self, text: str, sha: str | None = None) -> ActionResult:
        """
        LEARN: [ Save ] in the editor → one commit to content.txt

        sha → the version the editor opened; GitHub refuses the save if
          content.txt changed on GitHub meanwhile (nothing is overwritten)
        """
        client = self._open_connected_client()
        # always end with one line break (tidy file, clean diffs)
        cleaned = text.rstrip() + "\n"
        client.write_file(
            path=CONTENT_PATH,
            text=cleaned,
            message="daily commit: update the content list",
            sha=sha,
        )
        logger.info("Daily Commit content.txt saved")
        return ActionResult(message="Saved: the next post picks from the new list.")

    def run_daily_commit_now(self, message: str = "") -> ActionResult:
        """
        LEARN: [ Run now ] / [ Run with message ]

        GitHub starts the run a few seconds later; the page refreshes to
        show it. The message (if any) replaces today's random line.
        """
        client = self._open_connected_client()
        repo = self._read_repo_info(client)
        line = clean_run_message(message)
        client.start_workflow_run(
            file_name=WORKFLOW_FILE_NAME, branch=repo.default_branch, message=line
        )
        logger.info(f"Daily Commit run started {bool(line)=}")
        return ActionResult(message="Started: GitHub runs it in a few seconds.")

    def set_daily_commit_paused(self, paused: bool) -> ActionResult:
        """called by → view.js, [ Pause ] / [ Resume ] ▶ GitHub's switch."""
        client = self._open_connected_client()
        client.set_workflow_enabled(file_name=WORKFLOW_FILE_NAME, enabled=not paused)
        logger.info(f"Daily Commit workflow {paused=}")
        return ActionResult(
            message="Paused: no daily posts until you resume."
            if paused
            else "Resumed: the next post is at 10:00."
        )

    def test_daily_commit_connection(self) -> ConnectionReport:
        """
        LEARN: [ Test connection ] → a short checklist, nothing written

          ✓ connection set up      (repo + token found)
          ✓ repository reachable   (token can read it)
          ✓ Actions readable       (token has Actions permission)
        """
        checks: list[tuple[str, bool]] = []
        connection = self._connection_store.read_daily_commit_connection()
        checks.append(("Repo and token found", connection is not None))
        if connection is None:
            return ConnectionReport(ok=False, checks=checks)

        try:
            client = self._open_client(connection)
            repo = self._read_repo_info(client)
            visibility = "private" if repo.private else "public"
            checks.append((f"Repository reachable ({visibility})", True))
        except (GitHubApiError, ValueError) as error:
            checks.append((f"Repository reachable: {error}", False))
            return ConnectionReport(ok=False, checks=checks)

        try:
            client.read_workflow(WORKFLOW_FILE_NAME)
            checks.append(("Actions readable", True))
        except GitHubApiError as error:
            checks.append((f"Actions readable: {error}", False))

        return ConnectionReport(ok=all(ok for _, ok in checks), checks=checks)

    def connect_daily_commit_repository(
        self, repository: str, token: str
    ) -> ConnectionInfo:
        """
        LEARN: [ Connect ] (installed app) → save to the Keychain

        the token is typed into the page and comes straight here; it is
        never logged or sent back to the page
        """
        self._connection_store.save_daily_commit_connection(
            repository=repository, token=token
        )
        return self._connection_store.describe_daily_commit_connection()

    def disconnect_daily_commit_repository(self) -> ConnectionInfo:
        """
        LEARN: [ Disconnect ] (installed app) → remove from the Keychain

        GitHub keeps posting; only this app stops reading the repo
        """
        self._connection_store.forget_daily_commit_connection()
        return self._connection_store.describe_daily_commit_connection()
