#!/usr/bin/env python3
"""
Scrape Douban Top 250 books and export to Excel.
"""

from __future__ import annotations

import argparse
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

BASE_URL = "https://book.douban.com/top250"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
SUBJECT_ID_RE = re.compile(r"/subject/(\d+)/?")
RATING_COUNT_RE = re.compile(r"(\d+)")
KEY_VALUE_RE = re.compile(r"^([^:：]+)\s*[:：]\s*(.*)$")

FIXED_COLUMNS = [
    "rank",
    "subject_id",
    "title",
    "book_url",
    "cover_url",
    "rating",
    "rating_count",
    "list_meta_raw",
    "quote",
    "content_intro",
    "author_intro",
    "info_raw",
    "crawl_error",
    "crawled_at",
]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_subject_id(url: str) -> str:
    match = SUBJECT_ID_RE.search(url)
    return match.group(1) if match else ""


def extract_digits(text: str) -> str:
    match = RATING_COUNT_RE.search(text)
    return match.group(1) if match else ""


def fetch_with_retry(
    session: requests.Session,
    url: str,
    timeout: int,
    retries: int,
    headers: Dict[str, str],
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                break
            backoff = min(2**attempt, 8) + random.uniform(0, 0.8)
            time.sleep(backoff)
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def parse_list_item(item: Tag, rank: int) -> Dict[str, str]:
    link_tag = item.select_one("a.nbg")
    if link_tag is None or not link_tag.get("href"):
        raise ValueError("List item missing detail URL")

    book_url = str(link_tag["href"]).strip()
    cover_tag = link_tag.select_one("img")
    cover_url = str(cover_tag["src"]).strip() if cover_tag and cover_tag.get("src") else ""

    title_tag = item.select_one("div.pl2 a")
    title = ""
    if title_tag is not None:
        title = clean_text(str(title_tag.get("title") or title_tag.get_text(" ", strip=True)))

    rating_tag = item.select_one("span.rating_nums")
    rating = clean_text(rating_tag.get_text()) if rating_tag else ""

    rating_people_tag = item.select_one("div.star span.pl")
    rating_count = extract_digits(rating_people_tag.get_text(" ", strip=True)) if rating_people_tag else ""

    meta_tag = item.select_one("p.pl")
    quote_tag = item.select_one("p.quote span.inq") or item.select_one("p.quote")

    return {
        "rank": str(rank),
        "subject_id": extract_subject_id(book_url),
        "title": title,
        "book_url": book_url,
        "cover_url": cover_url,
        "rating": rating,
        "rating_count": rating_count,
        "list_meta_raw": clean_text(meta_tag.get_text(" ", strip=True)) if meta_tag else "",
        "quote": clean_text(quote_tag.get_text(" ", strip=True)) if quote_tag else "",
    }


def split_info_lines(info_tag: Tag) -> List[str]:
    lines: List[str] = []
    chunk: List[str] = []

    def flush() -> None:
        if not chunk:
            return
        merged = clean_text(" ".join(chunk)).strip()
        if merged:
            lines.append(merged)
        chunk.clear()

    for child in info_tag.children:
        if isinstance(child, NavigableString):
            text = clean_text(str(child))
            if text:
                chunk.append(text)
            continue

        if isinstance(child, Tag) and child.name == "br":
            flush()
            continue

        if isinstance(child, Tag):
            text = clean_text(child.get_text(" ", strip=True))
            if text:
                chunk.append(text)

    flush()
    return lines


def merge_value(old_value: str, new_value: str) -> str:
    if not old_value:
        return new_value
    if not new_value:
        return old_value
    if new_value == old_value:
        return old_value
    return f"{old_value} / {new_value}"


def parse_info_block(info_tag: Optional[Tag]) -> Tuple[str, Dict[str, str]]:
    if info_tag is None:
        return "", {}

    info_raw = clean_text(" ".join(info_tag.stripped_strings))
    fields: Dict[str, str] = {}
    current_key = ""

    for line in split_info_lines(info_tag):
        match = KEY_VALUE_RE.match(line)
        if match:
            key = clean_text(match.group(1))
            value = clean_text(match.group(2))
            if key:
                current_key = key
                fields[key] = merge_value(fields.get(key, ""), value)
            continue

        if line.startswith((":", "：")) and current_key:
            value = clean_text(line[1:])
            fields[current_key] = merge_value(fields.get(current_key, ""), value)
            continue

        if current_key and line:
            fields[current_key] = merge_value(fields.get(current_key, ""), line)

    # Drop keys that remain empty after parsing noise.
    fields = {k: v for k, v in fields.items() if v}
    return info_raw, fields


def extract_section_text(soup: BeautifulSoup, section_title: str) -> str:
    for h2 in soup.select("h2"):
        heading = clean_text(" ".join(h2.stripped_strings))
        if section_title not in heading:
            continue

        content_block = h2.find_next_sibling(lambda tag: isinstance(tag, Tag) and tag.name == "div")
        if content_block is None:
            continue

        target = (
            content_block.select_one("span.all.hidden")
            or content_block.select_one("span.short")
            or content_block.select_one("div.intro")
        )
        source = target if target is not None else content_block
        text = clean_text(" ".join(source.stripped_strings))
        if text:
            return text

    return ""


def parse_detail_page(detail_html: str) -> Dict[str, str]:
    soup = BeautifulSoup(detail_html, "lxml")

    rating_tag = soup.select_one("strong.ll.rating_num") or soup.select_one("strong[property='v:average']")
    votes_tag = soup.select_one("a.rating_people span[property='v:votes']")

    info_raw, info_fields = parse_info_block(soup.select_one("#info"))
    content_intro = extract_section_text(soup, "内容简介")
    author_intro = extract_section_text(soup, "作者简介")

    parsed: Dict[str, str] = {
        "rating": clean_text(rating_tag.get_text()) if rating_tag else "",
        "rating_count": clean_text(votes_tag.get_text()) if votes_tag else "",
        "content_intro": content_intro,
        "author_intro": author_intro,
        "info_raw": info_raw,
    }

    for key, value in info_fields.items():
        parsed[f"info_{key}"] = value
    return parsed


def iter_top250_pages(limit: Optional[int]) -> Iterable[int]:
    if limit is None:
        yield from range(0, 250, 25)
        return

    pages = max((limit - 1) // 25 + 1, 1)
    for idx in range(pages):
        yield idx * 25


def crawl_books(
    timeout: int,
    retries: int,
    min_delay: float,
    max_delay: float,
    limit: Optional[int] = None,
) -> List[Dict[str, str]]:
    session = requests.Session()
    records_by_subject: Dict[str, Dict[str, str]] = {}

    for start in iter_top250_pages(limit):
        page_url = f"{BASE_URL}?start={start}"
        list_html = fetch_with_retry(session, page_url, timeout, retries, DEFAULT_HEADERS)
        soup = BeautifulSoup(list_html, "lxml")
        items = soup.select("tr.item")

        for idx, item in enumerate(items, start=1):
            rank = start + idx
            record = parse_list_item(item, rank)
            subject_id = record["subject_id"] or f"unknown-{rank}"
            if subject_id not in records_by_subject:
                records_by_subject[subject_id] = record
            if limit is not None and len(records_by_subject) >= limit:
                break

        if limit is not None and len(records_by_subject) >= limit:
            break

    records = sorted(records_by_subject.values(), key=lambda row: int(row["rank"]))
    total = len(records)

    for idx, record in enumerate(records, start=1):
        record["crawl_error"] = ""
        try:
            detail_html = fetch_with_retry(session, record["book_url"], timeout, retries, DEFAULT_HEADERS)
            detail = parse_detail_page(detail_html)

            for key, value in detail.items():
                if key in ("rating", "rating_count"):
                    if value:
                        record[key] = value
                else:
                    record[key] = value
        except Exception as exc:  # noqa: BLE001 - keep per-book failures non-fatal.
            record["crawl_error"] = f"{type(exc).__name__}: {exc}"
            record.setdefault("content_intro", "")
            record.setdefault("author_intro", "")
            record.setdefault("info_raw", "")

        record["crawled_at"] = datetime.now().isoformat(timespec="seconds")

        if idx < total and max_delay > 0:
            time.sleep(random.uniform(min_delay, max_delay))

    return records


def build_dataframe(records: List[Dict[str, str]]) -> pd.DataFrame:
    dynamic_info_columns = sorted(
        {
            key
            for row in records
            for key in row
            if key.startswith("info_") and key != "info_raw"
        }
    )
    columns = FIXED_COLUMNS + dynamic_info_columns
    table = [{column: row.get(column, "") for column in columns} for row in records]
    frame = pd.DataFrame(table, columns=columns)
    if not frame.empty:
        frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
        frame.sort_values("rank", inplace=True)
        frame["rank"] = frame["rank"].astype("Int64")
    return frame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Douban Top250 books into an Excel file.")
    parser.add_argument("--output", default="douban_top250_books.xlsx", help="Excel output path.")
    parser.add_argument("--min-delay", type=float, default=1.0, help="Minimum delay between detail requests.")
    parser.add_argument("--max-delay", type=float, default=2.0, help="Maximum delay between detail requests.")
    parser.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Maximum retry count for each request.")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit for testing runs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.min_delay < 0 or args.max_delay < 0:
        raise SystemExit("--min-delay and --max-delay must be >= 0")
    if args.max_delay < args.min_delay:
        raise SystemExit("--max-delay must be >= --min-delay")
    if args.timeout <= 0:
        raise SystemExit("--timeout must be > 0")
    if args.retries < 0:
        raise SystemExit("--retries must be >= 0")
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be > 0 when provided")

    records = crawl_books(
        timeout=args.timeout,
        retries=args.retries,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        limit=args.limit,
    )
    frame = build_dataframe(records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(output_path, index=False, sheet_name="top250")

    error_count = int((frame["crawl_error"] != "").sum()) if "crawl_error" in frame.columns else 0
    print(f"Saved {len(frame)} books to {output_path.resolve()}")
    print(f"Rows with crawl_error: {error_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
