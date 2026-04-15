# 📋 PRD: Advanced Banner & Thumbnail Generation Pipeline

**Version:** 1.0  
**Status:** Draft  
**Date:** April 2026  
**Owner:** Flow Video Pipeline  

---

## 📌 Executive Summary

Upgrade banner/thumbnail generation from basic frame selection to an **intelligent, content-aware system** that:
- Intelligently extracts & filters video frames (blur detection, saturation scoring)
- Analyzes frame content (face/object detection, saliency mapping)
- Applies AI to select optimal frame + title (LLM decision)
- **Smart-crops frames** to preserve visual focal points when changing aspect ratios
- **Auto-designs graphics** with contrast-aware text, color matching, and adaptive layouts
- **Exports optimized** formats (.webp, .webm, .mp4) for different platforms

**Expected Outcomes:**
- 🎯 Select best visual frames with 90%+ consistency with manual review
- 🔍 Preserve subject focus through intelligent cropping (no head cuts)
- ✨ Professional-grade banners with auto-adjusted design elements
- 📦 Format-optimized exports for web/YouTube/TikTok

---

## 🎯 Problem Statement

**Current State:**
- Step 7 (Banner) uses basic quality scoring (brightness, contrast, colorfulness)
- Random frame sampling across video (no scene awareness)
- No content analysis (faces, objects, saliency)
- Naive cropping/composition (may cut off important subjects)
- Text overlay + design is manual or template-based

**Pain Points:**
1. ❌ Sometimes picks "technically high-quality" but visually boring frames
2. ❌ When cropping from 16:9 to 21:9, important elements (faces, text) often get cut
3. ❌ Text readability suffers when overlaid on complex backgrounds
4. ❌ Thumbnails look generic; no automatic color harmony or subject-aware layout
5. ❌ Exports are not optimized for platform (file size, format, dimensions)

**Why It Matters:**
- **YouTube/TikTok CTR** depends on thumbnail visual appeal
- **Viewer retention** depends on whether banner accurately represents content
- **Processing efficiency** requires filtering out blurry/low-quality frames early

---

## 🎬 Goals

### Primary Goals
1. **Maximize visual quality** — Extract only sharp, vibrant, well-lit frames
2. **Content-aware selection** — LLM picks most visually dramatic + relevant frame
3. **Preserve focal points** — Smart cropping keeps faces/objects in optimal positions
4. **Professional design** — Auto text placement, contrast, + color matching
5. **Platform-optimized** — Export formats + dimensions tailored per platform

### Success Criteria
- ✅ Blur-filtered candidates reduce processing by 30–40% (fewer frames analyzed)
- ✅ Saliency + face detection improves subject-aware cropping by 85%+ (vs. center-crop)
- ✅ LLM + content analysis achieves 90%+ satisfaction rate vs. manual review
- ✅ Generated banners pass visual QA without manual tweaks
- ✅ Export file size < 500KB (webp) / < 2MB (mp4) without quality loss

---

## 📐 Detailed Requirements by Phase

### **Phase 1: Candidate Extraction & Filtering**

#### 1.1 Frame Sampling
**Requirement:** Extract keyframes at regular intervals, prioritizing high-quality shots.

| Feature | Spec | Implementation |
|---------|------|-----------------|
| **Sample Rate** | Every 0.5s–1s (configurable) | `cv2.VideoCapture` with `CAP_PROP_POS_MSEC` |
| **Max Frames** | Cap at 30 frames/video (memory efficient) | Dedup by second bucket |
| **Source** | Prefer middle 60–80% of video | Skip intro/outro ~10s each end |
| **Scene-aware** | Use `scenes.json` midpoints if available | Extract frame at each scene boundary |

**Output:** `candidates_raw[]` = list of (frame, timestamp, source) tuples

---

#### 1.2 Blur Detection (Laplacian Variance)
**Requirement:** Discard blurry frames early to reduce processing.

| Feature | Spec | Threshold | Notes |
|---------|------|-----------|-------|
| **Blur Metric** | Laplacian variance | `< 100` → reject | `cv2.Laplacian(gray, cv2.CV_64F).var()` |
| **Processing** | Convert to grayscale first | N/A | Variance on Laplacian edges |
| **Action** | Log filtered out frames | Per-frame JSON | For debugging |

