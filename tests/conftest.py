import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Every test writes under a temp dir, never the real data/."""
    from school_planner import config, report

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(report, "DATA_DIR", tmp_path / "data")
    return tmp_path / "data"
