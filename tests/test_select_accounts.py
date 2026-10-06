from creative_research.stages.select_accounts import clean, pid


def test_clean_username_accepts_url_and_at_handle() -> None:
    assert clean("https://www.tiktok.com/@NickYStudy12/video/123") == "NickYStudy12"
    assert clean("@estudio1252") == "estudio1252"


def test_pid_prefers_post_id() -> None:
    assert pid({"post_id": 123, "url": "fallback"}) == "123"
