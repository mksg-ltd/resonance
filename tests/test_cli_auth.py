"""Interactive CLI credential prompting behavior."""

from io import StringIO

import pytest

from resonance.cli_auth import prompt_navidrome_credentials
from resonance.errors import ApplicationError

PASSWORD = "private-test-secret"  # noqa: S105 -- test credential fixture


class TTYInput(StringIO):
    def isatty(self):
        return True


def test_prompt_reads_username_and_masked_password(monkeypatch):
    monkeypatch.setattr("sys.stdin", TTYInput("ignored\n"))
    monkeypatch.setattr("builtins.input", lambda _prompt: "listener")
    monkeypatch.setattr("getpass.getpass", lambda _prompt: PASSWORD)

    credentials = prompt_navidrome_credentials()

    assert credentials.username == "listener"
    assert credentials.password == PASSWORD
    assert PASSWORD not in repr(credentials)


def test_noninteractive_prompt_fails_without_reading_password(monkeypatch):
    monkeypatch.setattr("sys.stdin", StringIO("listener\n"))
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("input should not be read"))

    with pytest.raises(ApplicationError) as error:
        prompt_navidrome_credentials()

    assert error.value.code == "credentials_required"
