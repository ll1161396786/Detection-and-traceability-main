"""Recover missing package/person photos from preserved source frames, without rerunning YOLO."""
import argparse
import json
import re
from pathlib import Path
from app import DATA, jobs, source_for, cv2, save_candidate_crop, save_person_crop


def repair(jid):
    job = jobs[jid]
    if job.get("archive_cleared") or job["status"] not in {"completed", "interrupted", "failed"}:
        raise ValueError("仅修复已结束且未清除结果的任务。")
    folder = DATA / "jobs" / jid
    log = folder / "frames.jsonl"
    source = job["source"]
    video, _ = source_for({"upload_id": source["id"]} if source.get("id") else {"library_name": source["name"]})
    for name in ("crops", "people"):
        (folder / name).mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    restored = 0
    try:
        with log.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                missing = []
                for box in row.get("boxes", []):
                    tid = box.get("track_id", "")
                    if not re.fullmatch(r"[LP]\d{3,}", tid):
                        continue
                    path = folder / ("crops" if tid.startswith("L") else "people") / (
                        f"crop-{tid}.jpg" if tid.startswith("L") else f"person-{tid}.jpg")
                    if not path.exists():
                        missing.append(box)
                if not missing:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, row["frame"] - 1)
                ok, frame = cap.read()
                if not ok:
                    raise OSError(f"原视频第 {row['frame']} 帧无法读取")
                w, h = row["width"], row["height"]
                if frame.shape[:2] != (h, w):
                    frame = cv2.resize(frame, (w, h))
                for box in missing:
                    tid = box["track_id"]
                    if tid.startswith("L"):
                        save_candidate_crop(folder, frame, {"bbox": box["xyxy"], "crop": f"crop-{tid}.jpg"}, w, h)
                    else:
                        save_person_crop(folder, frame, box, w, h)
                    restored += 1
    finally:
        cap.release()
    return restored


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id")
    args = parser.parse_args()
    print(f"Restored photos: {repair(args.job_id)}")
