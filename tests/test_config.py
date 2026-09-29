from pathlib import Path

from hexmind import config


def test_load_config_missing_file_returns_empty_dict(tmp_path):
    missing = tmp_path / "missing.toml"
    assert config.load_config(missing) == {}


def test_load_config_invalid_toml_returns_empty_dict(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("this is [not valid toml = = =")
    assert config.load_config(bad) == {}


def test_save_and_load_section_round_trip(tmp_path):
    p = tmp_path / "config.toml"
    room_data = {
        "lead": "claude",
        "members": ["claude", "agy"],
        "audit": True,
        "theme": "measured-dark",
    }
    config.save_section("room", room_data, p)
    loaded = config.load_config(p)
    assert loaded.get("room") == room_data


def test_save_section_preserves_other_sections(tmp_path):
    p = tmp_path / "config.toml"
    config.save_section("server", {"host": "0.0.0.0", "port": 9000, "token": "secret"}, p)
    config.save_section("room", {"lead": "codex", "audit": False}, p)
    config.save_section("notifications", {"phone_buzz": True, "threshold_seconds": 45}, p)
    config.save_nicknames({"claude": "Rex"}, p)

    loaded = config.load_config(p)
    assert loaded["server"]["host"] == "0.0.0.0"
    assert loaded["server"]["port"] == 9000
    assert loaded["server"]["token"] == "secret"
    assert loaded["room"]["lead"] == "codex"
    assert loaded["room"]["audit"] is False
    assert loaded["notifications"]["phone_buzz"] is True
    assert loaded["notifications"]["threshold_seconds"] == 45
    assert loaded["nicknames"]["claude"] == "Rex"
    assert config.load_nicknames(p) == {"claude": "Rex"}


def test_get_defaults_fallback_when_empty(tmp_path):
    p = tmp_path / "empty.toml"
    r = config.get_defaults(p)
    assert isinstance(r, config.RoomDefaults)
    assert r.lead == ""
    assert r.members == ["claude", "agy", "codex", "kimi"]
    assert r.audit is True
    assert r.theme == "measured-dark"

    s = config.get_server_defaults(p)
    assert isinstance(s, config.ServerDefaults)
    assert s.host == "127.0.0.1"
    assert s.port == 8765
    assert s.token == ""

    n = config.get_notification_defaults(p)
    assert isinstance(n, config.NotificationDefaults)
    assert n.phone_buzz is False
    assert n.threshold_seconds == 30


def test_get_defaults_populated(tmp_path):
    p = tmp_path / "config.toml"
    config.save_section("room", {"lead": "nemotron-ultra", "members": ["nemotron-ultra", "big-pickle"], "audit": False, "theme": "measured-sublime"}, p)
    config.save_section("server", {"host": "192.168.1.5", "port": 8888, "token": "tok123"}, p)
    config.save_section("notifications", {"phone_buzz": True, "threshold_seconds": 60}, p)

    r = config.get_defaults(p)
    assert r.lead == "nemotron-ultra"
    assert r.members == ["nemotron-ultra", "big-pickle"]
    assert r.audit is False
    assert r.theme == "measured-sublime"

    s = config.get_server_defaults(p)
    assert s.host == "192.168.1.5"
    assert s.port == 8888
    assert s.token == "tok123"

    n = config.get_notification_defaults(p)
    assert n.phone_buzz is True
    assert n.threshold_seconds == 60
