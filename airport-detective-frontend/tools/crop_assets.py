#!/usr/bin/env python3
"""
根据 app.js 中已有的 overlay ROI 坐标（百分比），从现有帧图中精确裁剪
9 张所属人头像 (1:1) 与 3 张遗留物缩略图 (16:10)。

输出目录：
  public/media/crops/owner/    头像 (600x600)
  public/media/crops/item/     遗留物缩略图 (800x500)
"""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRAMES_DIR = ROOT / "public" / "media" / "frames"
OWNER_DIR = ROOT / "public" / "media" / "crops" / "owner"
ITEM_DIR = ROOT / "public" / "media" / "crops" / "item"

OWNER_DIR.mkdir(parents=True, exist_ok=True)
ITEM_DIR.mkdir(parents=True, exist_ok=True)

# (id, source_filename, ROI(x%, y%, w%, h%), 输出尺寸)
OWNER_TARGETS = [
    ("P-01", "0740_05.jpg", (7.8, 38.0, 18.3, 57.5), "左侧前排黑衣乘客"),
    ("P-02", "0740_02.jpg", (7.8, 38.0, 18.3, 57.5), "左侧前排粉衣乘客"),
    ("P-03", "0740_03.jpg", (32.0, 22.0, 30.0, 70.0), "中部过道站立乘客"),
    ("P-04", "demo_450.jpg", (39.0, 22.0, 13.8, 73.0), "中部携袋女乘客"),
    ("P-06", "0800_04.jpg", (72.5, 42.0, 19.0, 53.0), "右侧黄衣乘客"),
    ("P-07", "0750_05.jpg", (60.0, 38.0, 22.0, 58.0), "右侧座位乘客"),
    ("P-09", "0800_03.jpg", (55.0, 25.0, 30.0, 70.0), "中部白衣站立乘客"),
    ("P-10", "0740_04.jpg", (12.0, 38.0, 22.0, 58.0), "左侧座位乘客"),
    ("P-13", "0800_01.jpg", (35.0, 25.0, 32.0, 70.0), "中部过道乘客"),
]

ITEM_TARGETS = [
    ("0740", "0740_01.jpg", (10.0, 60.0, 30.0, 38.0), "黑色随身包 - 左侧前排膝前"),
    ("0750", "demo_570.jpg", (50.0, 60.0, 30.0, 38.0), "浅色随身袋 - 右侧过道座位前"),
    ("0800", "0800_04.jpg", (65.0, 60.0, 30.0, 38.0), "红色购物袋 - 右侧黄衣乘客脚边"),
]

OWNER_SIZE = (600, 600)
ITEM_SIZE = (800, 500)


def pct_to_box(roi, w, h):
    """百分比 ROI -> 像素 (left, upper, right, lower)"""
    rx, ry, rw, rh = roi
    left = int(round(w * rx / 100))
    upper = int(round(h * ry / 100))
    right = int(round(w * (rx + rw) / 100))
    lower = int(round(h * (ry + rh) / 100))
    return left, upper, right, lower


def crop_to_aspect(src_path, roi, target_size, out_path):
    """
    以 ROI 中心为基准，扩展到 target_size 的比例，然后居中裁剪，
    最后缩放到 target_size。保持纵横比，不变形。
    """
    img = Image.open(src_path).convert("RGB")
    w, h = img.size
    box = pct_to_box(roi, w, h)
    cx = (box[0] + box[2]) // 2
    cy = (box[1] + box[3]) // 2

    # ROI 实际宽高（像素）
    roi_w = max(box[2] - box[0], 1)
    roi_h = max(box[3] - box[1], 1)

    # 目标比例
    tw, th = target_size
    target_ratio = tw / th

    # 在 ROI 周围扩展到目标比例（保留 ROI 在中心）
    # 宽度和高度至少要覆盖 ROI，并满足目标比例
    half_w = max(roi_w // 2, int(roi_h * target_ratio) // 2)
    half_h = max(roi_h // 2, int(roi_w / target_ratio) // 2)

    # 进一步放大 1.4 倍以提供上下文
    pad = 1.4
    half_w = int(half_w * pad)
    half_h = int(half_h * pad)

    left = cx - half_w
    right = cx + half_w
    upper = cy - half_h
    lower = cy + half_h

    # 裁剪到图片边界
    if left < 0:
        right -= left
        left = 0
    if upper < 0:
        lower -= upper
        upper = 0
    if right > w:
        left -= (right - w)
        right = w
    if lower > h:
        upper -= (lower - h)
        lower = h
    left = max(left, 0)
    upper = max(upper, 0)
    right = min(right, w)
    lower = min(lower, h)

    cropped = img.crop((left, upper, right, lower))
    # 等比例缩放到目标尺寸
    cropped = cropped.resize(target_size, Image.LANCZOS)
    cropped.save(out_path, "JPEG", quality=92, optimize=True)
    return cropped.size


def main():
    print(f"ROOT: {ROOT}")
    print(f"FRAMES_DIR: {FRAMES_DIR}")

    print("\n[所属人头像]")
    for pid, fname, roi, desc in OWNER_TARGETS:
        src = FRAMES_DIR / fname
        out = OWNER_DIR / f"{pid}.jpg"
        if not src.exists():
            print(f"  ! 缺失源帧: {src}")
            continue
        size = crop_to_aspect(src, roi, OWNER_SIZE, out)
        print(f"  + {pid} <- {fname}  ROI={roi}  -> {out.relative_to(ROOT)} {size}  ({desc})")

    print("\n[遗留物缩略图]")
    for clip_id, fname, roi, desc in ITEM_TARGETS:
        src = FRAMES_DIR / fname
        out = ITEM_DIR / f"{clip_id}.jpg"
        if not src.exists():
            print(f"  ! 缺失源帧: {src}")
            continue
        size = crop_to_aspect(src, roi, ITEM_SIZE, out)
        print(f"  + {clip_id} <- {fname}  ROI={roi}  -> {out.relative_to(ROOT)} {size}  ({desc})")

    print("\n完成。")


if __name__ == "__main__":
    main()
