from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scientific_calculator.settings_store import DatabaseMigrationError, SettingsStore


def test_typed_settings_round_trip_and_reset(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.db")
    values = {"name": "Graphite", "scale": 125, "enabled": True}

    store.save(values)
    assert store.load() == values

    store.reset_defaults()
    assert store.load() is None
    assert store.load_history() == []


def test_state_replacement_is_atomic_at_the_public_store_boundary(tmp_path: Path):
    store = SettingsStore(tmp_path / "settings.db")
    store.save_state({"scale": 100}, [("1+1", "2")])
    store.save_state({"scale": 125, "skin": "Blue"}, [("2+2", "4")])

    assert store.load() == {"scale": 125, "skin": "Blue"}
    assert store.load_history() == [("2+2", "4")]


@pytest.mark.parametrize(
    "value",
    [1.5, [], {"nested": "value"}, None],
)
def test_unsupported_setting_types_are_rejected_before_writing(tmp_path: Path, value):
    store = SettingsStore(tmp_path / "settings.db")
    with pytest.raises(TypeError, match="Unsupported setting type"):
        store.save({"bad": value})
    assert store.load() is None


@pytest.mark.parametrize(
    "entries",
    ["not a list", [("only one",)], [("ok", 2)], [("x" * 4097, "ok")]],
)
def test_history_validation_rejects_non_lcd_data(tmp_path: Path, entries):
    store = SettingsStore(tmp_path / "settings.db")
    with pytest.raises((TypeError, ValueError)):
        store.save_history(entries)  # type: ignore[arg-type]


def test_invalid_or_unsupported_database_schema_is_reported_without_loading(tmp_path: Path):
    path = tmp_path / "settings.db"
    issues = []
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO meta (key, value) VALUES ('db_schema_version', 'bad')")
    connection.commit()
    connection.close()

    store = SettingsStore(path, lambda operation, error: issues.append((operation, error)))
    assert store.load() is None
    assert issues[0][0] == "load"
    assert isinstance(issues[0][1], DatabaseMigrationError)


def test_legacy_schema_is_migrated_and_invalid_rows_are_not_deserialized(tmp_path: Path):
    path = tmp_path / "settings.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO meta (key, value) VALUES ('schema_version', '1')")
    connection.commit()
    connection.close()

    store = SettingsStore(path)
    assert store.load() is None
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT value FROM meta WHERE key = 'db_schema_version'").fetchone() == ("3",)
    connection.execute("INSERT INTO settings (key, value_type, value_text) VALUES ('bad', 'pickle', 'payload')")
    connection.commit()
    connection.close()

    issues = []
    store = SettingsStore(path, lambda operation, error: issues.append((operation, error)))
    assert store.load() is None
    assert issues[0][0] == "load"


def test_malformed_history_rows_are_reported_and_not_returned(tmp_path: Path):
    path = tmp_path / "settings.db"
    issues = []
    store = SettingsStore(path, lambda operation, error: issues.append((operation, error)))
    store.save_history([("1+1", "2")])
    connection = sqlite3.connect(path)
    connection.execute("UPDATE calculation_history SET expression = ?", ("x" * 4097,))
    connection.commit()
    connection.close()

    assert store.load_history() is None
    assert issues[0][0] == "load history"


def test_v2_history_schema_gets_structured_columns_once(tmp_path: Path):
    path = tmp_path / "settings.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO meta (key, value) VALUES ('db_schema_version', '2')")
    connection.execute("CREATE TABLE calculation_history (position INTEGER PRIMARY KEY, expression TEXT NOT NULL, result TEXT NOT NULL)")
    connection.commit()
    connection.close()

    store = SettingsStore(path)
    assert store.load_history() == []
    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(calculation_history)")}
    connection.close()
    assert {"kind", "metadata"} <= columns