**Pseudo-code:**
```python
gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
if laplacian_var < 100:
    skip(frame, reason="blur")
```

**Expected Impact:** Remove 25–40% of frames, focus on sharp shots.

---

#### 1.3 Saturation-Based Aesthetic Filtering
**Requirement:** Prioritize vibrant, colorful frames over dull/grayscale ones.

| Feature | Spec | Notes |
|---------|------|-------|
| **Color Space** | HSV (Hue, Saturation, Value) | `cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)` |
| **Score** | Mean of S channel | `np.mean(hsv[:, :, 1]) / 255.0` → 0–1 |
| **Weight** | Part of overall quality score | Saturation × 40% (+ brightness, contrast) |
| **Min Threshold** | Saturation > 0.25 (optional) | Discard extremely desaturated frames |

**Output:** `candidates_scored[]` = sorted by (saturation_score + brightness + contrast)

---

### **Phase 2: Content Analysis (AI-Powered)**

#### 2.1 Object & Face Detection
**Requirement:** Locate key subjects in frame for smart cropping + composition.

| Component | Tool | Output | Use Case |
|-----------|------|--------|----------|
| **Face Detection** | MediaPipe Face | `[{x, y, w, h, confidence}]` | Prioritize if face present |
| **Object Detection** | YOLO v8 (lightweight) | `[{class, bbox, confidence}]` | Fallback; detect phones, text, scenes |
| **Selection** | Face > YOLO | 1–3 bboxes per frame | Rank by confidence |

**API Contract:**
```python
def detect_subjects(frame) -> dict:
    return {
        "faces": [{"x": int, "y": int, "w": int, "h": int, "confidence": float}],
        "objects": [{"class": str, "bbox": (x, y, w, h), "confidence": float}],
        "primary_subject": {"type": "face|object", "bbox": (x,y,w,h)}
    }
```

**Fallback:** If no subjects detected, use saliency map (Phase 2.2).

---

#### 2.2 Saliency Mapping
**Requirement:** Find visually interesting regions even without faces/objects.

| Feature | Spec | Implementation |
|---------|------|-----------------|
| **Algorithm** | Spectral Residual (static) | `cv2.saliency.StaticSaliencySpectralResidual_create()` |
| **Output** | Saliency map (0–255) | Heatmap of visual attention |
| **Usage** | Find highest-attention regions | Centroid of top-N% pixels |
| **Fallback** | If no faces detected | Use saliency center as focus point |

**Pseudo-code:**
```python
saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
(success, saliency_map) = saliency.computeSaliency(frame)
saliency_map = (saliency_map * 255).astype("uint8")
# Find center of top-20% pixels
top_mask = cv2.threshold(saliency_map, int(255 * 0.8), 255, cv2.THRESH_BINARY)[1]
M = cv2.moments(top_mask)
cx = int(M["m10"] / M["m00"]) if M["m00"] != 0 else frame.shape[1] // 2
cy = int(M["m01"] / M["m00"]) if M["m00"] != 0 else frame.shape[0] // 2
```

**Output:** `saliency_center = (cx, cy)`

---

#### 2.3 LLM Integration (Gemini/Claude)
**Requirement:** Send top 3–5 frames to LLM for final content-aware decision.

| Feature | Spec | Notes |
|---------|------|-------|
| **Model** | Gemini 2.0 Flash or Claude Sonnet | Cost-optimized; fast inference |
| **Candidates** | Top 3–5 by quality score | Reduce API cost; still diverse |
| **Encoding** | Base64 JPEG (85% quality) | ~50–100KB each |
| **Prompt** | System: "Select most visually dramatic, eye-catching frame" | Include context: video title, first 3 captions |
| **Input Format** | `{"frames": [b64_1, b64_2, ...], "context": {...}}` | JSON payload |
| **Output Format** | `{"frame_index": int, "title": str, "reasoning": str}` | Structured JSON |

