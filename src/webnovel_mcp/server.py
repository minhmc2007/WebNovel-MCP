"""WebNovel MCP Server - Read and search web novels from webnovel.com."""

import re
from typing import Any

import cloudscraper
from bs4 import BeautifulSoup
from fastmcp import FastMCP

mcp = FastMCP("webnovel")

_BASE = "https://www.webnovel.com"
_HEADERS = {
    "Referer": _BASE,
    "Origin": _BASE,
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

_scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True},
    delay=5,
)

_csrf_token: str | None = None


def _init_session() -> str:
    """Visit homepage to get cookies/CSRF token."""
    global _csrf_token
    if _csrf_token:
        return _csrf_token
    _scraper.get(_BASE, headers=_HEADERS, timeout=15)
    for c in _scraper.cookies:
        if c.name == "_csrfToken":
            _csrf_token = c.value
            break
    return _csrf_token or ""


def _search_api(keyword: str, page: int = 1) -> dict[str, Any]:
    token = _init_session()
    url = f"{_BASE}/go/pcm/search/result"
    params = {
        "_csrfToken": token,
        "keywords": keyword,
        "type": "novel",
        "pageIndex": str(page),
    }
    resp = _scraper.get(url, params=params, headers=_HEADERS, timeout=15)
    return resp.json()


def _fetch_html(url: str) -> str:
    _init_session()
    headers = {**_HEADERS, "Accept": "text/html,application/xhtml+xml"}
    resp = _scraper.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.text


def _regex_field(html: str, field: str) -> str | None:
    """Extract a JSON string field from embedded g_data via regex.
    Skips meta tags by searching for the field within g_data.book context."""
    # Find the g_data.book section first
    book_start = html.find("g_data.book=")
    if book_start < 0:
        book_start = 0
    search_html = html[book_start:]
    m = re.search(rf'"{field}":\s*"((?:[^"\\]|\\.)*)"', search_html)
    if not m:
        return None
    val = m.group(1)
    val = val.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")
    val = re.sub(r"\\(\s)", r" ", val)
    return val


def _regex_int(html: str, field: str) -> int | None:
    book_start = html.find("g_data.book=")
    if book_start < 0:
        book_start = 0
    search_html = html[book_start:]
    m = re.search(rf'"{field}":\s*(\d+)', search_html)
    return int(m.group(1)) if m else None


# ── Tools ──────────────────────────────────────────────────────────────────


@mcp.tool()
def search_novels(query: str, page: int = 1) -> str:
    """Search for web novels by title or keyword.

    Args:
        query: Search keyword (e.g. "martial peak", "solo leveling")
        page: Page number (default 1, 20 results per page)

    Returns:
        List of matching novels with bookId, title, author, genre, rating.
    """
    try:
        data = _search_api(query, page)
    except Exception as e:
        return f"Search failed: {e}"

    if data.get("code") != 0:
        return f"API error: {data.get('msg', 'unknown')}"

    books = data.get("data", {}).get("bookInfo", {}).get("bookItems") or []
    if not books:
        return f"No results for '{query}'."

    lines = [f"Found {len(books)} results for '{query}':\n"]
    for i, b in enumerate(books, 1):
        desc = (b.get("description") or "")[:120]
        lines.append(
            f"{i}. **{b.get('bookName', 'Unknown')}**\n"
            f"   ID: `{b.get('bookId', '')}`\n"
            f"   Author: {b.get('authorName', 'N/A')}\n"
            f"   Genre: {b.get('categoryName', 'N/A')}\n"
            f"   Rating: {b.get('totalScore', 'N/A')}\n"
            f"   {desc}..."
        )
    return "\n".join(lines)


@mcp.tool()
def get_novel_info(book_id: str) -> str:
    """Get detailed info about a novel (title, author, chapter count, first chapter).

    Args:
        book_id: The novel's book ID (from search results)

    Returns:
        Novel metadata including firstChapterId for reading.
    """
    try:
        html = _fetch_html(f"{_BASE}/book/{book_id}/catalog")
    except Exception as e:
        return f"Failed to fetch novel: {e}"

    book_name = _regex_field(html, "bookName") or "Unknown"
    author = _regex_field(html, "authorName") or "N/A"
    category = _regex_field(html, "categoryName") or "N/A"
    total_chapters = _regex_int(html, "totalChapterNum")
    first_ch = _regex_int(html, "firstChapterId")
    score = _regex_int(html, "totalScore")
    description = _regex_field(html, "description") or ""

    lines = [
        f"**{book_name}**\n",
        f"Book ID: `{book_id}`",
        f"Author: {author}",
        f"Genre: {category}",
        f"Rating: {score or 'N/A'}",
        f"Total Chapters: {total_chapters or 'N/A'}",
    ]
    if first_ch:
        lines.append(f"First Chapter ID: `{first_ch}`")
    if description:
        lines.append(f"\nDescription:\n{description[:500]}")
    return "\n".join(lines)


