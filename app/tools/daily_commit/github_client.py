# LEARN: YOU ARE HERE
#   daily_commit/__init__.py (DailyCommitTool) ▶ THIS FILE talks to api.github.com
#   ▶ answers as plain dicts / small classes ▶ back to DailyCommitTool
#   read next → app/tools/daily_commit/connection.py
"""
A small GitHub REST API client, standard library only.

LEARN: REST API (industry term) = a website for programs instead of people
  every "thing" has an address, and the HTTP method says what to do with it

    GET    /repos/me/notes                 read the repo's details
    GET    /repos/me/notes/contents/x.txt  read one file
    PUT    /repos/me/notes/contents/x.txt  create / replace one file
    POST   /repos/me/notes/actions/…/dispatches   start the workflow

  the answer is JSON ≈ a Python dict as text
  status code → 200 OK · 201 created · 204 OK, nothing to say ·
    401 bad token · 403 not allowed · 404 not found (or no access) ·
    409 conflict (e.g. the repo is empty) · 422 invalid input

LEARN: every request carries the token in a header
  Authorization: Bearer <token>  → "this is me, with these permissions"
  the token never goes into a URL or a log line

LEARN: why urllib and not the popular "requests" package
  urllib ships with Python → nothing to install, nothing to bundle
"""

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"
# LEARN: GitHub asks every client to name its API version → stable answers
GITHUB_API_VERSION = "2022-11-28"
REQUEST_TIMEOUT_SECONDS = 15
# owner/name, e.g. nhqb1010/notes (letters, digits, - . _)
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
# a normal file in git (not executable, not a link)
GIT_FILE_MODE = "100644"
# statuses meaning "isn't there": not found, or the repo has no commits yet
NOT_FOUND_STATUSES = frozenset({404, 409})
# 400 and up = an error answer (4xx: our request, 5xx: GitHub's side)
FIRST_ERROR_STATUS = 400


