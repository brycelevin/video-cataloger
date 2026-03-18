# Video Cataloger

Personal tool for browsing, previewing, and streaming 500-2000 mp4 videos spread across folders on an external drive. Generates animated GIF previews, stores metadata in SQLite, and serves a gallery UI via Flask.

**Target platform:** Windows. **Development machine:** macOS (MacBook). File paths in the database and on disk will use Windows backslash separators at runtime. Code must handle both separators where paths are parsed or displayed.

## Quick Start

```bash
pip install -r requirements.txt     # flask, python-dotenv, tqdm
brew install ffmpeg                  # requires ffmpeg + ffprobe on PATH

# Scan videos (metadata only, fast)
python scanner.py /path/to/videos --scan-only

# Generate GIF previews (test with 1 first)
python scanner.py /path/to/videos --limit 1
python scanner.py /path/to/videos            # full run, resumable

# Start web server
python server.py                             # http://127.0.0.1:5000
```

## Architecture

Three-layer design, no ORM, no build tools:

- **scanner.py** — CLI entry point. Recursively finds videos, extracts metadata via `ffprobe`, generates GIFs via `ffmpeg` with `ProcessPoolExecutor`. Resumable (skips existing GIFs).
- **models.py** — SQLite schema + all query helpers. Single `videos` table. Uses `sqlite3.Row` for dict-like access. All DB access goes through `get_db()` context manager.
- **server.py** — Flask app. Gallery grid with pagination/search/sort, video player page, `/stream/<id>` route with HTTP 206 Range support for seeking.
- **config.py** — All tunables (paths, GIF params, parallelism, server bind). Every value overridable via `VC_*` environment variables.

## Project Structure

```
config.py              # Configuration with env var overrides (VC_*)
models.py              # SQLite schema, init_db(), query helpers
scanner.py             # CLI: video discovery + ffprobe + GIF generation
server.py              # Flask app: gallery, player, streaming
templates/
  base.html            # Shared layout
  index.html           # Gallery grid with search/sort/pagination
  player.html          # Video player with metadata
static/
  css/style.css        # Responsive dark theme (4/2/1 col grid)
  js/app.js            # Lazy loading fallback
catalog.db             # SQLite database (gitignored)
gifs/                  # Generated GIF previews (gitignored)
```

## Database Schema

Single `videos` table in `catalog.db`. Key columns:
- `video_path` (TEXT UNIQUE) — absolute path, used as the natural key
- `relative_path` — path relative to scan root (survives drive remounts)
- `gif_path` — absolute path to generated GIF, NULL until created
- `duration`, `width`, `height` — from ffprobe
- `tags` (JSON array), `rating` (1-5), `notes` — placeholders for future use

Upserts use `ON CONFLICT(video_path) DO UPDATE` so re-scanning is safe and updates metadata without losing GIF paths.

## Key Design Decisions

- **Single ffmpeg command per GIF** — no temp frames, no Pillow. Uses palettegen/paletteuse filter chain for small file sizes (~500KB-2MB).
- **Flat GIF directory** — GIF filenames encode the folder path with `__` separators (e.g., `Folder__Subfolder__clip.gif`) to avoid collisions without nested dirs.
- **HTTP Range streaming** — `/stream/<id>` returns `206 Partial Content` for seek support in all browsers. Reads in 8KB chunks.
- **Sort whitelist** — `get_videos()` only allows known column names in ORDER BY to prevent SQL injection via the `sort` parameter.
- **No JS framework** — server-rendered Jinja2 templates. The only JS is a lazy-loading polyfill.
- **UTF-8 subprocess encoding** — All `subprocess.run` calls that invoke `ffmpeg`/`ffprobe` must use `encoding='utf-8', errors='replace'` alongside `text=True`. Windows defaults to cp1252, which crashes on non-ASCII bytes in video metadata or ffmpeg output. Always catch `TypeError` in addition to `json.JSONDecodeError` when parsing subprocess stdout, since encoding failures can produce `None`.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `VC_DB_PATH` | `./catalog.db` | SQLite database location |
| `VC_GIF_DIR` | `./gifs/` | GIF output directory |
| `VC_GIF_WIDTH` | `320` | GIF width in pixels |
| `VC_GIF_FRAMES` | `24` | Number of frames per GIF |
| `VC_GIF_MAX_COLORS` | `128` | GIF palette size |
| `VC_WORKERS` | `4` | Parallel GIF generation workers |
| `VC_PAGE_SIZE` | `60` | Videos per gallery page |
| `VC_HOST` | `127.0.0.1` | Server bind address |
| `VC_PORT` | `5000` | Server port |

## Web Routes

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Gallery page — `?page=`, `?sort=`, `?order=`, `?q=` |
| `/api/videos` | GET | JSON API (same params as gallery) |
| `/gif/<filename>` | GET | Serve GIF preview files |
| `/video/<id>` | GET | Video player page |
| `/stream/<id>` | GET | MP4 streaming with Range support |

## Scanner CLI

```
python scanner.py <root_dir> [--scan-only] [--limit N] [--workers N]
```

- `--scan-only` — discover + extract metadata, skip GIF generation
- `--limit N` — process only first N videos (for testing)
- `--workers N` — override parallel worker count

## Future Expansion Areas

The schema already has `tags` (JSON array), `rating` (integer 1-5), and `notes` (text) columns ready for:
- Tagging/rating UI in the gallery or player
- Bulk operations (delete, move, tag)
- Filter by tag/rating in the gallery
- Thumbnail hover scrubbing (replace GIFs with sprite sheets)
- Video deduplication (add a hash column)
- Export/import catalog as JSON