@mcp.tool()
def get_chapter_list(book_id: str) -> str:
    """Get the full table of contents for a novel.

    Args:
        book_id: The novel's book ID

    Returns:
        List of chapters with IDs, titles, and volume info.
    """
    try:
        html = _fetch_html(f"{_BASE}/book/{book_id}/catalog")
    except Exception as e:
        return f"Failed to fetch catalog: {e}"

    soup = BeautifulSoup(html, "html.parser")
    volumes = soup.select(".volume-item")

    if not volumes:
        return "No chapters found in catalog."

    lines = []
    ch_count = 0
    for vol in volumes:
        vol_name_el = vol.select_one(".volume-name")
        if vol_name_el:
            lines.append(f"\n**{vol_name_el.get_text(strip=True)}**")

        for a in vol.select("a"):
            href = a.get("href", "")
            title = a.get("title") or a.get_text(strip=True)
            # Extract chapter ID from href: ..._chapterId
            m = re.search(r"_(\d+)$", href)
            ch_id = m.group(1) if m else "?"
            lines.append(f"  `{ch_id}` | {title}")
            ch_count += 1

    header = f"**Chapter List** ({ch_count} chapters):\n"
    return header + "\n".join(lines)


@mcp.tool()
def read_chapter(book_id: str, chapter_id: str) -> str:
    """Read the full content of a chapter.

    Args:
        book_id: The novel's book ID
        chapter_id: The chapter's chapter ID (from chapter list)

    Returns:
        The full text content of the chapter.
    """
    try:
        html = _fetch_html(f"{_BASE}/book/{book_id}/{chapter_id}")
    except Exception as e:
        return f"Failed to fetch chapter: {e}"

    soup = BeautifulSoup(html, "html.parser")

    # Primary: .cha-words contains chapter paragraphs
    content_div = soup.select_one(".cha-words")
    if content_div:
        paragraphs = [p.get_text(strip=True) for p in content_div.select("p") if p.get_text(strip=True)]
        if paragraphs:
            # Get chapter title
            title_el = soup.select_one(".cha-hd h1") or soup.select_one(".cha-hd .txt")
            title = title_el.get_text(strip=True) if title_el else "Chapter"
            return f"**{title}**\n\n" + "\n\n".join(paragraphs)

    # Fallback: check if locked
    lock = soup.select_one(".vip-locked, .locked, .pay")
    if lock:
        return "This chapter is locked (requires premium/VIP access)."

    return "Could not extract chapter content. The chapter may be locked or the page structure changed."


@mcp.tool()
def get_novel_by_name(name: str) -> str:
    """Quick search: find a novel by name and return book_id with first chapter.

    Args:
        name: Novel name to search for

    Returns:
        Top match with book_id, author, and instructions to read.
    """
    try:
        data = _search_api(name)
    except Exception as e:
        return f"Search failed: {e}"

    if data.get("code") != 0:
        return f"API error: {data.get('msg', 'unknown')}"

    books = data.get("data", {}).get("bookInfo", {}).get("bookItems") or []
    if not books:
        return f"No results for '{name}'."

    b = books[0]
    book_id = b.get("bookId", "")
    lines = [
        f"**{b.get('bookName', 'Unknown')}**",
        f"Book ID: `{book_id}`",
        f"Author: {b.get('authorName', 'N/A')}",
        f"Genre: {b.get('categoryName', 'N/A')}",
        f"Rating: {b.get('totalScore', 'N/A')}",
        f"\nNext steps:",
        f"  1. `get_novel_info('{book_id}')` - full details",
        f"  2. `get_chapter_list('{book_id}')` - all chapters",
        f"  3. `read_chapter('{book_id}', '<chapter_id>')` - read a chapter",
    ]
    return "\n".join(lines)


# ── Entry ──────────────────────────────────────────────────────────────────


def main():
    mcp.run()


if __name__ == "__main__":
    main()