class GitHubApiError(RuntimeError):
    """
    LEARN: GitHub said no (or couldn't be reached)

    status 0 → no answer at all (offline, timeout)
    message → GitHub's own words, e.g. "Bad credentials"
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub said: {message} (status {status})")
        self.status = status
        self.message = message


@dataclass(frozen=True)
class GitHubRequest:
    """LEARN: one HTTP request, as plain data (easy to check in tests)."""

    method: str
    url: str
    headers: dict[str, str]
    body: bytes | None


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    body: bytes


# LEARN: Callable[[A], B] = "a function that takes A and gives back B"
#   the client SENDS through this function; tests pass a fake one
#   → tests never touch the internet
#   industry term: "dependency injection" (the fake = a "test double")
type GitHubTransport = Callable[[GitHubRequest], GitHubResponse]


@dataclass(frozen=True)
class RemoteFile:
    """A file read from the repo: its text + its sha (version fingerprint)."""

    text: str
    sha: str


def send_github_request_with_urllib(request: GitHubRequest) -> GitHubResponse:
    """
    LEARN: the real sender (the default transport)

    called by → GitHubClient, for every request
    gives back → status + body, also for error statuses (4xx / 5xx)

    urlopen raises HTTPError for 4xx / 5xx → caught, turned into a response
      → one place (GitHubClient) decides what an error means
    URLError → no answer at all (offline, DNS, timeout) → status 0
    """
    urllib_request = urllib.request.Request(
        request.url, data=request.body, headers=request.headers, method=request.method
    )
    try:
        # LEARN: with … as reply → the connection is closed when done
        with urllib.request.urlopen(
            urllib_request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as reply:
            return GitHubResponse(status=reply.status, body=reply.read())

    except urllib.error.HTTPError as error:
        return GitHubResponse(status=error.code, body=error.read())

    except (urllib.error.URLError, TimeoutError) as error:
        raise GitHubApiError(status=0, message=f"couldn't reach GitHub ({error})")


def read_github_error_message(body: bytes) -> str:
    """
    LEARN: GitHub's error answers look like {"message": "Bad credentials", …}

    called by → GitHubClient._request_github_json, for status ≥ 400
    anything unreadable → a generic text instead of crashing
    """
    try:
        return str(json.loads(body).get("message", "unknown error"))
    except ValueError, AttributeError:
        return "unknown error"


class GitHubClient:
    """
    LEARN: one notes repo, reached with one token

    made by → DailyCommitTool (daily_commit/__init__.py), once per page action
    each method = one GitHub feature the Daily Commit page needs
    """

    def __init__(
        self,
        repository: str,
        token: str,
        transport: GitHubTransport = send_github_request_with_urllib,
    ) -> None:
        if not REPOSITORY_PATTERN.match(repository):
            raise ValueError(
                f"Repository must look like owner/name, got {repository!r}"
            )

        self.repository = repository
        self._token = token
        self._transport = transport

    # ---------- the one place requests are made ----------

    def _request_github_json(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        """
        LEARN: send one request, give back the JSON answer

        called by → every method below
        path → "/repos/me/notes/…" (added to https://api.github.com)
        gives back → the parsed JSON (dict / list), or None for 204
        status ≥ 400 → GitHubApiError (with GitHub's own message)

        json.dumps(dict).encode() → the dict as JSON text → bytes to send
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "bao-internal-apps",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        response = self._transport(
            GitHubRequest(
                method=method, url=GITHUB_API_URL + path, headers=headers, body=data
            )
        )
        if response.status >= FIRST_ERROR_STATUS:
            message = read_github_error_message(response.body)
            # 404 / 409 are often expected ("no file yet", "empty repo")
            #   → only DEBUG; real refusals (401, 403, 422, …) → WARNING
            level = (
                logging.DEBUG
                if response.status in NOT_FOUND_STATUSES
                else logging.WARNING
            )
            logger.log(
                level, f"GitHub refused {method} {path} {response.status=} {message=}"
            )
            raise GitHubApiError(status=response.status, message=message)

        if not response.body:
            return None

        return json.loads(response.body)

    def _repo_path(self, rest: str) -> str:
        # "/contents/x.txt" → "/repos/me/notes/contents/x.txt"
        return f"/repos/{self.repository}{rest}"

    # ---------- repo + files ----------

    def read_repository(self) -> dict[str, Any]:
        """
        called by → DailyCommitTool overview + Test connection
        gives back → name, private, html_url, default_branch, …
        """
        return self._request_github_json("GET", self._repo_path(""))

    def read_branch_head_sha(self, branch: str) -> str | None:
        """
        LEARN: the newest commit on a branch (its sha), or None

        sha (industry term) = git's 40-character fingerprint of a commit
        None → the repo has no commits yet (GitHub answers 409 "empty")
        called by → DailyCommitTool, to know if the repo is empty
        """
        try:
            ref = self._request_github_json(
                "GET", self._repo_path(f"/git/ref/heads/{branch}")
            )
        except GitHubApiError as error:
            if error.status in NOT_FOUND_STATUSES:
                return None

            raise

        return ref["object"]["sha"]

    def read_file(self, path: str, branch: str) -> RemoteFile | None:
        """
        LEARN: one file's text, or None if it isn't there

        called by → template sync (compare), content editor (open)
        GitHub sends file content as base64 = binary data written with
          plain letters only (safe inside JSON); b64decode turns it back
        quote(path) → makes spaces etc. safe for a URL ("/" stays)
        """
        quoted = urllib.parse.quote(path)
        try:
            answer = self._request_github_json(
                "GET", self._repo_path(f"/contents/{quoted}?ref={branch}")
            )
        except GitHubApiError as error:
            if error.status in NOT_FOUND_STATUSES:
                return None

            raise

        text = base64.b64decode(answer["content"]).decode("utf-8")
        return RemoteFile(text=text, sha=answer["sha"])

    def list_folder_names(self, path: str, branch: str) -> list[str]:
        """
        LEARN: the names inside one repo folder ([] if it doesn't exist)

        called by → DailyCommitTool, to find posted days (days/2026 → 11-03.md, …)
        """
        quoted = urllib.parse.quote(path)
        try:
            answer = self._request_github_json(
                "GET", self._repo_path(f"/contents/{quoted}?ref={branch}")
            )
        except GitHubApiError as error:
            if error.status in NOT_FOUND_STATUSES:
                return []

            raise

        # a file at that path (not a folder) → a dict, not a list
        if not isinstance(answer, list):
            return []

        return [entry["name"] for entry in answer]

    def write_file(
        self, path: str, text: str, message: str, sha: str | None
    ) -> str | None:
        """
        LEARN: create or replace ONE file = one commit

        called by → content editor (save), and set up of an EMPTY repo
        sha → the version you edited; None → a new file
          GitHub refuses (409) if the file changed since → nothing lost
        gives back → the commit's web address
        """
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha

        quoted = urllib.parse.quote(path)
        answer = self._request_github_json(
            "PUT", self._repo_path(f"/contents/{quoted}"), body
        )
        return answer["commit"].get("html_url")

    def commit_files(
        self, files: dict[str, str], message: str, branch: str, head_sha: str
    ) -> str:
        """
        LEARN: several files in ONE commit (the "Git Data" API)

        called by → template sync, when the repo already has commits
        gives back → the new commit's web address

        a commit, in git's own terms:
          blob   = one file's content
          tree   = a folder listing: path → blob
          commit = a tree + message + parent commit
          ref    = a branch name pointing at its newest commit

          1. read the head commit → its tree
          2. new tree = old tree + our files ("base_tree" keeps the rest)
          3. new commit → that tree, parent = the head commit
          4. move the branch to the new commit
             force=False → refused if someone pushed meanwhile (no lost work)
        """
        head_commit = self._request_github_json(
            "GET", self._repo_path(f"/git/commits/{head_sha}")
        )
        tree = self._request_github_json(
            "POST",
            self._repo_path("/git/trees"),
            {
                "base_tree": head_commit["tree"]["sha"],
                "tree": [
                    {
                        "path": path,
                        "mode": GIT_FILE_MODE,
                        "type": "blob",
                        "content": text,
                    }
                    for path, text in files.items()
                ],
            },
        )
        commit = self._request_github_json(
            "POST",
            self._repo_path("/git/commits"),
            {"message": message, "tree": tree["sha"], "parents": [head_sha]},
        )
        self._request_github_json(
            "PATCH",
            self._repo_path(f"/git/refs/heads/{branch}"),
            {"sha": commit["sha"], "force": False},
        )
        return commit["html_url"]

    # ---------- the workflow (GitHub Actions) ----------

    def read_workflow(self, file_name: str) -> dict[str, Any] | None:
        """
        LEARN: the workflow's details, or None if GitHub doesn't know it

        state → "active", "disabled_manually", …
        called by → DailyCommitTool overview
        """
        try:
            return self._request_github_json(
                "GET", self._repo_path(f"/actions/workflows/{file_name}")
            )
        except GitHubApiError as error:
            if error.status in NOT_FOUND_STATUSES:
                return None

            raise

    def set_workflow_enabled(self, file_name: str, enabled: bool) -> None:
        """
        LEARN: Pause / Resume = GitHub's own disable / enable switch

        paused → the schedule stops; the file and history stay as they are
        called by → DailyCommitTool, the Pause / Resume button
        """
        switch = "enable" if enabled else "disable"
        self._request_github_json(
            "PUT", self._repo_path(f"/actions/workflows/{file_name}/{switch}")
        )

    def start_workflow_run(self, file_name: str, branch: str, message: str) -> None:
        """
        LEARN: [ Run now ] = the workflow_dispatch trigger in daily.yml

        inputs → the small form in daily.yml ("message"; "" → random line)
        GitHub answers 204 at once; the run itself starts a few seconds later
        """
        self._request_github_json(
            "POST",
            self._repo_path(f"/actions/workflows/{file_name}/dispatches"),
            {"ref": branch, "inputs": {"message": message}},
        )

    def list_workflow_runs(self, file_name: str, per_page: int = 100) -> list[dict]:
        """
        LEARN: the newest runs first (up to per_page)

        called by → DailyCommitTool: recent runs list + minutes estimate
        """
        answer = self._request_github_json(
            "GET",
            self._repo_path(f"/actions/workflows/{file_name}/runs?per_page={per_page}"),
        )
        return answer.get("workflow_runs", [])
