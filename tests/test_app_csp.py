# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE reads the page files (no browser) and checks the
#   security policy in app/ui/index.html, and that no page file hides code
#   in text the policy would block
#   read next → tests/test_app_preferences.py
#
# LEARN: why test text files with Python
#   the policy only protects if it stays strict; one careless edit
#   (adding 'unsafe-inline') would quietly switch the main protection off
#   → this test fails loudly instead (industry term: "regression test")
import re
from pathlib import Path

from app.paths import APP_DIR, UI_DIR

INDEX_FILE = UI_DIR / "index.html"
# finds the content="…" of the Content-Security-Policy meta tag
POLICY_PATTERN = re.compile(
    r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', re.IGNORECASE
)
# an HTML event attribute like onerror="…" or onclick='…' (code hidden in text)
INLINE_HANDLER_PATTERN = re.compile(r"<[^>]*\son[a-z]+\s*=", re.IGNORECASE)
# a <script> tag that has code inside it instead of a src="…" file
INLINE_SCRIPT_PATTERN = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)


def read_policy_directives() -> dict[str, list[str]]:
    # "script-src 'self' blob:; img-src 'self'" →
    # {"script-src": ["'self'", "blob:"], "img-src": ["'self'"]}
    match = POLICY_PATTERN.search(INDEX_FILE.read_text("utf-8"))
    assert match, "index.html has no Content-Security-Policy"
    directives = {}
    for part in match.group(1).split(";"):
        words = part.split()
        if words:
            directives[words[0]] = words[1:]

    return directives


def list_page_files() -> list[Path]:
    # every .html and .js the app ships (shell + every tool's ui folder)
    return sorted([*APP_DIR.rglob("*.html"), *APP_DIR.rglob("*.js")])


class TestAppCspPolicy:
    def test_app_csp_policy_blocks_inline_scripts(self) -> None:
        script_sources = read_policy_directives()["script-src"]

        assert "'unsafe-inline'" not in script_sources
        assert "*" not in script_sources

    def test_app_csp_policy_blocks_the_internet(self) -> None:
        directives = read_policy_directives()

        assert directives["connect-src"] == ["'self'"]
        assert directives["img-src"] == ["'self'", "data:"]
        assert directives["default-src"] == ["'self'"]

    def test_app_csp_policy_turns_off_plugins_and_forms(self) -> None:
        directives = read_policy_directives()

        assert directives["object-src"] == ["'none'"]
        assert directives["base-uri"] == ["'none'"]
        assert directives["form-action"] == ["'none'"]


class TestAppCspPageFiles:
    def test_app_csp_page_files_have_no_inline_event_handlers(self) -> None:
        offenders = [
            str(path.relative_to(APP_DIR))
            for path in list_page_files()
            if INLINE_HANDLER_PATTERN.search(path.read_text("utf-8"))
        ]

        assert offenders == []

    def test_app_csp_page_files_have_no_inline_scripts(self) -> None:
        offenders = [
            str(path.relative_to(APP_DIR))
            for path in APP_DIR.rglob("*.html")
            if INLINE_SCRIPT_PATTERN.search(path.read_text("utf-8"))
        ]

        assert offenders == []

    def test_app_csp_page_files_patterns_catch_bad_code(self) -> None:
        # guard the guards: the patterns must really spot what they look for
        assert INLINE_HANDLER_PATTERN.search('<img src=x onerror="steal()">')
        assert INLINE_SCRIPT_PATTERN.search("<script>steal()</script>")
        assert not INLINE_SCRIPT_PATTERN.search('<script src="shell.js"></script>')
