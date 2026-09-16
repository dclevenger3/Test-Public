from school_planner.browser import credentials_from_env


def test_credentials_from_env(monkeypatch):
    assert credentials_from_env("kid-1") is None
    monkeypatch.setenv("CLASSLINK_USER_KID_1", "u")
    monkeypatch.setenv("CLASSLINK_PASS_KID_1", "p")
    assert credentials_from_env("kid-1") == ("u", "p")
