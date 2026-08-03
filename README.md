# 🎥 AIoT Vision Sensor System — Lab 6 (Computer Vision as IoT Sensor)

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
![OpenCV](https://img.shields.io/badge/OpenCV-Image_Processing-5C3EE8?logo=opencv)
![Uvicorn](https://img.shields.io/badge/Uvicorn-ASGI_Server-222222)
![Dashboard](https://img.shields.io/badge/Dashboard-HTML%2FJS-orange)

**Đưa camera/ảnh vào hệ thống AIoT như một cảm biến trực quan**
Live stream → Snapshot/Upload → ROI/Threshold/Canny → Blur & Brightness → Motion Detection → Metadata/Event Log → Dashboard

</div>

---

## 📌 Tổng quan

Một cảm biến nhiệt độ hay độ ẩm chỉ trả về một con số đơn lẻ. Camera cũng là một cảm biến, nhưng dữ liệu trả về là ảnh — một ma trận pixel nhiều chiều cần được xử lý trước khi hệ thống AIoT có thể "hiểu" được ý nghĩa của nó. Lab 6 xây dựng một pipeline thị giác máy tính nhập môn để biến camera/ảnh thành một node cảm biến thực thụ trong hệ thống AIoT: chạy được live stream, chụp ảnh, ghi video, phát hiện chuyển động, xử lý ảnh cơ bản (ROI, grayscale, threshold, Canny edge), tính chỉ số chất lượng ảnh (brightness, blur score), ghi metadata/event, và quan sát toàn bộ qua một dashboard HTML.

> **Câu hỏi trung tâm:** Camera/ảnh có thể trở thành một cảm biến trong hệ thống AIoT như thế nào, và dữ liệu đó cần được xử lý, ghi log ra sao để dùng được cho các bước tiếp theo (như Object Detection ở Lab 7)?

```
Camera thật / ảnh mô phỏng (fallback nếu không có camera)
  → Snapshot / Upload / Motion Capture qua dashboard
  → Backend FastAPI (app.py) nhận request
  → Crop ROI → Grayscale → Threshold (tunable) → Canny edge (tunable)
  → Tính brightness, blur score → so ngưỡng → sinh event
  → Lưu ảnh gốc, contact sheet 6 ô, video ngắn
  → Ghi image_metadata.csv, image_event_log.csv, parameter_experiment_log.csv
  → Trả kết quả JSON, dashboard tự cập nhật ảnh & bảng dữ liệu
```

---

## 🏗️ Cấu trúc project

```
AIoT_Vision_Sensor_System_Lab6/
├── app.py                      # Backend FastAPI: stream, snapshot, video, motion, preprocess, metadata, event
├── index.html                  # Dashboard: stream, upload ảnh, ROI, tham số, quan sát ảnh/metadata/event
├── run_lab6_demo.py             # Chạy thử nhanh pipeline không cần camera thật
├── requirements.txt             # Danh sách thư viện
├── docs/                        # Câu hỏi hiểu bản chất, checklist, rubric, phân tích code
├── outputs/                     # image_metadata.csv, image_event_log.csv, parameter_experiment_log.csv
├── data/                        # raw_images/, processed_images/, videos/ (không push lên Git)
├── picture/                     # Ảnh minh chứng chạy thực tế
└── RUN_TEST_LOG.txt              # Log kết quả smoke test
```

---

## ⚙️ Cài đặt & chạy nhanh

```bash
# 1. Clone repository
git clone https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6.git
cd AIoT_Vision_Sensor_System_Lab6

# 2. Tạo môi trường ảo
python -m venv .venv

# 3. Kích hoạt (Windows)
.venv\Scripts\activate

# 3. Kích hoạt (macOS/Linux/WSL)
source .venv/bin/activate

# 4. Cài thư viện
pip install -r requirements.txt

# 5. Chạy smoke test không cần camera thật
python run_lab6_demo.py

# 6. Chạy dashboard
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Mở trình duyệt tại:
```
http://127.0.0.1:8000/          → Dashboard
http://127.0.0.1:8000/docs      → Swagger UI
```

### Kết quả thực tế — smoke test & server khởi động

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/SDHD.png?raw=true" alt="Terminal chạy smoke test và khởi động uvicorn" width="450"/>
</p>

`python run_lab6_demo.py` trả về `LOCAL_PIPELINE_TEST_PASS` — toàn bộ pipeline (2 frame quality check, ROI, threshold sweep, Canny sweep, ghi video, 3 cấu hình motion capture) chạy không lỗi ngay cả khi không có camera thật, nhờ cơ chế fallback sang ảnh mô phỏng. Sau đó `uvicorn app:app --reload` khởi động thành công với log `Application startup complete`.

---

## 🖥️ Giao diện Dashboard

Dashboard cho phép điều khiển toàn bộ pipeline chỉ bằng thao tác chuột: chọn nguồn camera, kéo ROI, chỉnh threshold ảnh xám, chỉnh cặp tham số Canny edge, chỉnh 3 tham số motion detection (diff threshold / min area / cooldown), và các nút hành động Snapshot / Video 5s / Motion Capture.

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/GDC.png?raw=true" alt="Giao diện điều khiển camera và tham số thử nghiệm" width="850"/>
</p>

Mọi tham số trên dashboard (threshold, Canny low/high, ROI, motion config) đều được áp dụng trực tiếp vào lần Snapshot/Upload/Motion Capture tiếp theo, không cần sửa code hay khởi động lại server.

---

## 📤 Upload ảnh & xử lý thực tế

Ngoài camera/ảnh mô phỏng, dashboard hỗ trợ upload trực tiếp một ảnh có sẵn để kiểm thử pipeline với dữ liệu thật thay vì ảnh giả lập — tham số ROI, threshold, Canny ở phần điều khiển phía trên sẽ được áp dụng ngay lên ảnh vừa upload.

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/GD_CODE.png?raw=true" alt="Upload ảnh và xem ảnh gốc mới nhất" width="850"/>
</p>

---

## 🧪 Contact sheet 6 ô — trực quan hóa toàn bộ pipeline xử lý ảnh

Mỗi lần Snapshot/Upload/Motion Capture, hệ thống ghép 6 bước xử lý vào một ảnh duy nhất để quan sát trực tiếp thay vì phải mở 6 file rời rạc:

1. **Original + ROI** — ảnh gốc, khung xanh đánh dấu vùng ROI đang chọn
2. **ROI crop** — vùng ảnh được cắt riêng để tính brightness/blur
3. **Grayscale** — chuyển 3 kênh màu về 1 kênh độ sáng
4. **Threshold (tunable)** — phân ngưỡng nhị phân theo giá trị đang chỉnh trên dashboard
5. **Canny edge (tunable)** — dò biên theo cặp low/high đang chỉnh
6. **Motion mask / Laplacian** — nền cho bước phát hiện chuyển động và đo độ nét

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/Contact%20sheet.png?raw=true" alt="Contact sheet 6 ô xử lý ảnh nâng cao" width="850"/>
</p>

---

## 💾 Dữ liệu được lưu trữ

Sau khi chạy, dữ liệu được ghi vào 3 thư mục con trong `data/`:

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/data.png?raw=true" alt="Cấu trúc thư mục data" width="500"/>
</p>

| Thư mục | Nội dung |
|---|---|
| `data/raw_images/` | Ảnh gốc từ snapshot/upload/motion capture |
| `data/processed_images/` | Contact sheet 6 ô đã xử lý |
| `data/videos/` | Video ngắn ghi từ camera hoặc stream mô phỏng |

> Thư mục `data/` chứa ảnh/video thật nên **không được push lên Git** (đã khai báo trong `.gitignore`) để tránh public dữ liệu cá nhân không cần thiết.

---

## 📊 Metadata & Event log

Mỗi ảnh sau khi xử lý được ghi lại số liệu (`brightness`, `blur_score`, `timestamp`, `source_type`...) và một event vận hành tương ứng (`IMAGE_QUALITY_OK`, `LOW_LIGHT`, `BLURRY_IMAGE`, `MOTION_DETECTED`, `VIDEO_RECORDED`...), kèm giải thích rõ nghĩa bằng tiếng Việt ngay trên dashboard.

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/JSON_Metadata_Event.png?raw=true" alt="Bảng Metadata ảnh và Event log" width="850"/>
</p>

Trong lần chạy thực tế, hệ thống ghi nhận một event `MOTION_DETECTED` với `score = 16476.5` (vượt xa `min_area = 800`) khi có chuyển động rõ rệt trước camera — minh chứng cơ chế so khớp 2 frame liên tiếp hoạt động đúng.

---

## ⚗️ Parameter Experiment Log & Quick Param Sweep

Mỗi lần Snapshot/Upload/Motion Capture với bất kỳ bộ tham số nào cũng được ghi thành một dòng log riêng trong `parameter_experiment_log.csv`, giúp so sánh ảnh hưởng của từng tham số (threshold, Canny low/high, motion threshold, min area, cooldown) lên brightness/blur/event. Ngoài ra dashboard có sẵn 3 nút **Quick Param Sweep** để tự động thử một loạt giá trị threshold/Canny/motion mà không cần bấm tay từng lần.

<p align="center">
  <img src="https://github.com/khanhly-dn/AIoT_Vision_Sensor_System_Lab6/blob/main/picture/Parameter%20Experiment_Quick%20Param%20Sweep.png?raw=true" alt="Parameter Experiment Log và Quick Param Sweep" width="850"/>
</p>

---

## 🧠 Câu hỏi hiểu bản chất (tóm tắt)

Chi tiết đầy đủ nằm trong [`docs/CAU_HOI_HIEU_BAN_CHAT.md`](docs/CAU_HOI_HIEU_BAN_CHAT.md). Một số điểm mấu chốt:

| Câu hỏi | Trả lời tóm tắt |
|---|---|
| Camera có phải cảm biến không? | Có — cả hai đều chuyển hiện tượng vật lý thành dữ liệu số, camera chỉ khác ở việc dữ liệu trả về đa chiều (ảnh) thay vì một giá trị đơn (telemetry) |
| Vì sao cần metadata? | Để tra cứu chất lượng/thời điểm ảnh mà không cần mở lại từng file, và làm đầu vào lọc dữ liệu cho các bước sau |
| Motion capture có phải object detection không? | Không — motion capture chỉ so sánh 2 frame để tìm vùng thay đổi, không biết vật thể đó là gì; object detection cần model đã huấn luyện để phân loại |
| Khi ảnh quá tối thì sinh event gì? | `LOW_LIGHT`, khi brightness dưới ngưỡng quy định |
| Lab 6 chuẩn bị gì cho Lab 7? | Ảnh đã lọc chất lượng (`IMAGE_QUALITY_OK`) kèm metadata, làm dữ liệu đầu vào sạch cho Object Detection |

---

## ✅ Checklist sản phẩm

| Sản phẩm | Trạng thái |
|---|---|
| Dashboard chạy được tại `http://127.0.0.1:8000/` | ✅ |
| Live stream / stream mô phỏng hiển thị | ✅ |
| Snapshot / Upload ảnh xử lý thành công | ✅ |
| Ghi video ngắn (`data/videos/`) | ✅ |
| Motion capture với nhiều bộ tham số | ✅ |
| Contact sheet 6 bước xử lý ảnh | ✅ |
| `outputs/image_metadata.csv` | ✅ |
| `outputs/image_event_log.csv` | ✅ |
| `outputs/parameter_experiment_log.csv` | ✅ |
| Trả lời 10 câu hỏi hiểu bản chất | ✅ |

---


## 🛠️ Công nghệ sử dụng

| Công nghệ | Vai trò |
|---|---|
| Python 3.11 | Ngôn ngữ chính |
| FastAPI | Backend, Swagger UI tự sinh |
| Uvicorn | ASGI server chạy FastAPI |
| OpenCV (opencv-python-headless) | Xử lý ảnh: crop ROI, grayscale, threshold, Canny, motion diff |
| NumPy | Xử lý ma trận ảnh |
| Pillow | Đọc/ghi ảnh upload |
| HTML/CSS/JavaScript | Dashboard quan sát trực tiếp |

---

## 💡 Kết luận & bài học

| Quan sát | Kết luận |
|---|---|
| Pipeline chạy `LOCAL_PIPELINE_TEST_PASS` ngay cả khi không có camera | Cơ chế fallback sang ảnh mô phỏng giúp hệ thống không phụ thuộc cứng vào phần cứng, phù hợp tinh thần "graceful degradation" trong AIoT thực tế |
| ROI giúp tách vùng cần phân tích khỏi nền | Giảm nhiễu và tăng tốc xử lý khi chỉ quan tâm một khu vực cụ thể trong khung hình |
| Threshold/Canny chỉ chạy được trên ảnh xám | Grayscale là bước bắt buộc để gộp 3 kênh màu về 1 kênh trước khi áp các thuật toán phân ngưỡng/dò biên |
| Motion capture chỉ phát hiện *có thay đổi*, không phải *thay đổi là gì* | Đây chính là ranh giới rõ ràng giữa Lab 6 (cảm biến thị giác) và Lab 7 (Object Detection) |
| Metadata + Event tách biệt rõ ràng | Metadata mô tả đặc tính ảnh (số liệu đo được), Event diễn giải ý nghĩa vận hành (ảnh có dùng được không, có cần cảnh báo không) |

> ⚠️ **Lưu ý:** Đây là bài lab học thuật với mục tiêu minh họa nguyên lý computer-vision-as-sensor trong AIoT, không phải hệ thống giám sát an ninh sản xuất — các ngưỡng brightness/blur/motion trong code là giá trị minh họa, cần hiệu chỉnh lại nếu áp dụng vào môi trường thật.

---

<div align="center">
  <sub>Lab 6 — Computer Vision as IoT Sensor · Triển khai, phát triển ứng dụng AI và IoT</sub>
</div>
