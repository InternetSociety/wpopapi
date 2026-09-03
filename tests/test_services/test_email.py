import asyncio
import threading
from time import monotonic
from types import SimpleNamespace

import pytest

import app.services.email as email_module
from app.services.email import PasswordResetMailer


@pytest.mark.asyncio
async def test_password_reset_delivery_does_not_block_event_loop(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    def block_delivery(_recipient: str, _code: str) -> None:
        started.set()
        release.wait(timeout=1)

    monkeypatch.setattr(email_module, "settings", SimpleNamespace(SMTP_ENABLED=True))
    monkeypatch.setattr(PasswordResetMailer, "_send_sync", staticmethod(block_delivery))
    task = asyncio.create_task(PasswordResetMailer().send("user@example.com", "code"))
    start = monotonic()
    await asyncio.sleep(0.01)
    elapsed = monotonic() - start
    release.set()
    await task

    assert started.is_set()
    assert elapsed < 0.2
