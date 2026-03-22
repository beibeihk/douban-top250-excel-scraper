import os

import pytest

from douban_top250_to_excel import build_dataframe, crawl_books


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_NETWORK_TESTS") != "1",
    reason="Set RUN_NETWORK_TESTS=1 to enable network integration tests.",
)


def test_crawl_limit_5_end_to_end() -> None:
    records = crawl_books(
        timeout=20,
        retries=3,
        min_delay=0.0,
        max_delay=0.0,
        limit=5,
    )
    frame = build_dataframe(records)

    assert len(frame) == 5
    assert frame["subject_id"].nunique() == 5
    assert frame["title"].notna().all()
    assert frame["book_url"].str.contains("https://book.douban.com/subject/").all()
