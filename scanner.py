"""CLI scanner: discovers videos, extracts metadata via ffprobe, generates GIFs via ffmpeg."""

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

import config
import models


def find_videos(root_dir):
    """Recursively find all video files under root_dir."""
    root = Path(root_dir)
    videos = []
    for path in root.rglob("*"):
        if path.suffix.lower() in config.VIDEO_EXTENSIONS and path.is_file():
            videos.append(path)
    return sorted(videos)


def ffprobe_metadata(video_path):
    """Extract duration, width, height from a video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None, None, None

    duration = None
    width = None
    height = None

    # Get duration from format
    fmt = data.get("format", {})
    if "duration" in fmt:
        try:
            duration = float(fmt["duration"])
        except (ValueError, TypeError):
            pass

    # Get resolution from first video stream
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            if duration is None and "duration" in stream:
                try:
                    duration = float(stream["duration"])
                except (ValueError, TypeError):
                    pass
            break

    return duration, width, height


def gif_output_path(video_path, scan_root):
    """Generate a flat GIF filename from the video's relative path."""
    rel = Path(video_path).relative_to(scan_root)
    # Replace path separators with __ and change extension
    name = str(rel).replace(os.sep, "__")
    name = Path(name).stem + ".gif"
    return config.GIF_DIR / name


def extract_frame(video_path, timestamp, output_path):
    """Extract a single frame at a given timestamp using fast keyframe seek."""
    cmd = [
        "ffmpeg", "-y", "-v", "warning",
        "-ss", f"{timestamp:.2f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={config.GIF_WIDTH}:-1:flags=lanczos",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0 and Path(output_path).exists()
    except subprocess.TimeoutExpired:
        return False


def generate_gif(video_path, gif_path, duration):
    """Generate an animated GIF by seeking to random timestamps and grabbing single frames."""
    gif_path = Path(gif_path)
    gif_path.parent.mkdir(parents=True, exist_ok=True)

    if duration is None or duration <= 0:
        duration = 10  # fallback

    num_frames = config.GIF_FRAMES
    # Pick random timestamps spread throughout the video (skip first/last 2%)
    margin = duration * 0.02
    timestamps = sorted(random.uniform(margin, duration - margin) for _ in range(num_frames))

    with tempfile.TemporaryDirectory() as tmpdir:
        frame_paths = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(tmpdir, f"frame_{i:03d}.png")
            if extract_frame(video_path, ts, frame_path):
                frame_paths.append(frame_path)

        if not frame_paths:
            print(f"\n  No frames extracted for {Path(video_path).name}")
            return False

        # Assemble frames into GIF using ffmpeg concat + palette
        # Target ~3fps playback so the GIF loops in a few seconds
        list_file = os.path.join(tmpdir, "frames.txt")
        with open(list_file, "w") as f:
            for fp in frame_paths:
                f.write(f"file '{fp}'\n")
                f.write("duration 0.33\n")
            # Repeat last frame to avoid truncation
            f.write(f"file '{frame_paths[-1]}'\n")

        vf = (
            f"split[s0][s1];"
            f"[s0]palettegen=max_colors={config.GIF_MAX_COLORS}:stats_mode=diff[p];"
            f"[s1][p]paletteuse=dither=bayer:bayer_scale=3[out]"
        )

        cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-filter_complex", vf,
            "-map", "[out]",
            "-loop", "0",
            str(gif_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                stderr_tail = result.stderr.strip().splitlines()[-3:] if result.stderr.strip() else ["(no output)"]
                print(f"\n  ffmpeg failed for {Path(video_path).name}:\n    " + "\n    ".join(stderr_tail))
                if gif_path.exists():
                    gif_path.unlink()
                return False
        except subprocess.TimeoutExpired:
            print(f"\n  ffmpeg timed out assembling GIF for {Path(video_path).name}")
            if gif_path.exists():
                gif_path.unlink()
            return False

    return gif_path.exists()


def process_one_video(args):
    """Worker function: generate GIF for a single video. Used by ProcessPoolExecutor."""
    video_path_str, gif_path_str, duration = args
    success = generate_gif(video_path_str, gif_path_str, duration)
    if success:
        return video_path_str, gif_path_str
    return video_path_str, None


def scan(root_dir, limit=None, scan_only=False, skip_existing=True):
    """Main scan pipeline: discover, extract metadata, generate GIFs."""
    root = Path(root_dir).resolve()
    if not root.exists():
        print(f"Error: {root} does not exist")
        sys.exit(1)

    models.init_db()

    # Phase 1: Discover videos
    print(f"Scanning {root} for videos...")
    videos = find_videos(root)
    print(f"Found {len(videos)} video files")

    if limit:
        videos = videos[:limit]
        print(f"Limited to {limit} videos")

    # Phase 2: Extract metadata and populate DB
    print("Extracting metadata...")
    gif_tasks = []
    for vpath in tqdm(videos, desc="Metadata"):
        stat = vpath.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        duration, width, height = ffprobe_metadata(vpath)

        gpath = gif_output_path(vpath, root)
        existing_gif = str(gpath) if gpath.exists() else None

        models.upsert_video(
            video_path=str(vpath),
            filename=vpath.name,
            parent_dir=vpath.parent.name,
            relative_path=str(vpath.relative_to(root)),
            file_size=stat.st_size,
            duration=duration,
            width=width,
            height=height,
            date_modified=mtime,
            gif_path=existing_gif,
        )

        if not scan_only:
            if skip_existing and gpath.exists():
                continue
            gif_tasks.append((str(vpath), str(gpath), duration))

    total_in_db = models.count_videos()
    print(f"Database now has {total_in_db} videos")

    if scan_only:
        print("Scan-only mode — skipping GIF generation")
        return

    if not gif_tasks:
        print("All GIFs already generated — nothing to do")
        return

    # Phase 3: Generate GIFs in parallel
    print(f"Generating {len(gif_tasks)} GIFs with {config.WORKERS} workers...")
    completed = 0
    failed = 0

    with ProcessPoolExecutor(max_workers=config.WORKERS) as pool:
        futures = {pool.submit(process_one_video, t): t for t in gif_tasks}
        with tqdm(total=len(gif_tasks), desc="GIFs") as pbar:
            for future in as_completed(futures):
                video_path_str, gif_result = future.result()
                if gif_result:
                    models.set_gif_path(video_path_str, gif_result)
                    completed += 1
                else:
                    failed += 1
                pbar.update(1)

    print(f"Done: {completed} GIFs created, {failed} failed")
    print(f"Total GIFs: {models.count_gifs()}")


def main():
    parser = argparse.ArgumentParser(description="Scan videos and generate GIF previews")
    parser.add_argument("root", help="Root directory to scan for videos")
    parser.add_argument("--limit", type=int, help="Limit number of videos to process")
    parser.add_argument("--scan-only", action="store_true",
                        help="Only discover and extract metadata, skip GIF generation")
    parser.add_argument("--workers", type=int, help="Number of parallel workers")
    args = parser.parse_args()

    if args.workers:
        config.WORKERS = args.workers

    scan(args.root, limit=args.limit, scan_only=args.scan_only)


if __name__ == "__main__":
    main()
