from __future__ import annotations

from pathlib import Path

import pytest

from hexmind.desktop import install_desktop_entry


def test_installs_under_xdg_data_home_and_copies_packaged_icon(tmp_path, monkeypatch):
    data_home = tmp_path / "xdg data"
    executable = tmp_path / "bin with spaces" / "hexmind-gui"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr("hexmind.desktop.shutil.which", lambda _command: str(executable))

    desktop_path = install_desktop_entry(home=tmp_path / "home")

    assert desktop_path == data_home / "applications" / "hexmind-gui.desktop"
    content = desktop_path.read_text()
    assert f'Exec="{executable.resolve()}"' in content
    assert "Icon=hexmind" in content
    icon_path = data_home / "icons" / "hicolor" / "scalable" / "apps" / "hexmind.svg"
    packaged_icon = Path(__file__).parents[1] / "hexmind" / "hexmind.svg"
    assert icon_path.read_bytes() == packaged_icon.read_bytes()


def test_uses_injected_home_when_xdg_data_home_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("hexmind.desktop.shutil.which", lambda _command: "/usr/bin/hexmind-gui")

    path = install_desktop_entry(home=tmp_path)

    assert path == tmp_path / ".local" / "share" / "applications" / "hexmind-gui.desktop"


def test_escapes_desktop_exec_paths_and_accepts_injected_data_home(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    data_home = tmp_path / "data"
    executable = '/opt/Hexmind $ ` " \\ %/hexmind-gui'

    desktop_path = install_desktop_entry(data_home=data_home, executable=executable)

    expected = r'Exec="/opt/Hexmind \$ \` \" \\ %%/hexmind-gui"'
    assert expected in desktop_path.read_text()


def test_missing_gui_executable_fails_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr("hexmind.desktop.shutil.which", lambda _command: None)

    with pytest.raises(FileNotFoundError, match="hexmind-gui.*not found on PATH"):
        install_desktop_entry(home=tmp_path)
