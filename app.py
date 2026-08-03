"""
Lab 6 Nâng cao - Computer Vision as IoT Sensor: Parameter Experiment

Mở rộng từ Lab 6 cơ bản với:
- ROI (Region of Interest) crop
- Blur score (Laplacian variance)
- Advanced processed contact sheet: original+ROI, grayscale, threshold, edge, motion mask combined
- parameter_experiment_log.csv (ghi tham số + kết quả mỗi lần thử)
- Canny edge tunable (low/high)
- Threshold tunable
- Motion cooldown
- Nhiều API endpoint mới hỗ trợ dashboard nâng cao

Run:
    uvicorn app:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import csv
import json
import time
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

# ─── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw_images"
PROCESSED_DIR = DATA_DIR / "processed_images"
VIDEO_DIR = DATA_DIR / "videos"
OUTPUT_DIR = ROOT / "outputs"
METADATA_CSV = OUTPUT_DIR / "image_metadata.csv"
EVENT_CSV = OUTPUT_DIR / "image_event_log.csv"
PARAM_CSV = OUTPUT_DIR / "parameter_experiment_log.csv"
INDEX_HTML = ROOT / "index.html"

for folder in [RAW_DIR, PROCESSED_DIR, VIDEO_DIR, OUTPUT_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# ─── CSV field definitions ────────────────────────────────────────────────────
METADATA_FIELDS = [
    "image_id", "device_id", "timestamp", "source_type", "image_path",
    "processed_path", "width", "height", "brightness", "blur_score",
    "processing_status", "processing_time_ms", "note"
]

EVENT_FIELDS = [
    "event_id", "image_id", "timestamp", "event_type", "score",
    "severity", "explanation", "action_hint", "rule_used"
]

PARAM_FIELDS = [
    "exp_id", "timestamp", "image_id", "roi_x1", "roi_y1", "roi_x2", "roi_y2",
    "threshold_value", "canny_low", "canny_high", "motion_threshold", "min_area",
    "cooldown_sec", "brightness", "blur_score", "motion_score", "event_type", "note"
]

# ─── Cooldown state ───────────────────────────────────────────────────────────
_last_motion_event_time: float = 0.0

# ─── Utility ─────────────────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append_csv(path: Path, fieldnames: List[str], row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def relative_url(path: Optional[Path]) -> Optional[str]:
    if not path:
        return None
    try:
        rel = path.resolve().relative_to(ROOT.resolve())
        return f"/files/{rel.as_posix()}"
    except Exception:
        return None


def validate_image_bytes(data: bytes) -> "Image.Image":
    try:
        return Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {exc}") from exc


def pil_to_bgr(img: "Image.Image") -> np.ndarray:
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def frame_to_jpeg_bytes(frame_bgr: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".jpg", frame_bgr)
    if not ok:
        raise RuntimeError("Could not encode frame as JPEG")
    return buffer.tobytes()

# ─── Image analysis functions ─────────────────────────────────────────────────
def compute_brightness(frame_bgr: np.ndarray) -> float:
    """Tính độ sáng trung bình (0-255)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def compute_blur_score(frame_bgr: np.ndarray) -> float:
    """Tính độ sắc nét bằng variance of Laplacian. Cao = sắc, thấp = mờ."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def crop_roi(frame_bgr: np.ndarray,
             roi: Optional[Tuple[int, int, int, int]] = None) -> Tuple[np.ndarray, Optional[Tuple[int,int,int,int]]]:
    """
    Crop vùng ROI từ frame.
    roi = (x1, y1, x2, y2) tính theo pixel. None = full frame.
    Trả về (cropped_frame, roi_used).
    """
    if roi is None:
        return frame_bgr, None
    h, w = frame_bgr.shape[:2]
    x1 = max(0, min(roi[0], w - 1))
    y1 = max(0, min(roi[1], h - 1))
    x2 = max(x1 + 1, min(roi[2], w))
    y2 = max(y1 + 1, min(roi[3], h))
    return frame_bgr[y1:y2, x1:x2], (x1, y1, x2, y2)


def event_from_quality(image_id: str, brightness: float, blur_score: float) -> Dict[str, Any]:
    """Sinh event dựa trên chất lượng ảnh (brightness + blur)."""
    timestamp = now_iso()

    if brightness < 60:
        event_type = "LOW_LIGHT"
        severity = "WARNING"
        explanation = f"Brightness={brightness:.1f} < 60: ảnh tối, AI inference có thể kém chính xác."
        action_hint = "Cải thiện ánh sáng hoặc điều chỉnh exposure camera."
        rule = "brightness < 60"
    elif brightness > 220:
        event_type = "OVER_EXPOSED"
        severity = "WARNING"
        explanation = f"Brightness={brightness:.1f} > 220: ảnh quá sáng, chi tiết có thể bị mất."
        action_hint = "Giảm exposure hoặc kiểm tra nguồn sáng trực tiếp vào lens."
        rule = "brightness > 220"
    elif blur_score < 80:
        event_type = "BLURRY_IMAGE"
        severity = "WARNING"
        explanation = f"Blur score={blur_score:.1f} < 80: ảnh mờ, camera có thể bị rung."
        action_hint = "Kiểm tra camera bị rung hoặc lấy nét sai."
        rule = "blur_score < 80"
    else:
        event_type = "IMAGE_QUALITY_OK"
        severity = "NORMAL"
        explanation = f"Brightness={brightness:.1f}, Blur={blur_score:.1f}: chất lượng ảnh tốt."
        action_hint = "Tiếp tục pipeline hoặc gửi ảnh sang Lab 7 object detection."
        rule = "brightness 60-220 AND blur_score >= 80"

    return {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "image_id": image_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "score": round(brightness, 2),
        "severity": severity,
        "explanation": explanation,
        "action_hint": action_hint,
        "rule_used": rule,
    }


def create_advanced_contact_sheet(
    frame_bgr: np.ndarray,
    image_id: str,
    roi: Optional[Tuple[int,int,int,int]] = None,
    threshold_value: int = 120,
    canny_low: int = 80,
    canny_high: int = 160,
    motion_mask: Optional[np.ndarray] = None,
) -> Tuple[Path, float, Dict[str, Any]]:
    """
    Tạo ảnh contact sheet 6 ô:
    1. Original (có vẽ khung ROI nếu có)
    2. ROI crop (hoặc full frame nếu không có ROI)
    3. Grayscale
    4. Threshold (giá trị tunable)
    5. Canny Edge (tunable)
    6. Motion mask / combined (nếu có) hoặc Laplacian
    """
    start = time.perf_counter()

    TILE_W, TILE_H = 320, 240
    h_orig, w_orig = frame_bgr.shape[:2]

    # ── Tile 1: Original + ROI box ────────────────────────────────────────────
    orig_disp = cv2.resize(frame_bgr.copy(), (TILE_W, TILE_H))
    if roi:
        # scale roi to tile size
        sx, sy = TILE_W / w_orig, TILE_H / h_orig
        rx1 = int(roi[0] * sx); ry1 = int(roi[1] * sy)
        rx2 = int(roi[2] * sx); ry2 = int(roi[3] * sy)
        cv2.rectangle(orig_disp, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)
        cv2.putText(orig_disp, "ROI", (rx1 + 4, ry1 + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    # ── Tile 2: ROI crop ─────────────────────────────────────────────────────
    roi_crop, _ = crop_roi(frame_bgr, roi)
    roi_disp = cv2.resize(roi_crop, (TILE_W, TILE_H))

    # ── Base: resize roi for processing ──────────────────────────────────────
    base = cv2.resize(roi_crop, (TILE_W, TILE_H))
    gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)

    # ── Tile 3: Grayscale ─────────────────────────────────────────────────────
    gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # ── Tile 4: Threshold ─────────────────────────────────────────────────────
    _, thresh = cv2.threshold(gray, threshold_value, 255, cv2.THRESH_BINARY)
    thresh_bgr = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    # ── Tile 5: Canny Edge ────────────────────────────────────────────────────
    edges = cv2.Canny(gray, canny_low, canny_high)
    edge_bgr = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    # ── Tile 6: Motion mask OR Laplacian ─────────────────────────────────────
    if motion_mask is not None:
        mask_resized = cv2.resize(motion_mask, (TILE_W, TILE_H))
        tile6 = cv2.cvtColor(mask_resized, cv2.COLOR_GRAY2BGR)
        label6 = "6. MOTION MASK"
    else:
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        lap_norm = cv2.normalize(np.abs(lap), None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        tile6 = cv2.cvtColor(lap_norm, cv2.COLOR_GRAY2BGR)
        label6 = "6. LAPLACIAN"

    def label(tile: np.ndarray, text: str) -> np.ndarray:
        canvas = tile.copy()
        cv2.rectangle(canvas, (0, 0), (TILE_W, 30), (30, 30, 30), -1)
        cv2.putText(canvas, text, (8, 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1)
        return canvas

    tiles = [
        label(orig_disp,  "1. ORIGINAL + ROI"),
        label(roi_disp,   "2. ROI CROP"),
        label(gray_bgr,   "3. GRAYSCALE"),
        label(thresh_bgr, f"4. THRESHOLD={threshold_value}"),
        label(edge_bgr,   f"5. CANNY {canny_low}/{canny_high}"),
        label(tile6,      label6),
    ]

    row1 = np.hstack(tiles[:3])
    row2 = np.hstack(tiles[3:])
    sheet = np.vstack([row1, row2])

    out_path = PROCESSED_DIR / f"{image_id}_advanced_steps.jpg"
    cv2.imwrite(str(out_path), sheet)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    # Stats computed on ROI region
    brightness = round(compute_brightness(roi_crop), 2)
    blur = round(compute_blur_score(roi_crop), 2)
    stats = {
        "brightness": brightness,
        "blur_score": blur,
        "width": int(frame_bgr.shape[1]),
        "height": int(frame_bgr.shape[0]),
        "roi_width": int(roi_crop.shape[1]),
        "roi_height": int(roi_crop.shape[0]),
    }
    return out_path, elapsed_ms, stats


def log_image_pipeline_advanced(
    frame_bgr: np.ndarray,
    source_type: str,
    device_id: str,
    note: str = "",
    roi: Optional[Tuple[int,int,int,int]] = None,
    threshold_value: int = 120,
    canny_low: int = 80,
    canny_high: int = 160,
    motion_mask: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Pipeline nâng cao: lưu ảnh gốc, contact sheet 6 ô, metadata, event chất lượng."""
    image_id = f"img_{uuid.uuid4().hex[:10]}"
    timestamp = now_iso()

    raw_path = RAW_DIR / f"{image_id}.jpg"
    cv2.imwrite(str(raw_path), frame_bgr)

    processed_path, processing_time_ms, stats = create_advanced_contact_sheet(
        frame_bgr, image_id,
        roi=roi,
        threshold_value=threshold_value,
        canny_low=canny_low,
        canny_high=canny_high,
        motion_mask=motion_mask,
    )

    metadata_row = {
        "image_id": image_id,
        "device_id": device_id,
        "timestamp": timestamp,
        "source_type": source_type,
        "image_path": str(raw_path.relative_to(ROOT)),
        "processed_path": str(processed_path.relative_to(ROOT)),
        "width": stats["width"],
        "height": stats["height"],
        "brightness": stats["brightness"],
        "blur_score": stats["blur_score"],
        "processing_status": "processed",
        "processing_time_ms": processing_time_ms,
        "note": note,
    }
    append_csv(METADATA_CSV, METADATA_FIELDS, metadata_row)

    event_row = event_from_quality(image_id, stats["brightness"], stats["blur_score"])
    append_csv(EVENT_CSV, EVENT_FIELDS, event_row)

    return {
        "image_id": image_id,
        "metadata": metadata_row,
        "event": event_row,
        "raw_image_url": relative_url(raw_path),
        "processed_image_url": relative_url(processed_path),
        "stats": stats,
    }