**System Prompt Template:**
```
You are a YouTube/TikTok thumbnail expert. Given {N} candidate frames from a video:

Video: {title}
Context: {caption_excerpt}

1. Select the frame that is most visually dramatic, eye-catching, and curious.
   Consider: facial expression, action, contrast, composition, emotional appeal.
2. Generate a punchy 4–7 word Vietnamese hook title that creates curiosity/urgency.

Return ONLY valid JSON:
{"frame_index": <0 to N-1>, "title": "<Vietnamese title>", "reasoning": "<brief explanation>"}
```

**Error Handling:**
- If LLM fails → fallback to index 0 (highest quality score)
- If JSON parse fails → retry up to 2 times
- Log all LLM decisions for audit trail

**Output:** `selected_frame_idx, hook_title`

---

### **Phase 3: Smart Cropping for Aspect Ratio Changes**

#### 3.1 Aspect Ratio Transformation
**Requirement:** Intelligently crop from source aspect (16:9) to target (21:9 or custom).

| Platform | Source | Target | Mapping | Strategy |
|----------|--------|--------|---------|----------|
| YouTube | 16:9 | 16:9 | Identity | No crop needed |
| TikTok | 16:9 | 9:16 (portrait) | Rotate + center | Vertical center-crop |
| Banner Web | 16:9 | 21:9 (ultrawide) | Horizontal pan | Subject-aware crop |

**Math:**
```
Input: W=1920, H=1080 (16:9)
Target: 21:9 (W_new = 2352, H_new = 1080 for same height)
→ But usually scale-fit: H_target = 720, W_target = 1680 (21:9 at HD)
Crop Y: depends on subject position (see 3.2 below)
```

---

#### 3.2 Subject-Aware Y-Coordinate Calculation
**Requirement:** Position crop to keep focal points in optimal frame positions.

**Algorithm:**

| Case | Detection | Y Calculation | Reasoning |
|------|-----------|-----------------|-----------|
| **Face detected** | `face.y, face.h` | Target face center at 1/3 from top | "Looking room" composition rule |
| **Object/saliency** | `subject_cx, subject_cy` | Center saliency on vertical midline | Balance empty space |
| **Fallback** | None | Center crop (vertical midpoint) | Safest default |

**Formula:**
```python
# Face case:
face_eye_y = face.y + face.h * 0.35  # Eyes are ~35% down face bbox
target_y = frame_height * 0.33  # Rule of thirds
crop_y = face_eye_y - target_y
crop_y = max(0, min(crop_y, frame_height - crop_height))

# Saliency case:
crop_y = saliency_cy - crop_height // 2
crop_y = max(0, min(crop_y, frame_height - crop_height))
```

**Output:** `crop_rect = (x_start, y_start, crop_width, crop_height)`

---

#### 3.3 Motion Smoothing (for Video Sequences)
**Requirement:** If exporting a banner *video*, smooth Y-coordinate jitter.

| Feature | Spec | Notes |
|---------|------|-------|
| **Filter Type** | Moving average (N-frame window) | N = 5–15 frames |
| **Apply To** | crop_y coordinate across frames | Prevents sudden jumps |
| **Output** | Smooth keyframe offsets | Linear interpolation between anchor points |

**Pseudo-code:**
```python
crop_y_values = [calculate_crop_y(f) for f in video_frames]
smoothed_y = moving_average(crop_y_values, window_size=5)
```

---

### **Phase 4: Automated Graphic Design**

#### 4.1 Negative Space & Auto Layout
**Requirement:** Dynamically position text based on subject location.

| Detection | Text Position | Reasoning |
|-----------|---------------|-----------:|
| Subject on **left** (center_x < W/3) | Right side | Avoid overlap |
| Subject on **right** (center_x > 2W/3) | Left side | Avoid overlap |
| Subject **center** | Bottom region | Standard composition |
| No subject | Bottom center | Default safe zone |

**Implementation:**
```python
primary_subject = detect_subjects(frame)["primary_subject"]
if primary_subject:
    subject_cx = primary_subject["bbox"][0] + primary_subject["bbox"][2] // 2
    if subject_cx < frame_width / 3:
        text_align = "right"  # Position text right
        text_x = frame_width * 0.85
    elif subject_cx > 2 * frame_width / 3:
        text_align = "left"
        text_x = frame_width * 0.05
    else:
        text_align = "center"
        text_x = frame_width // 2
else:
    text_align = "center"
    text_x = frame_width // 2
```

