# LEARN: YOU ARE HERE
#   pytest ▶ THIS FILE checks app/preferences.py (each tool's settings)
#   read next → tests/test_app_bridge.py
import pytest

from app.preferences import InvalidPreferenceError, PreferencesService
from app.state import StateStore
from app.tools.base import UnknownToolActionError
from app.tools.system_monitor import SystemMonitorSettings
from tests.conftest import DummyTool


class SystemMonitorSettingsOnlyTool(DummyTool):
    """A tool with the real System Monitor settings but no system readers."""

    settings_model = SystemMonitorSettings


# LEARN: a fixture in a test file → only this file can use it
#   it asks for state_store itself (fixtures can use other fixtures)
@pytest.fixture
def preferences(state_store: StateStore) -> PreferencesService:
    return PreferencesService(
        store=state_store, tools=[SystemMonitorSettingsOnlyTool()]
    )


class TestAppPreferencesReadToolPreferences:
    def test_app_preferences_read_defaults_when_nothing_saved(
        self, preferences: PreferencesService
    ) -> None:
        values = preferences.read_tool_preferences("dummy")

        assert values.refresh_interval_seconds == 2
        assert values.top_apps_count == 5

    def test_app_preferences_read_bad_saved_value_resets_that_field(
        self, preferences: PreferencesService, state_store: StateStore
    ) -> None:
        # 7 is not an allowed choice → reset; 10 is fine → kept
        state_store.save_tool_preferences_raw(
            "dummy", {"refresh_interval_seconds": 7, "top_apps_count": 10}
        )

        values = preferences.read_tool_preferences("dummy")

        assert values.refresh_interval_seconds == 2
        assert values.top_apps_count == 10

    def test_app_preferences_read_unknown_tool_rejected(
        self, preferences: PreferencesService
    ) -> None:
        with pytest.raises(UnknownToolActionError):
            preferences.read_tool_preferences("nope")


class TestAppPreferencesUpdateToolPreference:
    def test_app_preferences_update_valid_change_saved(
        self, preferences: PreferencesService, state_store: StateStore
    ) -> None:
        preferences.update_tool_preference(
            tool_id="dummy", field="refresh_interval_seconds", value=5
        )

        saved = state_store.read_tool_preferences_raw("dummy")
        assert saved["refresh_interval_seconds"] == 5
        assert preferences.read_tool_preferences("dummy").refresh_interval_seconds == 5

    def test_app_preferences_update_value_outside_choices_rejected(
        self, preferences: PreferencesService
    ) -> None:
        with pytest.raises(InvalidPreferenceError):
            preferences.update_tool_preference(
                tool_id="dummy", field="refresh_interval_seconds", value=7
            )

    def test_app_preferences_update_unknown_field_rejected(
        self, preferences: PreferencesService
    ) -> None:
        with pytest.raises(InvalidPreferenceError):
            preferences.update_tool_preference(
                tool_id="dummy", field="colour", value="red"
            )


class TestAppPreferencesResetToolPreferences:
    def test_app_preferences_reset_restores_defaults(
        self, preferences: PreferencesService
    ) -> None:
        preferences.update_tool_preference(
            tool_id="dummy", field="top_apps_count", value=10
        )

        preferences.reset_tool_preferences("dummy")

        assert preferences.read_tool_preferences("dummy").top_apps_count == 5


class TestAppPreferencesDescribeSettingsSections:
    def test_app_preferences_describe_lists_choices_and_hides_internal_fields(
        self, preferences: PreferencesService
    ) -> None:
        # LEARN: (section,) = a_list → unpack exactly ONE item
        #   fails if the list has 0 or 2+ items → also checks the count
        (section,) = preferences.describe_settings_sections()
        fields = {field.name: field for field in section.fields}

        assert set(fields) == {"refresh_interval_seconds", "top_apps_count"}
        assert fields["refresh_interval_seconds"].choices == [1, 2, 5, 10]
        assert fields["refresh_interval_seconds"].unit == "s"
        assert fields["top_apps_count"].value == 5
