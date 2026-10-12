"""NHL season ids (20262027 = the 2026-27 season), shared by the ingest and model scripts."""

from datetime import date


def current_season_id(today=None):
    """Jul-Dec -> season starts this year; Jan-Jun -> it started last year."""
    today = today or date.today()
    start_year = today.year if today.month >= 7 else today.year - 1
    return int(f"{start_year}{start_year + 1}")


def previous_season_id(season_id):
    start = season_id // 10000
    return int(f"{start - 1}{start}")
