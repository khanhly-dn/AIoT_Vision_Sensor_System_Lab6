# Câu hỏi hiểu bản chất Lab 6

1. Vì sao camera có thể được xem là một cảm biến trong hệ thống AIoT?
    Một cảm biến, về bản chất, là thiết bị chuyển một hiện tượng vật lý (nhiệt độ, độ ẩm, ánh sáng...) thành dữ liệu số để hệ thống xử lý. Camera cũng làm đúng việc đó: nó chuyển ánh sáng phản chiếu từ môi trường thành ma trận pixel (dữ liệu số). Khác biệt duy nhất là dữ liệu đầu ra của camera có cấu trúc phức tạp hơn (ảnh 2 chiều, nhiều kênh màu) thay vì một con số đơn lẻ như cảm biến nhiệt độ. Vì vậy trong kiến trúc AIoT, camera hoàn toàn có thể đóng vai trò một node cảm biến, miễn là hệ thống có tầng xử lý phù hợp để "đọc hiểu" loại dữ liệu này.
2. Ảnh khác telemetry số ở những điểm nào?
    Telemetry số (VD nhiệt độ = 25.3°C) là dữ liệu vô hướng (scalar) — chỉ 1 giá trị đơn, có thể so sánh trực tiếp bằng phép toán cơ bản (lớn hơn/nhỏ hơn ngưỡng). Ảnh là dữ liệu đa chiều, dung lượng lớn (VD 640×480×3 = hơn 900,000 giá trị cho 1 ảnh), không thể "đọc thẳng" ý nghĩa mà phải qua bước xử lý trung gian (grayscale, threshold, tính brightness/blur...) mới rút ra được thông tin có ý nghĩa. Ngoài ra ảnh mang ngữ cảnh không gian (vị trí pixel này so với pixel khác có ý nghĩa), trong khi 1 số telemetry thì không.
3. Vì sao cần lưu metadata cho mỗi ảnh?
    Ảnh gốc chỉ là dữ liệu thô — nếu không đi kèm metadata (brightness, blur_score, timestamp, source_type...) thì sau này muốn biết "ảnh này chụp lúc nào, chất lượng ra sao, từ nguồn nào" sẽ phải mở lại từng ảnh và tính toán lại. Metadata giúp:
- Tra cứu nhanh mà không cần load ảnh
- Thống kê xu hướng theo thời gian (VD độ sáng trung bình theo giờ trong ngày)
- Làm dữ liệu đầu vào cho các bước xử lý tiếp theo (lọc ảnh chất lượng thấp trước khi đưa vào model AI)
4. Vì sao không nên chỉ lưu ảnh mà không ghi `device_id` và `timestamp`?
    Nếu hệ thống có nhiều camera (nhiều device_id) mà không ghi rõ ảnh đến từ thiết bị nào, ta không thể truy vết được sự cố xảy ra ở camera nào khi có nhiều nguồn cùng gửi ảnh về. Thiếu timestamp thì không thể sắp xếp lại đúng trình tự thời gian, không tính được khoảng cách giữa các sự kiện (VD để phát hiện chuyển động cần biết frame nào chụp trước, frame nào chụp sau), và không thể đối chiếu ảnh với các sự kiện khác trong hệ thống (log, cảnh báo...) xảy ra cùng lúc.