def log_param_experiment(
    image_id: str,
    roi: Optional[Tuple[int,int,int,int]],
    threshold_value: int,
    canny_low: int,
    canny_high: int,
    motion_threshold: int,
    min_area: int,
    cooldown_sec: float,
    brightness: float,
    blur_score: float,
    motion_score: float,
    event_type: str,
    note: str = "",
) -> Dict[str, Any]:
    """Ghi một dòng vào parameter_experiment_log.csv."""
    row = {
        "exp_id": f"exp_{uuid.uuid4().hex[:8]}",
        "timestamp": now_iso(),
        "image_id": image_id,
        "roi_x1": roi[0] if roi else "",
        "roi_y1": roi[1] if roi else "",
        "roi_x2": roi[2] if roi else "",
        "roi_y2": roi[3] if roi else "",
        "threshold_value": threshold_value,
        "canny_low": canny_low,
        "canny_high": canny_high,
        "motion_threshold": motion_threshold,
        "min_area": min_area,
        "cooldown_sec": cooldown_sec,
        "brightness": round(brightness, 2),
        "blur_score": round(blur_score, 2),
        "motion_score": round(motion_score, 2),
        "event_type": event_type,
        "note": note,
    }
    append_csv(PARAM_CSV, PARAM_FIELDS, row)
    return row