---

#### 4.2 Text Rendering with Contrast Overlay
**Requirement:** Ensure text is always readable, regardless of background.

| Component | Spec | Implementation |
|-----------|------|-----------------|
| **Overlay** | Semi-transparent black gradient | Pillow `Image.new("RGBA")` with alpha |
| **Gradient** | Bottom-to-transparent (140px height) | `Image.paste()` with mask |
| **Opacity** | 60–80% | Adjust by background brightness |
| **Font** | Google Fonts: Inter Bold / Montserrat Bold | Size: 60–80px (HD resolution) |
| **Fallback Outline** | White shadow/stroke (if low contrast) | Minimum 2px black outline |

**Logic:**
```python
def create_contrast_overlay(frame, height=140, opacity=0.7):
    """Create semi-transparent black gradient at bottom."""
    overlay = Image.new("RGBA", (frame.shape[1], frame.shape[0]), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (frame.shape[1], height))
    
    for y in range(height):
        alpha = int(255 * opacity * (y / height))  # Fade to transparent
        gradient.paste((0, 0, 0, alpha), (0, y, frame.shape[1], y+1))
    
    overlay.paste(gradient, (0, frame.shape[0] - height), gradient)
    return overlay
```

---

#### 4.3 Automatic Color Matching
**Requirement:** Extract dominant colors from frame and use for UI accents.

| Step | Technique | Output | Use |
|------|-----------|--------|-----|
| **1. Dominant Color Extraction** | K-Means (k=3–5) on frame pixels | Top 3 colors | Primary palette |
| **2. Select Accent** | Highest saturation color OR high-contrast | 1 accent color | Text underline, border |
| **3. Text Color** | White or black (check contrast ratio) | Readable text | Auto-select based on bg |
| **4. Accent Elements** | Bars, icons, border, subtitle | Accent color | Provide visual cohesion |

**Implementation:**
```python
def extract_dominant_colors(frame, k=5):
    """K-Means clustering to find dominant colors."""
    pixels = frame.reshape((-1, 3)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    centers = np.uint8(centers)
    # Sort by frequency
    unique, counts = np.unique(labels, return_counts=True)
    sorted_colors = centers[unique[np.argsort(-counts)]]
    return sorted_colors

def get_accent_color(frame):
    """Get highest-saturation color for accents."""
    colors = extract_dominant_colors(frame, k=5)
    hsv_colors = cv2.cvtColor(np.array([colors]), cv2.COLOR_BGR2HSV)[0]
    saturations = hsv_colors[:, 1]
    accent = colors[np.argmax(saturations)]
    return tuple(accent)
```

---

#### 4.4 Text Composition
**Requirement:** Render multi-line title with auto-wrapping and sizing.

| Feature | Spec | Notes |
|---------|------|-------|
| **Title Length** | 4–7 words (Vietnamese) | ~40–60 chars max |
| **Font Size** | Auto-scale (60–80px) | Fit within safe area |
| **Line Wrapping** | Break at word boundaries | Max 2–3 lines |
| **Positioning** | Dynamic (from Phase 4.1) | Left, right, or center |
| **Shadows/Outline** | 2–3px black stroke | Ensure readability |

**Pseudo-code:**
```python
title = hook_title  # "Cách này sẽ thay đổi cuộc sống"
font_size = 70
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("Montserrat-Bold.ttf", font_size)

# Auto-wrap text
max_width = img.width * 0.8
lines = wrap_text(title, font, max_width)

# Draw with outline
for line in lines:
    draw_text_with_outline(draw, line, (text_x, text_y), 
                          font=font, fill=(255,255,255), 
                          outline_width=2, outline_fill=(0,0,0))
    text_y += font_size + 10  # Line spacing
```

---

### **Phase 5: Export & Optimization**

#### 5.1 Format Selection by Platform
**Requirement:** Export in optimal format for each platform.