5. Resize, grayscale, threshold và edge làm thay đổi ảnh như thế nào?
- Resize: thay đổi kích thước ảnh (VD về 640×480) để chuẩn hóa dữ liệu đầu vào, giảm dung lượng xử lý, đảm bảo mọi ảnh có cùng kích thước để so sánh/xử lý đồng nhất.
- Grayscale: gộp 3 kênh màu (R, G, B) thành 1 kênh độ sáng duy nhất theo công thức trọng số 0.299R + 0.587G + 0.114B, vì các bước sau (threshold, edge) chỉ làm việc được trên 1 kênh số.
- Threshold: so mỗi điểm ảnh xám với 1 ngưỡng cố định — trên ngưỡng thành trắng, dưới ngưỡng thành đen, biến ảnh xám thành ảnh nhị phân, giúp tách vùng sáng/tối hoặc vật thể/nền rõ ràng hơn.
- Edge (Canny): tìm những nơi độ sáng thay đổi đột ngột giữa các điểm ảnh liền kề (đó chính là đường viền vật thể), cho ra ảnh chỉ còn các đường biên mảnh trên nền đen.
6. Motion capture có phải object detection không? Vì sao?
    Không. Motion capture chỉ so sánh 2 frame liên tiếp bằng phép trừ tuyệt đối (absdiff) để tìm những vùng pixel có thay đổi giá trị vượt ngưỡng — nó chỉ biết "có cái gì đó thay đổi ở vùng này" chứ hoàn toàn không biết vật thể đó là gì (người, xe, con vật...). Object detection cần một mô hình học máy (như YOLO) đã được huấn luyện để nhận diện và phân loại cụ thể từng loại vật thể, kèm vẽ khung bao (bounding box) quanh vật thể đó. Đây chính là lý do Lab 6 chỉ dừng ở phát hiện chuyển động, còn phần nhận diện vật thể để dành cho Lab 7.
7. Khi camera quá tối, event nào nên được sinh ra?
    Event LOW_LIGHT — được sinh ra khi giá trị brightness trung bình của ảnh thấp hơn ngưỡng quy định (trong code Lab 6 là brightness < 60). Event này giúp hệ thống tự động cảnh báo rằng ảnh chụp được có thể không đủ chất lượng để dùng cho các bước xử lý tiếp theo (như object detection ở Lab 7), thay vì âm thầm xử lý một ảnh không có giá trị sử dụng.
8. Nếu stream IP camera không truy cập được, hệ thống cần có cơ chế dự phòng nào?
    Hệ thống cần cơ chế fallback tự động — khi không kết nối được tới IP camera/RTSP URL, tự động chuyển sang dùng ảnh mô phỏng (simulated_frame()) để pipeline vẫn tiếp tục hoạt động, không bị dừng hoàn toàn (crash) chỉ vì mất kết nối tới 1 thiết bị ngoại vi. Đây là nguyên tắc "graceful degradation" (giảm cấp có kiểm soát) rất quan trọng trong hệ thống IoT thực tế, nơi thiết bị phần cứng có thể mất kết nối bất cứ lúc nào.
9. Dashboard giúp kiểm tra pipeline ảnh tốt hơn việc chỉ xem file CSV như thế nào?
    File CSV chỉ hiển thị số liệu thô (brightness=155.4, blur=141.2...) — muốn biết ảnh thực tế trông ra sao, có đúng là ảnh mờ hay không, phải tự tưởng tượng từ con số. Dashboard hiển thị trực quan cả ảnh lẫn số liệu cùng lúc (contact sheet 6 ô, ảnh gốc, bảng metadata/event), giúp người dùng đối chiếu ngay: "à, blur_score=65 tương ứng với ảnh mờ như thế này" — dễ phát hiện lỗi logic (VD threshold đặt sai khiến ảnh rõ bị đánh giá nhầm là mờ) mà chỉ nhìn số trong CSV sẽ khó nhận ra. 
10. Lab 6 chuẩn bị dữ liệu gì cho Lab 7 Object Detection?
    Lab 6 tạo ra ảnh đã được lọc chất lượng và có metadata đi kèm — nguồn dữ liệu đầu vào sạch cho Lab 7. Cụ thể:
- Ảnh trong raw_images/ đã được xác nhận đạt chất lượng tối thiểu (không tối, không quá mờ) qua event IMAGE_QUALITY_OK
- Metadata (brightness, blur_score, timestamp, source) giúp Lab 7 có thể lọc trước những ảnh không đủ tiêu chuẩn trước khi đưa vào model detection, tránh lãng phí tài nguyên chạy AI trên ảnh xấu
- Cơ chế ROI đã xây dựng sẵn cũng có thể tái sử dụng để giới hạn vùng cần chạy object detection, giúp tăng tốc độ xử lý ở Lab 7