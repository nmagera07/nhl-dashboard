import logging

import logging_config


def test_a_read_only_folder_falls_back_to_console_logging(monkeypatch, tmp_path):
    readonly = tmp_path / "ro"
    readonly.mkdir()
    readonly.chmod(0o500)
    monkeypatch.setattr(logging_config, "LOGS_DIR", str(readonly / "logs"))
    try:
        logger = logging_config.setup_logging("readonly_test_logger")
    finally:
        readonly.chmod(0o700)
    assert [type(h) for h in logger.handlers] == [logging.StreamHandler]