| Platform | Format | Codec | Resolution | Bitrate | Size Estimate |
|----------|--------|-------|------------|---------|-----------------|
| **YouTube Thumbnail** | .webp | VP8 | 1280×720 | N/A | 200–300KB |
| **YouTube Banner** | .jpg / .webp | JPEG / VP8 | 2560×1440 | N/A | 300–500KB |
| **TikTok Cover** | .webp / .mp4 | VP8 / H.264 | 1080×1920 | 500kbps–2Mbps | 100KB–2MB |
| **Web Preview** | .webp | VP8 | 1280×720 (responsive) | N/A | 150–250KB |

---

#### 5.2 WebP Compression (Static Images)
**Requirement:** Generate highly optimized WebP files.

| Parameter | Value | Tool | Notes |
|-----------|-------|------|-------|
| **Quality** | 85–90 | PIL/Pillow | Balances size + quality |
| **Method** | 6 (slowest, best) | Pillow kwarg | `method=6` |
| **Lossless** | False | Pillow kwarg | Use lossy for thumbnails |

**Implementation:**
```python
from PIL import Image
img = Image.open("banner.jpg")
img.save("banner.webp", "WEBP", quality=85, method=6)
# Expected: ~1280×720 → 200KB
```

---

#### 5.3 FFmpeg Integration (Video Sequences)
**Requirement:** Composite banner into short video clips (6–15 sec) if needed.

| Task | Command Pattern | Notes |
|------|-----------------|-------|
| **Static → MP4** | ` ffmpeg -loop 1 -i banner.jpg -t 10 -c:v libx264 -pix_fmt yuv420p output.mp4` | 10-second loop |
| **Audio Fade-In** | `-af afade=t=in:st=0:d=1` | Smooth audio intro |
| **Bitrate Target** | `-b:v 2500k` | YouTube safe bitrate |
| **Aspect Ratio** | `-vf "scale=1280:720"` | Enforce output dimensions |

**Subprocess call:**
```python
import subprocess
subprocess.run([
    "ffmpeg", "-y",
    "-loop", "1",
    "-i", "banner.jpg",
    "-t", "10",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-b:v", "2500k",
    "output.mp4"
])
```

---

#### 5.4 File Size & Quality Checks
**Requirement:** Validate output meets platform requirements.

| Check | Threshold | Action |
|-------|-----------|--------|
| **WebP Size** | < 500KB | Pass ✅ |
| **MP4 Size** | < 2MB (for 10sec) | Pass ✅ |
| **Image Dimensions** | Matches target | Verify aspect ratio |
| **Color Space** | sRGB / YUV420 | Standard web-safe |

**Validation logic:**
```python
output_size_mb = Path("output.webp").stat().st_size / (1024 * 1024)
if output_size_mb > 0.5:
    print(f"⚠️  Warning: {output_size_mb:.2f}MB exceeds 500KB target")
else:
    print(f"✅ {output_size_mb * 1024:.0f}KB")
```

---

## 🏗️ Technical Architecture

### System Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                    VIDEO INPUT                                  │
│              (final_youtube.mp4 / final_tiktok.mp4)             │
└────────────────┬────────────────────────────────────────────────┘
                 │
        ┌────────▼────────┐
        │  PHASE 1: Extract & Filter
        │  - Sampling (0.5s intervals)
        │  - Blur detection (Laplacian)
        │  - Saturation scoring
        └────────┬────────┘
                 │
        ┌────────▼────────────┐
        │ PHASE 2: Content Analysis
        │ - Face/Object detect (YOLO, MediaPipe)
        │ - Saliency mapping
        │ - LLM decision (Gemini)
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │ PHASE 3: Smart Cropping
        │ - Subject-aware crop_y
        │ - Motion smoothing (if video)
        │ - Preserve focal points
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │ PHASE 4: Design
        │ - Color extraction (K-Means)
        │ - Text layout (avoid subject)
        │ - Contrast overlay
        │ - Rendering (Pillow)
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │ PHASE 5: Export
        │ - Format selection
        │ - WebP compression
        │ - FFmpeg (if video)
        │ - Size validation
        └────────┬────────────┘
                 │
        ┌────────▼────────────┐
        │  OUTPUT
        │  ✅ banner_youtube.webp (or .jpg)
        │  ✅ banner_tiktok.webp
        │  ✅ metadata.json
        │  ✅ frames_review/
        └────────────────────┘
