"""Encerramento exclusivo: 25/10 00h00 em Fortaleza = até 24/10 23h59."""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Fortaleza")
END = datetime(2026, 10, 25, tzinfo=ZONE)


def now_local():
    return datetime.now(ZONE)


def expired(now=None):
    return (now or now_local()) >= END
