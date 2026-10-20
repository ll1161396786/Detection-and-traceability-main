"""Local YOLOv10 inference. The vendored fork and weights came from the user."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "data" / "yolo-settings"))
os.environ["YOLO_AUTOINSTALL"] = "false"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "data" / "matplotlib"))
sys.path.insert(0, str(ROOT / "vendor"))

import cv2
import torch
from ultralytics import YOLOv10

ZH = dict(zip(
    range(80),
    "人 自行车 汽车 摩托车 飞机 公交车 火车 卡车 船 红绿灯 消防栓 停车标志 停车计时器 长椅 鸟 猫 狗 马 羊 牛 大象 熊 斑马 长颈鹿 背包 雨伞 手提包 领带 行李箱 飞盘 滑雪板 单板滑雪板 运动球 风筝 棒球棒 棒球手套 滑板 冲浪板 网球拍 瓶子 酒杯 杯子 叉子 刀 勺子 碗 香蕉 苹果 三明治 橙子 西兰花 胡萝卜 热狗 披萨 甜甜圈 蛋糕 椅子 沙发 盆栽 床 餐桌 马桶 电视 笔记本电脑 鼠标 遥控器 键盘 手机 微波炉 烤箱 烤面包机 水槽 冰箱 书 时钟 花瓶 剪刀 泰迪熊 吹风机 牙刷".split()
))
MODEL_NAMES = [f"yolov10{x}.pt" for x in "ns mblx".replace(" ", "")]


def hardware():
    gpu = torch.cuda.is_available()
    return {"cuda": gpu, "device": torch.cuda.get_device_name(0) if gpu else "CPU",
            "torch": torch.__version__, "python": sys.version.split()[0]}


class Detector:
    def __init__(self):
        self.model = None
        self.key = None

    def load(self, name, device):
        if name not in MODEL_NAMES or not (ROOT / "models" / name).is_file():
            raise ValueError("模型文件不存在，请检查 models 文件夹。")
        actual = "0" if device == "auto" and torch.cuda.is_available() else device
        if actual == "auto":
            actual = "cpu"
        if actual == "0" and not torch.cuda.is_available():
            raise ValueError("CUDA 不可用，请改选 CPU。")
        if self.key != (name, actual):
            self.model = None
            self.key = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            # This 2024 fork expects a full checkpoint. Limit the compatibility
            # override to loading the allowlisted, local, user-provided weights.
            old = os.environ.get("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD")
            os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
            try:
                self.model = YOLOv10(str(ROOT / "models" / name))
            finally:
                if old is None:
                    os.environ.pop("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", None)
                else:
                    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = old
            self.key = (name, actual)
        return actual

    def predict(self, frame, options, device):
        result = self.model.predict(frame, conf=options["confidence"],
                                    imgsz=options["imgsz"], device=device,
                                    classes=[0, 24, 26, 28] if options["scope"] == "luggage" else None,
                                    verbose=False, save=False)[0]
        boxes = []
        for box in result.boxes.cpu().numpy():
            cls = int(box.cls[0])
            boxes.append({"class_id": cls, "label": result.names[cls], "label_zh": ZH.get(cls, result.names[cls]),
                          "confidence": round(float(box.conf[0]), 4),
                          "xyxy": [round(float(v), 2) for v in box.xyxy[0]]})
        # OpenCV draws English labels reliably without downloading any font.
        annotated = frame.copy()
        for b in boxes:
            x1, y1, x2, y2 = [int(v) for v in b["xyxy"]]
            color = (160, 220, 80) if b["class_id"] == 0 else (70, 188, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f'{b["label"]} {b["confidence"]:.0%}'
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, .5, 1)
            top = max(th + 8, y1)
            cv2.rectangle(annotated, (x1, top - th - 8), (min(annotated.shape[1], x1 + tw + 8), top), color, -1)
            cv2.putText(annotated, label, (x1 + 4, top - 5), cv2.FONT_HERSHEY_SIMPLEX, .5, (20, 30, 20), 1, cv2.LINE_AA)
        return annotated, boxes
