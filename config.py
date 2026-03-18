"""Central configuration for video-cataloger."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Database
DB_PATH = os.environ.get("VC_DB_PATH", str(BASE_DIR / "catalog.db"))

# GIF output directory
GIF_DIR = Path(os.environ.get("VC_GIF_DIR", str(BASE_DIR / "gifs")))
GIF_DIR.mkdir(exist_ok=True)

# GIF generation parameters
GIF_WIDTH = int(os.environ.get("VC_GIF_WIDTH", "320"))
GIF_FRAMES = int(os.environ.get("VC_GIF_FRAMES", "24"))
GIF_MAX_COLORS = int(os.environ.get("VC_GIF_MAX_COLORS", "128"))

# Scanner parallelism
WORKERS = int(os.environ.get("VC_WORKERS", "4"))

# Video file extensions to scan
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}

# Web server
PAGE_SIZE = int(os.environ.get("VC_PAGE_SIZE", "60"))
HOST = os.environ.get("VC_HOST", "127.0.0.1")
PORT = int(os.environ.get("VC_PORT", "5000"))
