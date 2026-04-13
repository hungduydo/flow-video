# 🎬 Frame Review & Verification

## Tính năng mới: Lưu frames cục bộ để kiểm tra

Khi chạy Step 7 (banner generation), tất cả candidate frames sẽ được tự động lưu vào thư mục `frames_review/` trong output directory. Điều này cho phép bạn:

1. **So sánh trực quan** các frames được trích xuất cùng với điểm quality score của chúng
2. **Xác minh quyết định của LLM** — kiểm tra liệu LLM có chọn frame tốt nhất không
3. **Điều chỉnh thủ công** nếu muốn thay đổi quyết định của LLM

## Cấu trúc Output

```
output/BVxxxxxx/
├── frames_review/                    # 📁 Thư mục mới
│   ├── frame_00_score_0.XXX.jpg      # Frame #0 (top candidate)
│   ├── frame_01_score_0.XXX.jpg      # Frame #1
│   ├── frame_02_score_0.XXX.jpg      # Frame #2
│   ├── ...
│   ├── candidates_metadata.json      # 📋 Metadata JSON (scores, LLM decision)
│   └── preview.html                  # 🎨 Interactive HTML gallery
├── banner_youtube.jpg                # Final banner (1280×720)
├── banner_tiktok.jpg                 # Final banner (1080×1920)
└── ...
```

## Cách sử dụng

### 1. **Xem Gallery Online**
```bash
# Mở file HTML trong trình duyệt (macOS)
open output/BVxxxxxx/frames_review/preview.html

# Hoặc trên Linux
xdg-open output/BVxxxxxx/frames_review/preview.html
```

### 2. **Kiểm tra Candidates Metadata**
```bash
cat output/BVxxxxxx/frames_review/candidates_metadata.json
```

**Ví dụ output:**
```json
{
  "candidates": [
    {
      "index": 0,
      "filename": "frame_00_score_0.876.jpg",
      "score": 0.876,
      "timestamp": 45.32
    },
    {
      "index": 1,
      "filename": "frame_01_score_0.812.jpg",
      "score": 0.812,
      "timestamp": 32.15
    }
  ],
  "llm_decision": {
    "chosen_frame_index": 0,
    "title": "Một câu trích dẫn hay",
    "video_title": "Video gốc"
  }
}
```

### 3. **Đánh giá Frames**
- **Frames được sắp xếp theo chất lượng** (brightness, contrast, colorfulness)
- **Green checkmark** ✓ = LLM đã chọn frame này
- **Quality score** = 0–1 (cao hơn = tốt hơn)

### 4. **Thay đổi Quyết định (Manual Override)**
Nếu bạn không đồng ý với LLM:

```bash
# 1. Xác định frame ID mà bạn muốn (từ preview.html)
# 2. Edit metadata và cập nhật chosen_frame_index
$ nano output/BVxxxxxx/frames_review/candidates_metadata.json

# 3. Chạy compose lại với frame index mới
python -m pipeline.step7_banner --override-frame-index 2
```

## Quality Score Giải thích

Mỗi frame được scoring dựa trên:
- **Brightness (25%)** — Ưu tiên frames có độ sáng vừa phải (không quá tối/sáng)
- **Contrast (35%)** — Độ chênh lệch sáng tối (texture tốt hơn)
- **Colorfulness (40%)** — Độ bão hòa màu sắc (hình ảnh sống động)

### Giá trị điển hình:
- `0.85–1.00` — Rất tốt ✨
- `0.70–0.84` — Tốt ✓
- `0.50–0.69` — Tạm được
- `< 0.50` — Không lý tưởng

## Workflow Khuyến nghị

1. **Chạy Step 7** → Tạo frames_review/
2. **Mở preview.html** → Xem tất cả candidates
3. **So sánh với LLM decision** → Đồng ý hay không?
4. **Nếu không đồng ý** → Manual override hoặc adjust LLM prompt
5. **Final banner** sẽ được compose từ frame đã chọn

## Tips & Tricks

- 🎬 **Scene-based candidates** — Nếu `scenes.json` tồn tại, LLM sẽ ưu tiên frames ở giữa các scene (có visual variety)
- 🎨 **Dramatic frames** — LLM được prompt tìm frames có "high contrast, clear subject, dynamic action"
- 📊 **Score consistency** — Nếu top 3 frames có score tương tự, chúng có chất lượng tương đương nhau
- 🔄 **Rerunning** — Delete `.step7.done` file để rerun step 7 với metadata mới

## File Structure

Trong `frames_review/`:
- **frame_XY_score_Z.jpg** — Frame index XY, quality score Z
- **candidates_metadata.json** — Tất cả info (scores, timestamps, LLM decision)
- **preview.html** — Beautiful gallery để review (load locally trong browser)

---

**💡 Tip:** Nếu bạn thường xuyên không hài lòng với LLM's choice, hãy điều chỉnh system prompt trong `step7_banner/main.py` để describe tốt hơn cái gì là "best frame" cho use case của bạn.
