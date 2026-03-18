"""Flask web server: gallery UI, video player, and streaming."""

import math
import mimetypes
import os
import re

from flask import (Flask, Response, abort, jsonify, render_template, request,
                   send_from_directory)

import config
import models

app = Flask(__name__)


def format_duration(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    if seconds is None:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(bytes_val):
    """Format bytes as human-readable size."""
    if bytes_val is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(bytes_val) < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"


app.jinja_env.filters["duration"] = format_duration
app.jinja_env.filters["filesize"] = format_size


@app.route("/")
def index():
    """Gallery page with GIF grid."""
    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "filename")
    order = request.args.get("order", "asc")
    query = request.args.get("q", "").strip() or None

    rows, total = models.get_videos(
        page=page, sort=sort, order=order, query=query
    )

    total_pages = max(1, math.ceil(total / config.PAGE_SIZE))
    page = min(page, total_pages)

    return render_template("index.html",
                           videos=rows,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           sort=sort,
                           order=order,
                           query=query or "")


@app.route("/api/videos")
def api_videos():
    """JSON API for video listing."""
    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "filename")
    order = request.args.get("order", "asc")
    query = request.args.get("q", "").strip() or None

    rows, total = models.get_videos(
        page=page, sort=sort, order=order, query=query
    )

    total_pages = max(1, math.ceil(total / config.PAGE_SIZE))

    return jsonify({
        "videos": [dict(r) for r in rows],
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@app.route("/gif/<path:filename>")
def serve_gif(filename):
    """Serve a generated GIF file."""
    return send_from_directory(str(config.GIF_DIR), filename)


@app.route("/video/<int:video_id>")
def player(video_id):
    """Video player page."""
    video = models.get_video_by_id(video_id)
    if not video:
        abort(404)
    return render_template("player.html", video=video)


@app.route("/stream/<int:video_id>")
def stream(video_id):
    """Stream video with HTTP Range request support for seeking."""
    video = models.get_video_by_id(video_id)
    if not video:
        abort(404)

    video_path = video["video_path"]
    if not os.path.isfile(video_path):
        abort(404)

    file_size = os.path.getsize(video_path)
    mime_type = mimetypes.guess_type(video_path)[0] or "video/mp4"

    range_header = request.headers.get("Range")
    if range_header:
        # Parse Range: bytes=start-end
        match = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            abort(416)

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            abort(416)

        length = end - start + 1

        def generate():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return Response(
            generate(),
            status=206,
            mimetype=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
            },
            direct_passthrough=True,
        )
    else:
        def generate():
            with open(video_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(
            generate(),
            status=200,
            mimetype=mime_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
            direct_passthrough=True,
        )


if __name__ == "__main__":
    models.init_db()
    app.run(host=config.HOST, port=config.PORT, debug=True)
