"""User preferences per tool, and the description the Settings page is built from."""

import logging
import typing
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from app.state import StateStore, build_model_leniently
from app.tools.base import Tool, UnknownToolActionError

logger = logging.getLogger(__name__)


class SettingsField(BaseModel):
    name: str
    title: str
    description: str | None
    choices: list[Any]
    unit: str | None
    value: Any


class SettingsSection(BaseModel):
    tool_id: str
    tool_name: str
    fields: list[SettingsField]


class InvalidPreferenceError(ValueError):
    """A preference value or field the tool does not accept."""


def read_field_extra(field: FieldInfo, key: str) -> Any:
    extra = field.json_schema_extra
    return extra.get(key) if isinstance(extra, dict) else None


def list_field_choices(field: FieldInfo) -> list[Any]:
    # LEARN: for Literal[1, 2, 5, 10], get_args returns (1, 2, 5, 10): the
    # choices the Settings page shows as buttons. A bool becomes on and off.
    if typing.get_origin(field.annotation) is Literal:
        return list(typing.get_args(field.annotation))
    if field.annotation is bool:
        return [False, True]

    return []


def describe_settings_section(tool: Tool, values: BaseModel) -> SettingsSection:
    return SettingsSection(
        tool_id=tool.info.id,
        tool_name=tool.info.name,
        fields=[
            SettingsField(
                name=name,
                title=field.title or name.replace("_", " ").capitalize(),
                description=field.description,
                choices=list_field_choices(field),
                unit=read_field_extra(field, "unit"),
                value=getattr(values, name),
            )
            for name, field in tool.settings_model.model_fields.items()
            if not read_field_extra(field, "hidden")
        ],
    )


class PreferencesService:
    """Reads, validates and saves each tool's preferences."""

    def __init__(self, store: StateStore, tools: list[Tool]) -> None:
        self._store = store
        self._tools = {tool.info.id: tool for tool in tools}

    def read_tool_preferences(self, tool_id: str) -> BaseModel:
        tool = self._find_tool(tool_id)
        raw = self._store.read_tool_preferences_raw(tool_id)
        return build_model_leniently(tool.settings_model, raw)

    def update_tool_preference(self, tool_id: str, field: str, value: Any) -> BaseModel:
        tool = self._find_tool(tool_id)
        if field not in tool.settings_model.model_fields:
            raise InvalidPreferenceError(f"{tool_id} has no setting {field!r}")

        current = self.read_tool_preferences(tool_id).model_dump()
        try:
            updated = tool.settings_model.model_validate({**current, field: value})
        except ValidationError as error:
            raise InvalidPreferenceError(
                f"Invalid value for {tool_id}.{field}"
            ) from error

        self._store.save_tool_preferences_raw(tool_id, updated.model_dump(mode="json"))
        logger.info(f"Preference changed {tool_id=} {field=} {value=}")
        return updated

    def reset_tool_preferences(self, tool_id: str) -> BaseModel:
        tool = self._find_tool(tool_id)
        defaults = tool.settings_model()
        self._store.save_tool_preferences_raw(tool_id, defaults.model_dump(mode="json"))
        logger.info(f"Preferences reset to defaults {tool_id=}")
        return defaults

    def describe_settings_sections(self) -> list[SettingsSection]:
        sections = [
            describe_settings_section(tool, self.read_tool_preferences(tool_id))
            for tool_id, tool in self._tools.items()
        ]
        return [section for section in sections if section.fields]

    def _find_tool(self, tool_id: str) -> Tool:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise UnknownToolActionError(f"Unknown tool {tool_id!r}")

        return tool
