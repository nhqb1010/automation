# LEARN: YOU ARE HERE
#   every tool (e.g. System Monitor) is built on THIS FILE's Tool class
#   bridge.py ▶ tool.run_tool_action(...) / tool.read_tool_view() ▶ page
#   read next → app/tools/system_monitor/__init__.py
"""What every tool plugged into the hub provides."""

# LEARN: ABC = "abstract base class" = a parent class meant to be inherited
#   from, not used on its own
from abc import ABC
from dataclasses import dataclass
from pathlib import Path

# LEARN: Any = "any type at all"
#   ClassVar = this attribute belongs to the class, not to each object
from typing import Any, ClassVar

from pydantic import BaseModel

VIEW_FILE_NAMES = ("view.html", "view.css", "view.js")


# LEARN: LookupError = Python's built-in "couldn't find it" error family
class UnknownToolActionError(LookupError):
    """The page asked for a tool or action that does not exist."""


@dataclass(frozen=True)
class ToolInfo:
    """LEARN: what the sidebar shows for a tool (icon = a name from icons.js)."""

    id: str
    name: str
    icon: str
    description: str


class ToolView(BaseModel):
    """LEARN: the tool's page files, as text, sent to the shell to show."""

    html: str
    css: str
    js: str


class NoToolSettings(BaseModel):
    """Settings model for tools that have nothing to configure."""


class Tool(ABC):
    """
    LEARN: the parent class every tool inherits from

    a tool plugs in by filling FOUR things; the shell needs nothing else

      info            ──▶ sidebar entry (name, icon)
      settings_model  ──▶ its section on the Settings page
      actions         ──▶ the only methods its page may call
      ui_dir          ──▶ folder with view.html, view.css, view.js

    ≈ a Django app: self-contained, registered in one list (the registry)

    industry term: "plugin architecture"
    """

    # LEARN: "name: Type" with no value = "every tool must set this"
    #   "= NoToolSettings" = a default a tool may leave as is
    #   type[BaseModel] = a model CLASS (not an object made from it)
    info: ClassVar[ToolInfo]
    settings_model: ClassVar[type[BaseModel]] = NoToolSettings
    actions: ClassVar[frozenset[str]] = frozenset()
    ui_dir: ClassVar[Path]

    def run_tool_action(self, action: str, params: dict[str, Any]) -> BaseModel:
        """
        LEARN: run one action the page asked for

        called by → app/bridge.py, on every call from the page
        gives back → the action's result model ▶ bridge turns it into JSON

        allow list = only names in "actions" may run
          ✗ without it → the page could call ANY method, even private ones
          industry term: "allowlist"
        """
        if action not in self.actions:
            # !r → show the value with quotes, e.g. 'get_storage'
            raise UnknownToolActionError(f"{self.info.id} has no action {action!r}")

        # LEARN: getattr(obj, "name") = get obj.name, with the name as text
        #   → getattr(self, "get_storage") is self.get_storage
        # LEARN: **params = spread a dict into named arguments
        #   {"limit": 5} → method(limit=5)
        return getattr(self, action)(**params)

    def read_tool_view(self) -> ToolView:
        """
        LEARN: read the tool's three page files

        called by → app/bridge.py, the first time the tool is opened
        gives back → ToolView (html, css, js as text) ▶ shell.js shows them
        """
        # LEARN: generator expression ( … for … ) unpacked into 3 names
        #   same as:
        #     html = (self.ui_dir / "view.html").read_text(…)
        #     css  = (self.ui_dir / "view.css").read_text(…)
        #     js   = (self.ui_dir / "view.js").read_text(…)
        html, css, js = (
            (self.ui_dir / name).read_text(encoding="utf-8") for name in VIEW_FILE_NAMES
        )
        return ToolView(html=html, css=css, js=js)
