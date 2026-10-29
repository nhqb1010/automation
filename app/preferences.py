# LEARN: YOU ARE HERE
#   bridge.py (Settings page clicks) ▶ THIS FILE checks + saves each tool's
#   settings ▶ state.py writes them to state.json
#   read next → app/bridge.py
"""
User preferences per tool, and the description the Settings page is built from.

LEARN: the Settings page is built FROM the tool's settings model

  tool's settings model (pydantic)        Settings page
  ┌───────────────────────────────┐       ┌──────────────────────────┐
  │ refresh: Literal[1, 2, 5]     │ ────▶ │ Refresh   [1] [2] [5]    │
  │ show_gpu: bool                │ ────▶ │ Show GPU  [off] [on]     │
  └───────────────────────────────┘       └──────────────────────────┘

  add a field to the model → a new row appears; no page code to write
  industry term: "schema-driven UI"
"""

import logging

# LEARN: typing = helpers to look INSIDE type hints while the app runs
import typing

# LEARN: Literal[1, 2, 5] = "only exactly one of these values is allowed"
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

# LEARN: FieldInfo = pydantic's description of one model field
#   (its type, title, description, extra info)
from pydantic.fields import FieldInfo

from app.state import StateStore, build_model_leniently
from app.tools.base import Tool, UnknownToolActionError

logger = logging.getLogger(__name__)


class SettingsField(BaseModel):
    """
    LEARN: one row on the Settings page

    built by → describe_settings_section
    sent to → settings.js, which draws the row
    """

    name: str
    title: str
    description: str | None
    # the buttons to show (empty → no buttons)
    choices: list[Any]
    # e.g. "s" → buttons read "1 s", "2 s"
    unit: str | None
    # the value saved right now (that button is highlighted)
    value: Any


class SettingsSection(BaseModel):
    """LEARN: one tool's block on the Settings page (a title + its rows)."""

    tool_id: str
    tool_name: str
    fields: list[SettingsField]


class InvalidPreferenceError(ValueError):
    """A preference value or field the tool does not accept."""


def read_field_extra(field: FieldInfo, key: str) -> Any:
    """
    LEARN: read one extra tag a tool put on a field

    called by → describe_settings_section ("unit", "hidden")
    gives back → the tag's value, or None if missing

    the tool writes: Field(…, json_schema_extra={"unit": "s"})
    """
    extra = field.json_schema_extra
    # LEARN: "a if condition else b" = one-line if / else
    #   same as: if isinstance(…): return extra.get(key) / else: return None
    return extra.get(key) if isinstance(extra, dict) else None


def list_field_choices(field: FieldInfo) -> list[Any]:
    """
    LEARN: which buttons a field gets

    called by → describe_settings_section
    gives back → the allowed values, in order

      Literal[1, 2, 5, 10] → [1, 2, 5, 10]
      bool                 → [False, True]   (off / on)
      anything else        → []              (no buttons)
    """
    # LEARN: get_origin(Literal[1, 2]) → Literal  (the "outer" type)
    #   get_args(Literal[1, 2]) → (1, 2)          (what's inside the [ ])
    if typing.get_origin(field.annotation) is Literal:
        return list(typing.get_args(field.annotation))
    if field.annotation is bool:
        return [False, True]

    return []


def describe_settings_section(tool: Tool, values: BaseModel) -> SettingsSection:
    """
    LEARN: turn one tool's settings model into a Settings page block

    called by → PreferencesService.describe_settings_sections
    gives back → SettingsSection ▶ bridge ▶ settings.js draws it

    fields tagged "hidden" are skipped (kept, but not shown on the page)
    """
    return SettingsSection(
        tool_id=tool.info.id,
        tool_name=tool.info.name,
        # LEARN: list comprehension = a for-loop that builds a list
        #   same as:
        #     fields = []
        #     for name, field in ….model_fields.items():
        #         if not hidden: fields.append(SettingsField(…))
        fields=[
            SettingsField(
                name=name,
                # no title given → "refresh_interval" becomes "Refresh interval"
                title=field.title or name.replace("_", " ").capitalize(),
                description=field.description,
                choices=list_field_choices(field),
                unit=read_field_extra(field, "unit"),
                # getattr(values, "x") = values.x, with the name as text
                value=getattr(values, name),
            )
            for name, field in tool.settings_model.model_fields.items()
            if not read_field_extra(field, "hidden")
        ],
    )


class PreferencesService:
    """
    LEARN: reads, checks and saves each tool's preferences

    made by → main.py, once at startup
    used by → bridge.py (Settings page), tools (their own settings)

    ≈ a Django form + model save: check the input, then store it
    industry term: "service layer" (logic between the API and the storage)
    """

    def __init__(self, store: StateStore, tools: list[Tool]) -> None:
        self._store = store
        # LEARN: dict comprehension = build a dict in one line
        #   same as: d = {} / for tool in tools: d[tool.info.id] = tool
        #   → find a tool by id fast: self._tools["system_monitor"]
        self._tools = {tool.info.id: tool for tool in tools}

    def read_tool_preferences(self, tool_id: str) -> BaseModel:
        """
        called by → bridge.py, tools, and the methods below
        gives back → the tool's settings model; bad saved values → defaults
        """
        tool = self._find_tool(tool_id)
        raw = self._store.read_tool_preferences_raw(tool_id)
        return build_model_leniently(tool.settings_model, raw)

    def update_tool_preference(self, tool_id: str, field: str, value: Any) -> BaseModel:
        """
        LEARN: change ONE setting (a button click on the Settings page)

        called by → bridge.py update_tool_preference
        gives back → the full updated settings ▶ page shows the new value
        bad field / value → InvalidPreferenceError, nothing is saved
        """
        tool = self._find_tool(tool_id)
        if field not in tool.settings_model.model_fields:
            raise InvalidPreferenceError(f"{tool_id} has no setting {field!r}")

        # model_dump() → the model as a plain dict
        current = self.read_tool_preferences(tool_id).model_dump()
        try:
            # {**current, field: value} = all current values, one replaced
            updated = tool.settings_model.model_validate({**current, field: value})
        except ValidationError as error:
            # LEARN: "raise … from error" → the new error keeps the original
            #   one attached, so the log shows both (industry: "exception chaining")
            raise InvalidPreferenceError(
                f"Invalid value for {tool_id}.{field}"
            ) from error

        # mode="json" → only JSON-safe values (ready to write to the file)
        self._store.save_tool_preferences_raw(tool_id, updated.model_dump(mode="json"))
        logger.info(f"Preference changed {tool_id=} {field=} {value=}")
        return updated

    def reset_tool_preferences(self, tool_id: str) -> BaseModel:
        """
        called by → bridge.py (the Settings page "Reset" button)
        gives back → the defaults, now also saved
        """
        tool = self._find_tool(tool_id)
        # calling the model class with nothing → every field at its default
        defaults = tool.settings_model()
        self._store.save_tool_preferences_raw(tool_id, defaults.model_dump(mode="json"))
        logger.info(f"Preferences reset to defaults {tool_id=}")
        return defaults

    def describe_settings_sections(self) -> list[SettingsSection]:
        """
        called by → bridge.py get_settings_sections (Settings page opens)
        gives back → one section per tool that has something to set
        """
        sections = [
            describe_settings_section(tool, self.read_tool_preferences(tool_id))
            for tool_id, tool in self._tools.items()
        ]
        # tools with no visible settings → no empty block on the page
        return [section for section in sections if section.fields]

    def _find_tool(self, tool_id: str) -> Tool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise UnknownToolActionError(f"Unknown tool {tool_id!r}")

        return tool
