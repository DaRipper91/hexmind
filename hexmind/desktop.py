"""Install Hexmind's per-user XDG desktop launcher."""
from __future__ import annotations

import os
import shutil
import tempfile
from importlib.resources import files
from pathlib import Path


def _escape_exec_argument(argument: str) -> str:
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in argument):
        raise ValueError("Desktop Exec arguments cannot contain control characters")
    escaped = argument.replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        escaped = escaped.replace(char, "\\" + char)
    return f'"{escaped}"'


def _atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(contents)
        temporary_path.chmod(0o644)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def install_desktop_entry(
    *,
    home: str | Path | None = None,
    data_home: str | Path | None = None,
    executable: str | Path | None = None,
) -> Path:
    """Install the desktop entry and icon, returning the desktop entry's path.

    ``executable`` and the home/data paths are injectable to make installation
    deterministic in tests and usable by callers managing a non-default profile.
    """
    resolved_executable = str(executable) if executable is not None else shutil.which("hexmind-gui")
    if not resolved_executable:
        raise FileNotFoundError(
            "Cannot install the Hexmind desktop entry: 'hexmind-gui' was not found on PATH. "
            "Install Hexmind with its Qt extra first."
        )
    executable_path = str(Path(resolved_executable).resolve())
    exec_value = _escape_exec_argument(executable_path)

    if data_home is not None:
        data_root = Path(data_home)
    else:
        xdg_data_home = os.environ.get("XDG_DATA_HOME")
        user_home = Path(home) if home is not None else Path.home()
        data_root = Path(xdg_data_home) if xdg_data_home else user_home / ".local" / "share"

    desktop_path = data_root / "applications" / "hexmind-gui.desktop"
    icon_path = data_root / "icons" / "hicolor" / "scalable" / "apps" / "hexmind.svg"
    icon_contents = files("hexmind").joinpath("hexmind.svg").read_bytes()
    desktop_contents = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        "Name=Hexmind\n"
        "Comment=Multi-model agent team in one chat room\n"
        f"Exec={exec_value}\n"
        "Icon=hexmind\n"
        "Terminal=false\n"
        "Categories=Development;IDE;\n"
        "StartupNotify=true\n"
    ).encode()

    _atomic_write(icon_path, icon_contents)
    _atomic_write(desktop_path, desktop_contents)
    return desktop_path