```

---

### File Structure

```
pipeline/step7_banner/
├── main.py                    # Orchestrator
├── frames.py                  # Phase 1: Extraction & filtering
├── content_analysis.py        # Phase 2: Object detection, saliency, LLM
├── smart_crop.py              # Phase 3: Cropping + subject tracking
├── design.py                  # Phase 4: Color matching, text rendering
├── export.py                  # Phase 5: WebP, MP4, validation
├── config.py                  # Settings (thresholds, font paths, etc.)
├── prompts.py                 # LLM system prompts
├── frames_review/             # Output: preview.html + candidate images
└── fonts/
    ├── Montserrat-Bold.ttf
    └── Inter-Bold.ttf
```

---

## 📦 Dependencies & Libraries

### New Dependencies (to add to `requirements.txt`)

```
# Core dependencies
opencv-python>=4.8.0          # Blur detection, saliency, color analysis
opencv-contrib-python>=4.8.0  # cv2.saliency module
mediapipe>=0.10.0              # Face/hand detection
ultralytics>=8.0.0             # YOLO v8 (object detection)
pillow>=10.0.0                 # Image composition, rendering
numpy>=1.24.0                  # Array operations

# LLM Integration (already in project)
# anthropic>=0.7.0             # Claude API (if using)
# google-generativeai>=0.3.0   # Gemini API (if using)

# Optimization
scikit-image>=0.21.0           # Additional image processing
ffmpeg-python>=0.2.1           # FFmpeg wrapper (optional; can use subprocess)

# (Optional but recommended)
Pillow-SIMD>=9.0.0             # Faster PIL operations (if available)
```

---

## 🔄 Processing Pipeline (Detailed Flow)

### Pseudocode: Main Orchestrator

```python
def generate_smart_banner(output_dir, platform="both"):
    """End-to-end banner generation."""
    
    # ─── Phase 1: Extract & Filter ────────────────────────
    frames_raw = extract_frames_by_sampling(
        video_path=output_dir / "final_youtube.mp4",
        sample_interval=0.5
    )
    frames_sharp = filter_blur(frames_raw, threshold=100)
    frames_scored = score_by_saturation(frames_sharp)
    top_candidates = frames_scored[:5]
    
    # ─── Phase 2: Content Analysis ─────────────────────
    for frame in top_candidates:
        subjects = detect_subjects(frame)  # Faces + YOLO
        saliency = compute_saliency(frame)
        frame.metadata = {
            "subjects": subjects,
            "saliency_center": saliency,
        }
    
    llm_choice = call_llm_for_frame_selection(top_candidates)
    selected_idx = llm_choice["frame_index"]
    hook_title = llm_choice["title"]
    
    # ─── Phase 3: Smart Crop ───────────────────────────
    crop_rect = compute_subject_aware_crop(
        top_candidates[selected_idx],
        target_aspect_ratio=21/9
    )
    cropped_frame = crop_image(top_candidates[selected_idx], crop_rect)
    
    # ─── Phase 4: Design ──────────────────────────────
    colors = extract_dominant_colors(cropped_frame)
    accent_color = colors[highest_saturation]
    
    designed_banner = render_banner(
        base_image=cropped_frame,
        title=hook_title,
        colors={"accent": accent_color},
        subject=top_candidates[selected_idx].metadata["subjects"]
    )
    
    # ─── Phase 5: Export ──────────────────────────────
    export_webp(designed_banner, output_dir / f"banner_{platform}.webp", quality=85)
    if platform in ["youtube", "both"]:
        export_jpg(designed_banner, output_dir / "banner_youtube.jpg", quality=95)
    
    # Save metadata
    save_metadata({
        "selected_frame_idx": selected_idx,
        "title": hook_title,
        "crop_rect": crop_rect,
        "colors_used": colors,
    })
    
    return output_dir / f"banner_{platform}.webp"
