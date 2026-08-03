"""
run_lab6_advanced_demo.py
Smoke test cho Lab 6 Nâng cao - không cần camera thật, không cần server web.

Khi chạy:
    python run_lab6_advanced_demo.py

Kết quả cần thấy:
    RUN_TEST_LOG.txt → LOCAL_PIPELINE_TEST_PASS
    data/raw_images/       → ảnh gốc
    data/processed_images/ → contact sheet 6 ô (original+ROI, gray, threshold, edge, mask)
    outputs/image_metadata.csv
    outputs/image_event_log.csv
    outputs/parameter_experiment_log.csv  ← CÁI MỚI
"""

from pathlib import Path
import json

from app import (
    ROOT, VIDEO_DIR, EVENT_CSV, EVENT_FIELDS,
    PARAM_CSV, PARAM_FIELDS,
    append_csv, log_image_pipeline_advanced, log_param_experiment,
    simulated_frame, record_short_video, motion_capture_advanced,
)

log_lines = []
all_pass = True

try:
    # ── Bước 1: Thử hai frame không ROI (giống Lab 6 cơ bản) ─────────────────
    for i in range(2):
        frame = simulated_frame(i)
        result = log_image_pipeline_advanced(
            frame,
            source_type="demo_script",
            device_id="simulated_camera",
            note=f"demo_frame={i}",
            threshold_value=120,
            canny_low=80,
            canny_high=160,
        )
        log_lines.append(f"[FRAME {i}] image_id={result['image_id']} event={result['event']['event_type']} brightness={result['stats']['brightness']} blur={result['stats']['blur_score']}")

    # ── Bước 2: Frame có ROI (vùng trung tâm) ────────────────────────────────
    frame_roi = simulated_frame(5)
    h, w = frame_roi.shape[:2]
    roi = (w//4, h//4, 3*w//4, 3*h//4)  # vùng 50% trung tâm
    result_roi = log_image_pipeline_advanced(
        frame_roi,
        source_type="demo_script",
        device_id="simulated_camera",
        note="ROI center 50%",
        roi=roi,
        threshold_value=120,
        canny_low=80,
        canny_high=160,
    )
    log_lines.append(f"[ROI] image_id={result_roi['image_id']} roi={roi} event={result_roi['event']['event_type']}")

    # ── Bước 3: Thử nhiều giá trị threshold ──────────────────────────────────
    for thresh in [80, 120, 180]:
        frame_t = simulated_frame(10 + thresh)
        r = log_image_pipeline_advanced(
            frame_t,
            source_type="param_experiment",
            device_id="simulated_camera",
            note=f"threshold_test={thresh}",
            threshold_value=thresh,
            canny_low=80,
            canny_high=160,
        )
        log_param_experiment(
            image_id=r["image_id"], roi=None,
            threshold_value=thresh, canny_low=80, canny_high=160,
            motion_threshold=25, min_area=800, cooldown_sec=1.0,
            brightness=r["stats"]["brightness"], blur_score=r["stats"]["blur_score"],
            motion_score=0, event_type=r["event"]["event_type"],
            note=f"threshold_sweep thresh={thresh}",
        )
        log_lines.append(f"[THRESH={thresh}] brightness={r['stats']['brightness']} blur={r['stats']['blur_score']} event={r['event']['event_type']}")

    # ── Bước 4: Thử nhiều bộ Canny edge ──────────────────────────────────────
    for cl, ch in [(50, 100), (80, 160), (150, 250)]:
        frame_c = simulated_frame(20 + cl)
        r = log_image_pipeline_advanced(
            frame_c,
            source_type="param_experiment",
            device_id="simulated_camera",
            note=f"canny_test={cl}/{ch}",
            threshold_value=120,
            canny_low=cl,
            canny_high=ch,
        )
        log_param_experiment(
            image_id=r["image_id"], roi=None,
            threshold_value=120, canny_low=cl, canny_high=ch,
            motion_threshold=25, min_area=800, cooldown_sec=1.0,
            brightness=r["stats"]["brightness"], blur_score=r["stats"]["blur_score"],
            motion_score=0, event_type=r["event"]["event_type"],
            note=f"canny_sweep {cl}/{ch}",
        )
        log_lines.append(f"[CANNY={cl}/{ch}] event={r['event']['event_type']}")

    # ── Bước 5: Ghi video ngắn ────────────────────────────────────────────────
    video_result = record_short_video("no_camera_fallback", seconds=1)
    log_lines.append(f"[VIDEO] video_id={video_result['video_id']} frames={video_result['frames']}")

    # ── Bước 6: Motion capture 3 cấu hình ────────────────────────────────────
    configs = [
        {"motion_threshold": 15, "min_area": 500,  "cooldown_sec": 0},
        {"motion_threshold": 25, "min_area": 800,  "cooldown_sec": 1},
        {"motion_threshold": 40, "min_area": 1500, "cooldown_sec": 5},
    ]
    for cfg in configs:
        mr = motion_capture_advanced(
            "no_camera_fallback",
            seconds=1,
            **cfg,
            threshold_value=120,
            canny_low=80,
            canny_high=160,
        )
        log_lines.append(
            f"[MOTION threshold={cfg['motion_threshold']} min_area={cfg['min_area']} cooldown={cfg['cooldown_sec']}] "
            f"score={mr['motion_score']} event={mr['motion_event']['event_type']} suppressed={mr['suppressed_by_cooldown']}"
        )

    status = "LOCAL_PIPELINE_TEST_PASS"

except Exception as exc:
    status = f"LOCAL_PIPELINE_TEST_FAIL: {exc}"
    log_lines.append(status)
    all_pass = False

# ── Ghi log ───────────────────────────────────────────────────────────────────
log_content = status + "\n" + "\n".join(log_lines)
Path("RUN_TEST_LOG.txt").write_text(log_content, encoding="utf-8")

print(status)
print()
for line in log_lines:
    print(line)
print()
print("─" * 70)
print("Quan sát sau khi chạy:")
print("  data/raw_images/                  → ảnh gốc")
print("  data/processed_images/            → contact sheet 6 ô nâng cao")
print("  data/videos/                      → video ngắn")
print("  outputs/image_metadata.csv        → metadata ảnh (+ blur_score)")
print("  outputs/image_event_log.csv       → event (LOW_LIGHT, BLURRY, MOTION...)")
print("  outputs/parameter_experiment_log.csv  ← LOG THỬ THAM SỐ")
print("  RUN_TEST_LOG.txt                  → trạng thái test này")
