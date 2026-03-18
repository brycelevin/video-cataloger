"""SQLite schema and query helpers."""

import json
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    parent_dir TEXT,
    relative_path TEXT,
    gif_path TEXT,
    file_size INTEGER,
    duration REAL,
    width INTEGER,
    height INTEGER,
    date_added TEXT DEFAULT (datetime('now')),
    date_modified TEXT,
    tags TEXT DEFAULT '[]',
    rating INTEGER,
    notes TEXT
);
"""


def init_db():
    """Create the database and tables if they don't exist."""
    with get_db() as db:
        db.executescript(SCHEMA)


@contextmanager
def get_db():
    """Yield a database connection with row_factory set."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_video(video_path, filename, parent_dir, relative_path,
                 file_size, duration, width, height, date_modified,
                 gif_path=None):
    """Insert or update a video record."""
    with get_db() as db:
        db.execute("""
            INSERT INTO videos
                (video_path, filename, parent_dir, relative_path,
                 file_size, duration, width, height, date_modified, gif_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_path) DO UPDATE SET
                filename=excluded.filename,
                parent_dir=excluded.parent_dir,
                relative_path=excluded.relative_path,
                file_size=excluded.file_size,
                duration=excluded.duration,
                width=excluded.width,
                height=excluded.height,
                date_modified=excluded.date_modified,
                gif_path=COALESCE(excluded.gif_path, videos.gif_path)
        """, (video_path, filename, parent_dir, relative_path,
              file_size, duration, width, height, date_modified, gif_path))


def set_gif_path(video_path, gif_path):
    """Update the GIF path for a video."""
    with get_db() as db:
        db.execute("UPDATE videos SET gif_path = ? WHERE video_path = ?",
                   (gif_path, video_path))


def get_video_by_id(video_id):
    """Return a single video row by ID."""
    with get_db() as db:
        return db.execute("SELECT * FROM videos WHERE id = ?",
                          (video_id,)).fetchone()


def get_videos(page=1, per_page=None, sort="filename", order="asc", query=None):
    """Return paginated, sorted, optionally filtered video list."""
    per_page = per_page or config.PAGE_SIZE
    allowed_sorts = {"filename", "date_added", "date_modified",
                     "file_size", "duration", "parent_dir"}
    if sort not in allowed_sorts:
        sort = "filename"
    if order not in ("asc", "desc"):
        order = "asc"

    where = ""
    params = []
    if query:
        where = "WHERE filename LIKE ? OR parent_dir LIKE ? OR relative_path LIKE ?"
        like = f"%{query}%"
        params = [like, like, like]

    with get_db() as db:
        total = db.execute(
            f"SELECT COUNT(*) FROM videos {where}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = db.execute(
            f"SELECT * FROM videos {where} ORDER BY {sort} {order} "
            f"LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

    return rows, total


def count_videos():
    """Return total number of videos in the database."""
    with get_db() as db:
        return db.execute("SELECT COUNT(*) FROM videos").fetchone()[0]


def count_gifs():
    """Return number of videos that have GIFs generated."""
    with get_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM videos WHERE gif_path IS NOT NULL"
        ).fetchone()[0]
