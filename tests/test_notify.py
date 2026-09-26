import subprocess

from hexmind import notify as nt


class FakeRun:
    """Records kdeconnect-cli calls; `--list-available` returns the given device ids."""
    def __init__(self, devices="", fail_ping=(), raise_on=None):
        self.devices, self.fail_ping, self.raise_on, self.calls = devices, set(fail_ping), raise_on, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        if self.raise_on and self.raise_on in argv:
            raise subprocess.TimeoutExpired(argv, 5)
        if "--list-available" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout=self.devices, stderr="")
        dev = argv[argv.index("--device") + 1]
        return subprocess.CompletedProcess(argv, 1 if dev in self.fail_ping else 0, stdout=b"", stderr=b"")


def test_no_kdeconnect_is_a_silent_noop(monkeypatch):
    monkeypatch.setattr(nt.shutil, "which", lambda _: None)
    fake = FakeRun("abc\n")
    monkeypatch.setattr(nt.subprocess, "run", fake)
    assert nt.notify("Hexmind", "done") == 0 and fake.calls == []


def test_pings_every_available_device(monkeypatch):
    monkeypatch.setattr(nt.shutil, "which", lambda _: "/usr/bin/kdeconnect-cli")
    fake = FakeRun("dev1\n\ndev2\n", fail_ping={"dev2"})
    monkeypatch.setattr(nt.subprocess, "run", fake)
    assert nt.notify("Hexmind", "relay finished") == 1  # dev2's ping failed
    assert fake.calls[0] == ["/usr/bin/kdeconnect-cli", "--list-available", "--id-only"]
    assert fake.calls[1] == ["/usr/bin/kdeconnect-cli", "--device", "dev1", "--ping-msg", "Hexmind: relay finished"]
    assert len(fake.calls) == 3


def test_no_devices_or_hung_cli_never_raises(monkeypatch):
    monkeypatch.setattr(nt.shutil, "which", lambda _: "/usr/bin/kdeconnect-cli")
    monkeypatch.setattr(nt.subprocess, "run", FakeRun(""))
    assert nt.notify("x") == 0
    monkeypatch.setattr(nt.subprocess, "run", FakeRun("dev1\n", raise_on="--list-available"))
    assert nt.notify("x") == 0
    monkeypatch.setattr(nt.subprocess, "run", FakeRun("dev1\n", raise_on="--ping-msg"))
    assert nt.notify("x") == 0