# ─── Camera helpers ───────────────────────────────────────────────────────────
def parse_camera_source(source: str) -> Any:
    source = str(source).strip()
    return int(source) if source.isdigit() else source


def simulated_frame(counter: int = 0, width: int = 640, height: int = 360) -> np.ndarray:
    """Fallback frame khi không có camera thật."""
    frame = np.full((height, width, 3), 230, dtype=np.uint8)
    # gradient background
    for i in range(height):
        frame[i, :] = [max(30, 220 - i // 3), max(30, 190 - i // 4), max(30, 210 - i // 5)]

    x = 30 + (counter * 12) % max(1, width - 180)
    y = 80 + (counter * 7) % max(1, height - 170)
    cv2.rectangle(frame, (x, y), (x + 130, y + 120), (40, 140, 240), -1)
    cv2.circle(frame, (x + 65, y + 160), 40, (60, 200, 80), -1)
    cv2.putText(frame, f"SIMULATED frame={counter}", (10, height - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (20, 20, 20), 1)
    return frame


def open_capture(source: str) -> Optional[cv2.VideoCapture]:
    parsed = parse_camera_source(source)
    cap = cv2.VideoCapture(parsed)
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def read_one_frame(source: str) -> Tuple[np.ndarray, str]:
    cap = open_capture(source)
    if cap is None:
        return simulated_frame(0), "simulated"
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return simulated_frame(0), "simulated"
    return frame, "camera"


def stream_frames(source: str = "0") -> Iterable[bytes]:
    cap = open_capture(source)
    counter = 0
    while True:
        if cap is None:
            frame = simulated_frame(counter)
            source_label = "SIMULATED"
        else:
            ok, frame = cap.read()
            if not ok or frame is None:
                frame = simulated_frame(counter)
                source_label = "SIMULATED_AFTER_ERROR"
            else:
                source_label = "LIVE_CAMERA"

        cv2.rectangle(frame, (0, 0), (frame.shape[1], 30), (255, 255, 255), -1)
        cv2.putText(frame, f"{source_label} | source={source} | f={counter}",
                    (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 1)
        jpg = frame_to_jpeg_bytes(frame)
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
        counter += 1
        time.sleep(0.08)


def record_short_video(source: str, seconds: int = 5) -> Dict[str, Any]:
    seconds = max(1, min(int(seconds), 30))
    cap = open_capture(source)
    fps = 10
    width, height = 640, 360
    video_id = f"vid_{uuid.uuid4().hex[:10]}"
    out_path = VIDEO_DIR / f"{video_id}.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    frame_count = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        frame = simulated_frame(frame_count, width, height) if cap is None else (lambda ok, f: f if ok else simulated_frame(frame_count, width, height))(*cap.read())
        frame = cv2.resize(frame, (width, height))
        writer.write(frame)
        frame_count += 1
        time.sleep(1.0 / fps)
    if cap is not None:
        cap.release()
    writer.release()
    event_row = {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "image_id": video_id,
        "timestamp": now_iso(),
        "event_type": "VIDEO_RECORDED",
        "score": frame_count,
        "severity": "NORMAL",
        "explanation": f"Đã ghi video {seconds}s với {frame_count} frames.",
        "action_hint": "Dùng video để review sau hoặc trích frame cho Lab 7.",
        "rule_used": f"record_video seconds={seconds}",
    }
    append_csv(EVENT_CSV, EVENT_FIELDS, event_row)
    return {
        "video_id": video_id,
        "video_path": str(out_path.relative_to(ROOT)),
        "video_url": relative_url(out_path),
        "seconds": seconds,
        "frames": frame_count,
        "event": event_row,
    }


def motion_capture_advanced(
    source: str,
    seconds: int = 8,
    motion_threshold: int = 25,
    min_area: int = 800,
    cooldown_sec: float = 1.0,
    roi: Optional[Tuple[int,int,int,int]] = None,
    threshold_value: int = 120,
    canny_low: int = 80,
    canny_high: int = 160,
) -> Dict[str, Any]:
    """Motion capture nâng cao với cooldown, ROI, param logging."""
    global _last_motion_event_time

    seconds = max(1, min(int(seconds), 30))
    cap = open_capture(source)
    prev_gray = None
    best_frame = None
    best_score = 0.0
    best_mask = None
    frames_seen = 0
    start = time.perf_counter()

    while time.perf_counter() - start < seconds:
        frame = simulated_frame(frames_seen) if cap is None else (lambda ok, f: f if ok else simulated_frame(frames_seen))(*cap.read())
        frames_seen += 1

        # crop ROI for motion analysis
        roi_frame, _ = crop_roi(frame, roi)
        gray = cv2.cvtColor(cv2.resize(roi_frame, (320, 240)), cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            diff = cv2.absdiff(prev_gray, gray)
            _, mask = cv2.threshold(diff, motion_threshold, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            score = float(sum(cv2.contourArea(c) for c in contours if cv2.contourArea(c) >= min_area))
            if score > best_score:
                best_score = score
                best_frame = frame.copy()
                best_mask = mask.copy()
        prev_gray = gray
        time.sleep(0.08)

    if cap is not None:
        cap.release()
    if best_frame is None:
        best_frame = simulated_frame(frames_seen)

    motion_detected = best_score >= float(min_area)

    # ── Cooldown check ──────────────────────────────────────────────────────
    now = time.time()
    suppressed = False
    if motion_detected and cooldown_sec > 0:
        if now - _last_motion_event_time < cooldown_sec:
            motion_detected = False  # suppressed by cooldown
            suppressed = True
    if motion_detected:
        _last_motion_event_time = now

    # ── Log image pipeline ──────────────────────────────────────────────────
    result = log_image_pipeline_advanced(
        best_frame, source_type="motion_capture", device_id=f"camera:{source}",
        note=f"motion_score={round(best_score,2)}, threshold={motion_threshold}, min_area={min_area}, cooldown={cooldown_sec}",
        roi=roi,
        threshold_value=threshold_value,
        canny_low=canny_low,
        canny_high=canny_high,
        motion_mask=best_mask,
    )

    # ── Motion event ────────────────────────────────────────────────────────
    if suppressed:
        event_type = "MOTION_SUPPRESSED_COOLDOWN"
        severity = "NORMAL"
        expl = f"Chuyển động phát hiện nhưng cooldown {cooldown_sec}s chưa hết."
        hint = f"Cooldown còn {round(cooldown_sec - (now - _last_motion_event_time), 1)}s."
        rule = f"motion_score={round(best_score,2)} >= min_area={min_area} nhưng cooldown active"
    elif motion_detected:
        event_type = "MOTION_DETECTED"
        severity = "WARNING"
        expl = f"Frame diff score={round(best_score,2)} >= min_area={min_area}. Chuyển động đáng kể."
        hint = "Xem ảnh chụp và motion mask. Điều chỉnh min_area nếu bị false positive."
        rule = f"motion_score >= min_area={min_area} AND threshold={motion_threshold}"
    else:
        event_type = "NO_SIGNIFICANT_MOTION"
        severity = "NORMAL"
        expl = f"Không phát hiện chuyển động đáng kể. score={round(best_score,2)} < min_area={min_area}."
        hint = "Giảm motion_threshold hoặc min_area nếu muốn nhạy hơn."
        rule = f"motion_score < min_area={min_area}"

    motion_event = {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "image_id": result["image_id"],
        "timestamp": now_iso(),
        "event_type": event_type,
        "score": round(best_score, 2),
        "severity": severity,
        "explanation": expl,
        "action_hint": hint,
        "rule_used": rule,
    }
    append_csv(EVENT_CSV, EVENT_FIELDS, motion_event)

    # ── Parameter experiment log ────────────────────────────────────────────
    param_row = log_param_experiment(
        image_id=result["image_id"],
        roi=roi,
        threshold_value=threshold_value,
        canny_low=canny_low,
        canny_high=canny_high,
        motion_threshold=motion_threshold,
        min_area=min_area,
        cooldown_sec=cooldown_sec,
        brightness=result["stats"]["brightness"],
        blur_score=result["stats"]["blur_score"],
        motion_score=best_score,
        event_type=event_type,
        note=f"frames_seen={frames_seen}, suppressed={suppressed}",
    )

    result.update({
        "motion_event": motion_event,
        "motion_detected": motion_detected,
        "motion_score": round(best_score, 2),
        "frames_seen": frames_seen,
        "suppressed_by_cooldown": suppressed,
        "param_experiment": param_row,
    })
    return result


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Lab 6 Nâng cao - Computer Vision as IoT Sensor",
    description="ROI, threshold, edge, blur, motion score, cooldown, parameter experiment log."
)
app.mount("/files", StaticFiles(directory=str(ROOT)), name="files")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(INDEX_HTML)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "lab": "Lab 6 Nâng cao",
        "outputs": {
            "metadata_csv": str(METADATA_CSV.relative_to(ROOT)),
            "event_csv": str(EVENT_CSV.relative_to(ROOT)),
            "param_csv": str(PARAM_CSV.relative_to(ROOT)),
        }
    }


@app.get("/video_feed")
def video_feed(source: str = Query("0")) -> StreamingResponse:
    return StreamingResponse(stream_frames(source), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/snapshot")
def snapshot(
    source: str = Query("0"),
    roi_x1: Optional[int] = None, roi_y1: Optional[int] = None,
    roi_x2: Optional[int] = None, roi_y2: Optional[int] = None,
    threshold_value: int = Query(120, ge=0, le=255),
    canny_low: int = Query(80, ge=1, le=254),
    canny_high: int = Query(160, ge=2, le=255),
) -> Dict[str, Any]:
    frame, source_type = read_one_frame(source)
    roi = (roi_x1, roi_y1, roi_x2, roi_y2) if all(v is not None for v in [roi_x1, roi_y1, roi_x2, roi_y2]) else None
    result = log_image_pipeline_advanced(
        frame, source_type=source_type, device_id=f"camera:{source}",
        note=f"snapshot | threshold={threshold_value} | canny={canny_low}/{canny_high} | roi={roi}",
        roi=roi, threshold_value=threshold_value, canny_low=canny_low, canny_high=canny_high,
    )
    # Log param experiment for snapshot
    log_param_experiment(
        image_id=result["image_id"], roi=roi,
        threshold_value=threshold_value, canny_low=canny_low, canny_high=canny_high,
        motion_threshold=0, min_area=0, cooldown_sec=0,
        brightness=result["stats"]["brightness"], blur_score=result["stats"]["blur_score"],
        motion_score=0, event_type=result["event"]["event_type"], note="snapshot",
    )
    return result


@app.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    device_id: str = "upload_client",
    roi_x1: Optional[int] = None, roi_y1: Optional[int] = None,
    roi_x2: Optional[int] = None, roi_y2: Optional[int] = None,
    threshold_value: int = Query(120, ge=0, le=255),
    canny_low: int = Query(80, ge=1, le=254),
    canny_high: int = Query(160, ge=2, le=255),
) -> Dict[str, Any]:
    data = await file.read()
    img = validate_image_bytes(data)
    roi = (roi_x1, roi_y1, roi_x2, roi_y2) if all(v is not None for v in [roi_x1, roi_y1, roi_x2, roi_y2]) else None
    result = log_image_pipeline_advanced(
        pil_to_bgr(img), source_type="upload", device_id=device_id,
        note=f"filename={file.filename} | threshold={threshold_value} | canny={canny_low}/{canny_high} | roi={roi}",
        roi=roi, threshold_value=threshold_value, canny_low=canny_low, canny_high=canny_high,
    )
    log_param_experiment(
        image_id=result["image_id"], roi=roi,
        threshold_value=threshold_value, canny_low=canny_low, canny_high=canny_high,
        motion_threshold=0, min_area=0, cooldown_sec=0,
        brightness=result["stats"]["brightness"], blur_score=result["stats"]["blur_score"],
        motion_score=0, event_type=result["event"]["event_type"], note=f"upload:{file.filename}",
    )
    return result


@app.get("/record-video")
def record_video(source: str = Query("0"), seconds: int = Query(5, ge=1, le=30)) -> Dict[str, Any]:
    return record_short_video(source, seconds=seconds)


@app.get("/motion-capture")
def motion_capture_endpoint(
    source: str = Query("0"),
    seconds: int = Query(8, ge=1, le=30),
    threshold: int = Query(25, ge=1, le=255),
    min_area: int = Query(800, ge=10, le=50000),
    cooldown: float = Query(1.0, ge=0, le=60),
    roi_x1: Optional[int] = None, roi_y1: Optional[int] = None,
    roi_x2: Optional[int] = None, roi_y2: Optional[int] = None,
    threshold_value: int = Query(120, ge=0, le=255),
    canny_low: int = Query(80, ge=1, le=254),
    canny_high: int = Query(160, ge=2, le=255),
) -> Dict[str, Any]:
    roi = (roi_x1, roi_y1, roi_x2, roi_y2) if all(v is not None for v in [roi_x1, roi_y1, roi_x2, roi_y2]) else None
    return motion_capture_advanced(
        source, seconds=seconds, motion_threshold=threshold, min_area=min_area,
        cooldown_sec=cooldown, roi=roi,
        threshold_value=threshold_value, canny_low=canny_low, canny_high=canny_high,
    )


@app.get("/metadata")
def metadata_endpoint(limit: int = 20) -> Dict[str, Any]:
    rows = read_csv(METADATA_CSV)
    return {"count": len(rows), "items": rows[-limit:]}


@app.get("/events")
def events_endpoint(limit: int = 20) -> Dict[str, Any]:
    rows = read_csv(EVENT_CSV)
    return {"count": len(rows), "items": rows[-limit:]}


@app.get("/param-experiments")
def param_experiments(limit: int = 20) -> Dict[str, Any]:
    rows = read_csv(PARAM_CSV)
    return {"count": len(rows), "items": rows[-limit:]}


@app.get("/latest")
def latest_endpoint() -> Dict[str, Any]:
    meta_rows = read_csv(METADATA_CSV)
    event_rows = read_csv(EVENT_CSV)
    param_rows = read_csv(PARAM_CSV)
    latest_meta = meta_rows[-1] if meta_rows else None
    raw_url = processed_url = None
    if latest_meta:
        raw_url = relative_url(ROOT / latest_meta.get("image_path", ""))
        processed_url = relative_url(ROOT / latest_meta.get("processed_path", ""))
    return {
        "latest_metadata": latest_meta,
        "latest_event": event_rows[-1] if event_rows else None,
        "latest_param": param_rows[-1] if param_rows else None,
        "raw_image_url": raw_url,
        "processed_image_url": processed_url,
        "metadata_count": len(meta_rows),
        "event_count": len(event_rows),
        "param_count": len(param_rows),
    }


if __name__ == "__main__":
    frame = simulated_frame(1)
    result = log_image_pipeline_advanced(
        frame, source_type="script", device_id="smoke_test",
        note="python app.py direct smoke test",
        threshold_value=120, canny_low=80, canny_high=160,
    )
    print(json.dumps({"image_id": result["image_id"], "event": result["event"]["event_type"]}, indent=2, ensure_ascii=False))