```

---

## 📊 Data Structures

### Frame Metadata
```json
{
  "frame_id": 0,
  "timestamp": 5.5,
  "source": "sample",
  "blur_score": 245.3,
  "blur_passed": true,
  "saturation_score": 0.68,
  "quality_composite": 0.82,
  "subjects": {
    "faces": [
      {
        "bbox": [100, 50, 80, 100],
        "confidence": 0.95,
        "landmarks": {}
      }
    ],
    "objects": [
      {
        "class": "phone",
        "bbox": [300, 200, 150, 250],
        "confidence": 0.87
      }
    ],
    "primary_subject": {
      "type": "face",
      "bbox": [100, 50, 80, 100]
    }
  },
  "saliency": {
    "center_x": 420,
    "center_y": 380,
    "map": "..."
  }
}
```

### LLM Request/Response
```json
{
  "request": {
    "frames": ["base64_1", "base64_2", ...],
    "context": {
      "video_title": "Cách kiếm tiền online",
      "captions": "Hôm nay tôi sẽ hướng dẫn bạn..."
    }
  },
  "response": {
    "frame_index": 0,
    "title": "Kiếm 10 triệu/tháng từ nhà",
    "reasoning": "Strong eye contact, bright background, confident expression"
  }
}
```

### Export Metadata
```json
{
  "banner": {
    "source_frame_idx": 0,
    "source_timestamp": 5.5,
    "crop_rect": [0, 140, 1280, 720],
    "target_resolution": "1280x720",
    "target_aspect": "16:9",
    "title": "Kiếm 10 triệu/tháng từ nhà",
    "colors_used": {
      "primary": [245, 120, 50],
      "accent": [0, 200, 150],
      "text": [255, 255, 255]
    },
    "export_formats": {
      "webp": {
        "size_mb": 0.28,
        "quality": 85
      },
      "jpg": {
        "size_mb": 0.35,
        "quality": 95
      }
    }
  }
}
```

---

## 🧪 Testing Strategy

### Unit Tests (Phase-by-phase)

| Phase | Test Case | Expected | Priority |
|-------|-----------|----------|----------|
| **1-Blur** | cv2.Laplacian variance detection | Sharp frames pass, blurry < 25% | HIGH |
| **1-Saturation** | HSV saturation scoring | Colorful frames > 0.6 score | HIGH |
| **2-Face Detection** | MediaPipe on known faces | 95%+ accuracy on standard dataset | MEDIUM |
| **2-Saliency** | Spectral Residual on objects | Center-of-mass within 10% of true object center | MEDIUM |
| **3-Crop** | Subject-aware crop preservation | Face eyes stay in target zone (rule of thirds) | HIGH |
| **4-Color** | K-Means dominant color | Top color matches human perception | MEDIUM |
| **4-Text** | Contrast overlay + readability | WCAG AA contrast ratio (4.5:1) | HIGH |
| **5-WebP** | Compression ratio | < 500KB at 85% quality for 1280×720 | HIGH |

### Integration Tests

```python
def test_end_to_end_banner_generation():
    """Full pipeline on sample video."""
    output_dir = generate_smart_banner(test_video_path)
    
    assert (output_dir / "banner_youtube.webp").exists()
    assert (output_dir / "banner_tiktok.webp").exists()
    assert (output_dir / "metadata.json").exists()
    
    size_mb = (output_dir / "banner_youtube.webp").stat().st_size / (1024**2)
    assert size_mb < 0.5, f"WebP too large: {size_mb}MB"
    
    # Verify metadata
    metadata = json.loads((output_dir / "metadata.json").read_text())
    assert "selected_frame_idx" in metadata
    assert "title" in metadata
    assert "crop_rect" in metadata
