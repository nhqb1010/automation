"""What every tool plugged into the hub provides."""

from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

VIEW_FILE_NAMES = ("view.html", "view.css", "view.js")


class UnknownToolActionError(LookupError):
    """The page asked a tool for an action it does not offer."""


@dataclass(frozen=True)
class ToolInfo:
    id: str
    name: str
    icon: str
    description: str


class ToolView(BaseModel):
    html: str
    css: str
    js: str


class NoToolSettings(BaseModel):
    """Settings model for tools that have nothing to configure."""


class Tool(ABC):
    """
    Base class for a tool in the hub.

    LEARN: a tool plugs in by declaring four things. The shell never needs to
    know anything else about it.

      info            ──▶ sidebar entry (name, icon)
      settings_model  ──▶ its section on the Settings page
      actions         ──▶ the only methods its page may call
      ui_dir          ──▶ folder holding view.html, view.css, view.js

    Comparable to a Django app: self contained, registered in one list.
    """

    info: ClassVar[ToolInfo]
    settings_model: ClassVar[type[BaseModel]] = NoToolSettings
    actions: ClassVar[frozenset[str]] = frozenset()
    ui_dir: ClassVar[Path]

    def run_tool_action(self, action: str, params: dict[str, Any]) -> BaseModel:
        """
        Run one of this tool's declared actions.

        LEARN: the allow list matters. Without it, the page could call any
        method on the tool, including private helpers.

        Args:
            action (str): the action name sent by the page.
            params (dict[str, Any]): keyword arguments for the action.
        Returns:
            BaseModel: the action's result, turned into JSON by the bridge.
        """
        if action not in self.actions:
            raise UnknownToolActionError(f"{self.info.id} has no action {action!r}")

        return getattr(self, action)(**params)

    def read_tool_view(self) -> ToolView:
        html, css, js = (
            (self.ui_dir / name).read_text(encoding="utf-8") for name in VIEW_FILE_NAMES
        )
        return ToolView(html=html, css=css, js=js)
