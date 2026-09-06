# WebNovel MCP

MCP server that reads web novels from [webnovel.com](https://www.webnovel.com). Search by title, browse chapters, read content — all through MCP tools.

## Install

```bash
uv add fastmcp cloudscraper beautifulsoup4
```

Or clone and install:

```bash
git clone https://github.com/minhmc2007/WebNovel-MCP.git
cd WebNovel-MCP
uv sync
```

## Configure

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "webnovel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/WebNovel-MCP", "webnovel-mcp"]
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `search_novels(query, page)` | Search by keyword. Returns 20 results per page with bookId, title, author, genre, rating. |
| `get_novel_by_name(name)` | Quick lookup — returns top match with bookId and next-step instructions. |
| `get_novel_info(book_id)` | Full metadata: title, author, description, chapter count, first chapter ID. |
| `get_chapter_list(book_id)` | Table of contents with chapter IDs and titles. |
| `read_chapter(book_id, chapter_id)` | Full chapter text. |

## Usage

Typical flow:

1. `search_novels("solo leveling")` — find the novel
2. `get_chapter_list(book_id)` — pick a chapter
3. `read_chapter(book_id, chapter_id)` — read it

Or skip to `get_novel_by_name("solo leveling")` for the bookId directly.

## How It Works

```
┌─────────────────────────────────────────────────────┐
│                  MCP Client                         │
│            (Claude, Cursor, etc.)                   │
└──────────────────────┬──────────────────────────────┘
                       │ stdio (JSON-RPC)
                       ▼
┌─────────────────────────────────────────────────────┐
│              webnovel-mcp server                    │
│                                                     │
│  ┌───────────┐  ┌────────────┐  ┌───────────────┐  │
│  │  search   │  │   novel    │  │    chapter    │  │
│  │  _novels  │  │   _info    │  │   _list /     │  │
│  │           │  │            │  │   read_chapter│  │
│  └─────┬─────┘  └─────┬──────┘  └──────┬────────┘  │
│        │              │                │            │
│        ▼              ▼                ▼            │
│  ┌─────────────────────────────────────────────┐    │
│  │           cloudscraper session              │    │
│  │   (bypasses Cloudflare, manages cookies)    │    │
│  └─────────────────────┬───────────────────────┘    │
└────────────────────────┼────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────┐
│               webnovel.com                          │
│                                                     │
│  /go/pcm/search/result     ← search API (JSON)     │
│  /book/{id}/catalog        ← catalog page (HTML)   │
│  /book/{id}/{chapter_id}   ← chapter page (HTML)   │
└─────────────────────────────────────────────────────┘
```

**Search** hits the JSON API at `/go/pcm/search/result` with a CSRF token. Returns structured data — bookId, title, author, genre, rating.

**Chapter list** scrapes the catalog HTML page. Chapter IDs are extracted from `<a href>` tags (pattern: `..._chapterId`). No encrypted API needed.

**Chapter reading** scrapes the chapter HTML page. Content lives in `.cha-words` elements as `<p>` tags. Free chapters only — locked chapters return a message.

All requests go through `cloudscraper` which handles Cloudflare's bot challenge automatically.

## Limits

- Free chapters only. VIP/locked chapters behind paywall.
- Rate limiting is Cloudflare's call, not the API's. Slow down if you get blocked.
- No authentication — works without login for free content.

## License

MIT