```

### QA Checklist

- [ ] All frames extracted (no ValueError in OpenCV)
- [ ] Blur filter removes 25–40% of frames
- [ ] Highest-saturation frame is visually colorful
- [ ] LLM decision makes sense (reasonable title + frame selection)
- [ ] Cropped banner shows full face (if face present)
- [ ] Text is readable on all test cases (50 videos)
- [ ] Accent color matches visual dominant color
- [ ] WebP file size < 500KB, JPEG < 1MB
- [ ] Thumbnails look professional (no artifacts, text readable)

---

## ⏱️ Implementation Timeline

| Phase | Duration | Dependencies | Deliverables |
|-------|----------|--------------|--------------|
| **Phase 1: Filtering** | Week 1 | OpenCV | `frames.py` (blur + saturation) |
| **Phase 2: Content Analysis** | Week 2 | MediaPipe, YOLO, LLM API | `content_analysis.py` + system tests |
| **Phase 3: Smart Crop** | Week 1.5 | Phase 2 output | `smart_crop.py` + crop validation |
| **Phase 4: Design** | Week 2 | Pillow, color extraction | `design.py` + contrast QA |
| **Phase 5: Export** | Week 1 | FFmpeg, Pillow | `export.py` + size validation |
| **Integration & Polish** | Week 1 | All phases | End-to-end tests, documentation |
| **Total** | ~8 weeks | — | Production-ready system |

---

## 🎯 Success Metrics

### Quantitative
- ✅ **Blur filter efficacy:** Removes 25–40% of frames, reducing downstream processing
- ✅ **LLM + content match:** 90%+ user satisfaction vs. manual review (A/B test on 50 videos)
- ✅ **File size optimization:** WebP 70–80% smaller than JPEG equivalent
- ✅ **Subject preservation:** 95%+ of faces remain fully visible in cropped output
- ✅ **Processing speed:** < 30 seconds per video (5 fps on GPU-enabled machine)

### Qualitative
- ✅ Thumbnails feel professional (no generic/AI-slop aesthetics)
- ✅ Text is always readable (contrast passes WCAG AA)
- ✅ Color accents enhance composition (not jarring)
- ✅ Layout adapts to subject (left/right/center text placement)

---

## 🚨 Constraints & Assumptions

### Constraints
- 🔴 **GPU optional but recommended** — YOLO inference slower on CPU (~2sec/frame)
- 🔴 **LLM API costs** — ~$0.01–0.05 per banner (5 frames × 100KB ≈ 5–10M tokens)
- 🔴 **Face detection:** Works best for frontal/semi-frontal faces (mediaipe limitation)
- 🔴 **Text in Vietnamese:** Font must support Unicode (included in requirements)

### Assumptions
- ✅ Input video is already processed (audio separated, captions transcribed)
- ✅ `scenes.json` exists and is accurate (but optional fallback works without it)
- ✅ Output directory structure follows pipeline standards
- ✅ LLM API keys available (GEMINI_API_KEY or ANTHROPIC_API_KEY)
- ✅ FFmpeg installed system-wide (or vendored)

---

## 📝 Open Questions & Next Steps

### TBD (Refinement Needed)
1. **Blur threshold:** 100 is conservative. Profile on real videos to optimize detection rate.
2. **Saliency backup:** What if saliency map is empty? Default to center-crop or random?
3. **Multi-subject frames:** If multiple faces detected, which one to prioritize? (Largest? Central?)
4. **Banner variations:** Should we generate 3–5 design variations and let LLM/user pick?
5. **Branding:** How to include channel logo or watermark without compromising composition?

### Future Enhancements (Out of Scope)
- 🔮 **ML model for thumbnail appeal:** Train model on CTR data to predict thumbnail performance
- 🔮 **A/B testing framework:** Auto-generate 3 variants, test on platform API
- 🔮 **Real-time preview:** Live dashboard showing candidate selection in progress
- 🔮 **User feedback loop:** Capture thumbs-up/down to fine-tune LLM prompt over time

---

## 📄 References

### Key Libraries & Tools
- **OpenCV Saliency:** https://docs.opencv.org/master/d8/d5e/classcv_1_1saliency_1_1StaticSaliencySpectralResidual.html
- **MediaPipe Face Detection:** https://developers.google.com/mediapipe/solutions/vision/face_detector
- **YOLO v8 Docs:** https://docs.ultralytics.com/
- **Pillow Image Processing:** https://pillow.readthedocs.io/
- **WebP Compression Guide:** https://developers.google.com/speed/webp

### Design Principles
- **Rule of Thirds:** Subject placement at 1/3 intervals (photography composition)
- **WCAG Contrast Requirements:** https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- **YouTube Thumbnail Best Practices:** https://support.google.com/youtube/answer/72431

---

**Document Version:** 1.0  
**Last Updated:** April 2026  
**Author:** Flow Video Team  
**Status:** 🟡 Ready for Technical Review
