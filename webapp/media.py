"""媒体处理：图片压缩、缩略图、视频抽帧"""
import base64
import io
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS


def classify(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def safe_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "file"
    # Windows 保留设备名（CON/NUL 等）无法作为文件名
    stem, ext = os.path.splitext(name)
    if stem.upper() in {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4",
        "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }:
        name = "_" + name
    if len(name) > 180:
        stem, ext = os.path.splitext(name)
        name = stem[: 180 - len(ext)] + ext
    return name


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{stem}_{i}{ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def write_text(path: str, text: str) -> str:
    path = unique_path(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")
    return path


def _b64_jpeg(img: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def prepare_image(path: str, max_side: int = 1600, quality: int = 88):
    """读取图片 -> 等比缩放 -> JPEG data URL。返回 (dataurl, meta) 或抛异常"""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, float(max_side) / max(w, h))
        if scale < 1.0:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
            w, h = im.size
        data = _b64_jpeg(im, quality)
    return data, {"width": w, "height": h, "format": "jpeg"}


def make_thumb(path: str, out_path: str, size: int = 320):
    try:
        if classify(path) == "video":
            cap = cv2.VideoCapture(path)
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return None
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        else:
            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
        img.thumbnail((size, size), Image.LANCZOS)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        img.convert("RGB").save(out_path, "JPEG", quality=82)
        return out_path
    except Exception:
        return None


def _encode_frame(frame, max_side: int = 1024, quality: int = 85):
    h0, w0 = frame.shape[:2]
    scale = min(1.0, float(max_side) / max(h0, w0))
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")


def sample_video(path: str, count: int = 10, max_side: int = 1024):
    """均匀抽样帧（不编码），返回 (frames, meta)"""
    try:
        count = max(3, min(24, int(count)))
    except (TypeError, ValueError):
        count = 9
    try:
        max_side = max(512, min(2048, int(max_side)))
    except (TypeError, ValueError):
        max_side = 1024
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("无法打开视频文件")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = (total / fps) if fps > 0 else 0

    frames = []
    idxs = [min(total - 1, int(i * total / count)) for i in range(count)] if total > 0 else []
    if idxs:
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if ok:
                h0, w0 = frame.shape[:2]
                scale = min(1.0, float(max_side) / max(h0, w0))
                if scale < 1.0:
                    frame = cv2.resize(frame, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
                frames.append(frame)
    else:
        step = 5
        i = 0
        while len(frames) < count:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                h0, w0 = frame.shape[:2]
                scale = min(1.0, float(max_side) / max(h0, w0))
                if scale < 1.0:
                    frame = cv2.resize(frame, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
                frames.append(frame)
            i += 1
    cap.release()

    if not frames:
        raise RuntimeError("视频帧提取失败，文件可能损坏或格式不受支持")
    meta = {
        "duration": round(duration, 1), "fps": round(fps, 1),
        "width": width, "height": height, "frames": len(frames),
    }
    return frames, meta


def frames_to_dataurls(frames, quality: int = 85):
    return [u for f in frames if (u := _encode_frame(f, quality=quality))]


def contact_sheet(frames, cols: int = 3, cell: int = 640, quality: int = 85):
    """把多帧拼成一张触点图，显著降低请求体积与耗时"""
    if not frames:
        return []
    n = len(frames)
    rows = (n + cols - 1) // cols
    h, w = frames[0].shape[:2]
    scale = min(1.0, float(cell) / max(h, w))
    cw, ch = max(1, int(w * scale)), max(1, int(h * scale))
    sheet = np.full((rows * ch + (rows - 1) * 4, cols * cw + (cols - 1) * 4, 3), 18, np.uint8)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        tile = cv2.resize(f, (cw, ch), interpolation=cv2.INTER_AREA)
        y = r * (ch + 4)
        x = c * (cw + 4)
        sheet[y:y + ch, x:x + cw] = tile
    url = _encode_frame(sheet, max_side=2048, quality=quality)
    return [url] if url else []


def extract_video_frames(path: str, count: int = 10, max_side: int = 1024, quality: int = 85, grid: bool = False):
    """兼容旧接口：返回 (dataurl列表, meta)"""
    frames, meta = sample_video(path, count=count, max_side=max_side)
    meta["mode"] = "grid" if grid else "frames"
    imgs = contact_sheet(frames, quality=quality) if grid else frames_to_dataurls(frames, quality=quality)
    if not imgs:
        raise RuntimeError("视频帧编码失败")
    return imgs, meta


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"
