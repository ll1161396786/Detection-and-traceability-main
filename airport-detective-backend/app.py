"""Single-user local video analysis server, with persistent jobs and real inference."""
import csv
import json
import logging
import math
import os
import re
import shutil
import subprocess
import struct
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException
from engine import ROOT, MODEL_NAMES, Detector, cv2, hardware
from analytics import SceneAnalyzer, draw_scene, merge_warning
import imageio_ffmpeg
from person_photos import quality as person_photo_quality, improves as improves_person_photo, JPEG_QUALITY as PERSON_JPEG_QUALITY

DATA = ROOT / "data"
VIDEOS = ROOT / "videos"
for folder in [DATA / "uploads", DATA / "jobs", VIDEOS]:
    folder.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler(DATA / "server.log", encoding="utf-8"), logging.StreamHandler()])
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 ** 3
app.json.ensure_ascii = False
FRONTEND = ROOT.parent / "airport-detective-frontend"
EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
TERMINAL = {"completed", "cancelled", "failed", "interrupted"}
jobs = {}
lock = threading.RLock()
detector = Detector()
machine = hardware()


def json_write(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def write_jpeg(path, frame, quality=86):
    """Encode before publishing, support Unicode paths and never expose partial JPEGs."""
    if frame is None or not frame.size:
        raise ValueError("截图为空，无法保存照片。")
    success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise OSError(f"截图编码失败：{path.name}")
    temp = path.with_suffix(".jpg.tmp")
    temp.write_bytes(encoded.tobytes())
    temp.replace(path)


for path in (DATA / "jobs").glob("*/status.json"):
    try:
        j = json.loads(path.read_text(encoding="utf-8"))
        if j["status"] not in TERMINAL:
            j.update(status="interrupted", message="上次服务退出，任务已中断。请重新开始识别。")
            json_write(path, j)
        jobs[j["id"]] = j
    except (ValueError, KeyError, OSError):
        logging.exception("Cannot recover job %s", path)


def update(jid, **fields):
    with lock:
        jobs[jid].update(fields)
        if "candidate_summary" in fields and not jobs[jid].get("archive_cleared"):
            save_local_archive(jid, fields["candidate_summary"])
        json_write(DATA / "jobs" / jid / "status.json", jobs[jid])


def save_local_archive(jid, candidates):
    """Merge cumulative records on disk; the browser never owns archive history."""
    path = DATA / "jobs" / jid / "archive.json"
    records = {item["id"]: item for item in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
    for candidate in candidates:
        previous = records.get(candidate["id"], {})
        owners = {owner["person_id"]: owner for owner in previous.get("owners", [])}
        for owner in candidate.get("owners", []):
            saved = owners.get(owner["person_id"], {})
            owners[owner["person_id"]] = {
                **saved, **owner,
                "probability": max(saved.get("probability", 0), owner["probability"]),
                "near_frames": max(saved.get("near_frames", 0), owner.get("near_frames", 0)),
            }
        first_owner = candidate.get("first_owner_id", previous.get("first_owner_id"))
        current_owner = candidate.get("current_owner_id", previous.get("current_owner_id"))
        for owner in owners.values():
            owner["is_first_owner"] = owner["person_id"] == first_owner
            owner["is_current_owner"] = owner["person_id"] == current_owner
        records[candidate["id"]] = {
            **previous, **candidate,
            **merge_warning(previous, candidate),
            "stationary_seconds": max(previous.get("stationary_seconds", 0), candidate.get("stationary_seconds", 0)),
            "owners": sorted(owners.values(), key=lambda owner: (not owner["is_current_owner"], not owner["is_first_owner"], -owner["probability"])),
        }
        # Snapshot the triggering frame, rather than the continually advancing last_seen.
        if candidate.get("alarm_frame") and jobs[jid]["source"].get("video_path"):
            replay = records[candidate["id"]].get("replay", {})
            if replay.get("revision") != candidate.get("alarm_revision"):
                records[candidate["id"]]["replay"] = {
                    "frame": candidate["alarm_frame"], "revision": candidate["alarm_revision"],
                    "time": (candidate["alarm_frame"] - 1) / jobs[jid]["source"]["fps"],
                }
    json_write(path, sorted(records.values(), key=lambda item: item["id"]))


def valid_id(value):
    return bool(re.fullmatch(r"[a-f0-9]{32}", value or ""))


def video_info(path):
    cap = cv2.VideoCapture(str(path))
    try:
        ok, first = cap.read()
        if not cap.isOpened() or not ok or first is None:
            raise ValueError("无法解码视频。请确认文件完整，或转换为 H.264 MP4 后重试。")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(fps) or fps <= 0 or fps > 240:
            raise ValueError("视频帧率无效或超过 240 FPS，请先转换为标准帧率 MP4。")
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        frames = max(0, int(frames)) if math.isfinite(frames) else 0
        height, width = first.shape[:2]
        return {"fps": round(fps, 5), "frames": frames, "width": width, "height": height,
                "duration": round(frames / fps, 2), "size": path.stat().st_size}
    finally:
        cap.release()


@app.before_request
def same_origin():
    if request.method in {"POST", "DELETE", "PUT"}:
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            return jsonify(error="仅允许本机页面发起请求。"), 403


@app.after_request
def no_cache(response):
    if response.status_code < 400 and re.search(r"/(crops|people)/[^/]+\.jpg$", request.path):
        response.headers["Cache-Control"] = "private, max-age=86400"
    elif request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error="文件超过 2 GB，请放入 videos 文件夹后刷新列表。" if exc.code == 413 else exc.description), exc.code
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    logging.exception("Request failed")
    return jsonify(error="服务处理失败，请查看 data/server.log。"), 500


@app.get("/")
def index():
    if FRONTEND.is_dir():
        return send_from_directory(FRONTEND, "index.html")
    return send_from_directory(app.static_folder, "index.html")


@app.get("/workbench")
def workbench():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/app.js")
@app.get("/styles.css")
@app.get("/live-client.js")
@app.get("/live-monitor.css")
def frontend_code():
    return send_from_directory(FRONTEND, request.path.lstrip("/"))


@app.get("/public/<path:name>")
def frontend_media(name):
    return send_from_directory(FRONTEND / "public", name)


@app.get("/api/health")
def health():
    return jsonify(ready=True, hardware=machine,
                   models=[{"name": n, "size_mb": round((ROOT / "models" / n).stat().st_size / 1024 ** 2, 1)}
                           for n in MODEL_NAMES if (ROOT / "models" / n).is_file()])


@app.get("/api/library")
def library():
    return jsonify(files=[{"name": p.name, "size": p.stat().st_size} for p in VIDEOS.iterdir()
                          if p.is_file() and p.suffix.lower() in EXTENSIONS])


@app.get("/api/library/media/<name>")
def library_media(name):
    if not isinstance(name, str) or not name or "/" in name or "\\" in name:
        return jsonify(error="视频不存在"), 404
    path = (VIDEOS / name).resolve()
    if path.parent != VIDEOS.resolve() or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        return jsonify(error="视频不存在"), 404
    return send_file(path, conditional=True)


@app.post("/api/uploads")
def upload():
    file = request.files.get("video")
    if file is None or not file.filename:
        raise ValueError("请选择一个视频。")
    name = file.filename.replace("\\", "/").split("/")[-1]
    ext = Path(name).suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError("支持 MP4 / MOV / AVI / MKV / WEBM / M4V 视频。")
    uid = uuid.uuid4().hex
    folder = DATA / "uploads" / uid
    folder.mkdir()
    path = folder / ("source" + ext)
    try:
        file.save(path)
        meta = {"id": uid, "name": name, "filename": path.name, **video_info(path)}
        json_write(folder / "meta.json", meta)
        cap = cv2.VideoCapture(str(path))
        try:
            ok, frame = cap.read()
            if ok:
                write_jpeg(folder / "poster.jpg", frame)
        finally:
            cap.release()
        return jsonify(meta)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def source_for(body):
    if body.get("upload_id"):
        uid = body["upload_id"]
        if not isinstance(uid, str) or not valid_id(uid):
            raise ValueError("无效的视频编号。")
        folder = DATA / "uploads" / uid
        if not (folder / "meta.json").is_file():
            raise ValueError("视频不存在，请重新上传。")
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        return folder / meta["filename"], meta
    name = body.get("library_name", "")
    if not isinstance(name, str) or not name or "/" in name or "\\" in name:
        raise ValueError("请选择视频。")
    path = (VIDEOS / name).resolve()
    if path.parent != VIDEOS.resolve() or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError("videos 文件夹内没有这个视频，请刷新列表。")
    return path, {"name": name, **video_info(path)}


@app.get("/api/uploads/<uid>/<kind>")
def uploaded_media(uid, kind):
    if not valid_id(uid) or kind not in {"poster", "video"}:
        return jsonify(error="文件不存在"), 404
    folder = DATA / "uploads" / uid
    if not (folder / "meta.json").is_file():
        return jsonify(error="文件不存在"), 404
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return send_file(folder / ("poster.jpg" if kind == "poster" else meta["filename"]), conditional=True)


@app.get("/api/jobs")
def list_jobs():
    with lock:
        return jsonify(jobs=sorted([dict(j) for j in jobs.values()], key=lambda j: j["created"], reverse=True)[:30])


@app.post("/api/jobs")
def start_job():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ValueError("无效的请求参数。")
    try:
        opts = {"model": body.get("model", "yolov10n.pt"), "device": body.get("device", "auto"),
                "confidence": float(body.get("confidence", .25)), "imgsz": "source",
                "stride": int(body.get("stride", 1)), "scope": body.get("scope", "all"),
                "linger_seconds": float(body.get("linger_seconds", 3))}
    except (TypeError, ValueError):
        raise ValueError("识别参数无效。")
    if any(not isinstance(opts[key], str) for key in ("model", "device", "scope")):
        raise ValueError("识别参数无效。")
    if (opts["model"] not in MODEL_NAMES or opts["device"] not in {"auto", "cpu", "0"}
            or not .05 <= opts["confidence"] <= .95
            or opts["stride"] not in {1, 2, 5, 10} or opts["scope"] not in {"all", "luggage"}):
        raise ValueError("识别参数不在支持范围内。")
    if not math.isfinite(opts["linger_seconds"]) or not 1 <= opts["linger_seconds"] <= 120:
        raise ValueError("遗留物静止阈值应在 1–120 秒之间。")
    train = {}
    for key, fallback in (("number", "DT-0421"), ("route", "Downtown Line"),
                          ("carriage", "Car 03"), ("camera", "CAM-07")):
        value = str(body.get("train", {}).get(key, fallback)).strip() if isinstance(body.get("train", {}), dict) else fallback
        train[key] = value[:40] or fallback
    with lock:
        if any(j["status"] not in TERMINAL for j in jobs.values()):
            return jsonify(error="已有识别任务正在运行，请等待完成或停止当前任务。"), 409
        source, meta = source_for(body)
        jid = uuid.uuid4().hex
        (DATA / "jobs" / jid).mkdir()
        jobs[jid] = {"id": jid, "created": datetime.now().isoformat(timespec="seconds"),
                     "source": meta, "options": opts, "train": train, "status": "loading", "message": "正在加载本地模型…",
                     "progress": 0, "processed": 0, "frame": 0, "time": 0, "elapsed": 0,
                     "boxes": [], "counts": [], "timeline": [], "preview_version": 0, "cancel": False,
                     "current_count": 0, "peak_count": 0, "inference_fps": 0, "artifacts": [],
                     "luggage_candidates": [], "candidate_summary": [], "alert_count": 0,
                     "archive_cleared": False}
        update(jid)
        threading.Thread(target=run_job, args=(jid, source), daemon=True).start()
        return jsonify(jobs[jid]), 202


@app.get("/api/jobs/<jid>")
def job_status(jid):
    with lock:
        if jid not in jobs:
            return jsonify(error="任务不存在"), 404
        return jsonify(jobs[jid])


@app.get("/api/jobs/<jid>/archive")
def job_archive(jid):
    """Return the cumulative package archive independently of the live frame."""
    with lock:
        if jid not in jobs:
            return jsonify(error="任务不存在"), 404
        job = jobs[jid]
        if job.get("archive_cleared"):
            return jsonify(job_id=jid, status=job["status"], cleared=True,
                           record_count=0, records=[])
        path = DATA / "jobs" / jid / "archive.json"
        if not path.exists():
            # Migrate older on-disk jobs once, including associations between publishes.
            frame_log = path.parent / "frames.jsonl"
            if frame_log.exists():
                with frame_log.open(encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            save_local_archive(jid, json.loads(line).get("luggage_candidates", []))
                        except ValueError:
                            continue
            save_local_archive(jid, job.get("candidate_summary", []))
        records = []
        for candidate in json.loads(path.read_text(encoding="utf-8")):
            item = dict(candidate)
            item.setdefault("warning_level", "suspected" if item.get("risk") == "high" else "none")
            item["package_photo"] = f"/api/jobs/{jid}/crops/{candidate.get('event_crop', candidate['crop'])}"
            item["owners"] = [
                {**owner, "photo": person_photo_url(jid,owner['person_id'])}
                for owner in candidate.get("owners", [])
            ]
            records.append(item)
        return jsonify(job_id=jid, status=job["status"], cleared=False,
                       record_count=len(records), records=records)


@app.post("/api/jobs/<jid>/archive/<candidate_id>/confirm")
def confirm_abandoned(jid, candidate_id):
    with lock:
        if jid not in jobs or jobs[jid].get("archive_cleared") or (jobs[jid].get("cancel") and jobs[jid]["status"] not in TERMINAL):
            return jsonify(error="任务已停止或档案不存在"), 404
        if not re.fullmatch(r"L\d{3,}", candidate_id):
            return jsonify(error="无效的包裹编号"), 400
        path = DATA / "jobs" / jid / "archive.json"
        if not path.exists():
            job_archive(jid)
        records = json.loads(path.read_text(encoding="utf-8"))
        item = next((record for record in records if record["id"] == candidate_id), None)
        if item is None:
            return jsonify(error="包裹档案不存在"), 404
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or not isinstance(body.get("confirmed", True), bool):
            return jsonify(error="确认状态必须为布尔值"), 400
        item.setdefault("automatic_warning_level", item.get("warning_level", "none"))
        item["warning_level"] = "confirmed" if body.get("confirmed", True) else "suspected"
        item["manual_warning_level"] = item["warning_level"]
        item["manual_alarm_revision"] = item.get("alarm_revision", 0)
        item["warning_source"] = "manual"
        item["confirmed_at"] = datetime.now().isoformat(timespec="seconds") if body.get("confirmed", True) else None
        json_write(path, records)
        return job_archive(jid)


@app.post("/api/jobs/<jid>/cancel")
def cancel_job(jid):
    with lock:
        if jid not in jobs:
            return jsonify(error="任务不存在"), 404
        if jobs[jid]["status"] not in TERMINAL:
            update(jid, cancel=True, message="正在停止，请稍候…")
        return jsonify(jobs[jid])


@app.get("/api/jobs/<jid>/preview")
def preview(jid):
    if jid not in jobs:
        return jsonify(error="任务不存在"), 404
    with lock:
        path = DATA / "jobs" / jid / "preview.jpg"
        if not path.is_file():
            return "", 204
        # Read under the writer lock to avoid Windows replacement/file sharing races.
        from io import BytesIO
        return send_file(BytesIO(path.read_bytes()), mimetype="image/jpeg")


@app.get("/api/jobs/<jid>/files/<name>")
def artifact(jid, name):
    if jid not in jobs or jobs[jid]["status"] != "completed" or name not in jobs[jid]["artifacts"]:
        return jsonify(error="结果尚未生成"), 404
    return send_file(DATA / "jobs" / jid / name, conditional=True,
                     as_attachment=request.args.get("download") == "1", download_name=name)


@app.get("/api/jobs/<jid>/crops/<name>")
def candidate_crop(jid, name):
    if jid not in jobs or jobs[jid].get("archive_cleared") or not re.fullmatch(r"crop-L\d{3,}(?:-event-\d+)?\.jpg", name or ""):
        return jsonify(error="候选物截图不存在"), 404
    path = DATA / "jobs" / jid / "crops" / name
    if not path.is_file():
        return jsonify(error="候选物截图不存在"), 404
    return send_file(path, conditional=True)


@app.get("/api/jobs/<jid>/people/<name>")
def person_crop(jid, name):
    if jid not in jobs or jobs[jid].get("archive_cleared") or not re.fullmatch(r"person-P\d{3,}\.jpg", name or ""):
        return jsonify(error="人员截图不存在"), 404
    from io import BytesIO
    with lock:
        path = DATA / "jobs" / jid / "people" / name
        if not path.is_file() or jobs[jid].get('archive_cleared'):
            return jsonify(error="人员截图不存在"), 404
        return send_file(BytesIO(path.read_bytes()),mimetype='image/jpeg')


def person_photo_url(jid,person_id):
    path=DATA/'jobs'/jid/'people'/f'person-{person_id}.jpg'
    try:version=f'?v={path.stat().st_mtime_ns}'
    except OSError:version=''
    return f'/api/jobs/{jid}/people/person-{person_id}.jpg{version}'


def evidence_index(jid):
    """Build a compact per-package index from the available frame log."""
    folder = DATA / "jobs" / jid
    cache = folder / "evidence-index.json"
    if jobs[jid]["status"] in TERMINAL and cache.is_file():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            logging.warning("Rebuilding invalid evidence index for %s", jid)
    frames_path = folder / "frames.jsonl"
    if not frames_path.is_file():
        return {}
    index = {}
    with frames_path.open("r", encoding="utf-8") as stream:
        for sequence, line in enumerate(stream):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            current = {c["id"]: c for c in row.get("luggage_candidates", [])}
            luggage_ids = {b.get("track_id") for b in row.get("boxes", [])
                           if re.fullmatch(r"L\d{3,}", b.get("track_id") or "")}
            for candidate_id in sorted(luggage_ids):
                owners = current.get(candidate_id, {}).get("owners", [])
                best = owners[0] if owners else None
                index.setdefault(candidate_id, []).append({
                    "sequence": sequence,
                    "frame": row["frame"],
                    "time": row["time"],
                    "owner_id": best["person_id"] if best else None,
                    "owner_probability": best["probability"] if best else None,
                })
    if jobs[jid]["status"] in TERMINAL:
        json_write(cache, index)
    return index


@app.get("/api/jobs/<jid>/evidence/<candidate_id>")
def package_evidence(jid, candidate_id):
    if (jid not in jobs or jobs[jid].get("archive_cleared")
            or not re.fullmatch(r"L\d{3,}", candidate_id or "")):
        return jsonify(error="包裹证据尚未生成"), 404
    candidate = next((item for item in jobs[jid].get("candidate_summary", []) if item.get("id") == candidate_id), None)
    frames = evidence_index(jid).get(candidate_id, [])
    if not candidate or not frames:
        return jsonify(error="未找到该包裹的逐帧证据"), 404
    return jsonify(candidate=candidate, frames=frames, total_frames=len(frames),
                   analyzed_stride=jobs[jid]["options"]["stride"])


@app.get("/api/jobs/<jid>/evidence/<candidate_id>/frames/<int:sequence>.jpg")
def package_evidence_frame(jid, candidate_id, sequence):
    if (jid not in jobs or jobs[jid].get("archive_cleared")
            or not re.fullmatch(r"L\d{3,}", candidate_id or "")):
        return jsonify(error="包裹证据帧不存在"), 404
    frames = evidence_index(jid).get(candidate_id, [])
    if not any(item["sequence"] == sequence for item in frames):
        return jsonify(error="包裹证据帧不存在"), 404
    folder = DATA / "jobs" / jid
    cache_folder = folder / "evidence-frames"
    cache_folder.mkdir(exist_ok=True)
    image_path = cache_folder / f"frame-{sequence:08d}.jpg"
    if not image_path.is_file():
        if jobs[jid]["status"] != "completed":
            return jsonify(error="该实时证据帧尚未写入"), 404
        cap = cv2.VideoCapture(str(folder / "result.mp4"))
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, sequence)
            ok, frame = cap.read()
            if not ok or frame is None:
                return jsonify(error="无法读取该证据帧"), 404
            scale = min(1., 480 / frame.shape[1])
            if scale < 1:
                frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
            write_jpeg(image_path, frame, 78)
        finally:
            cap.release()
    return send_file(image_path, conditional=True)


@app.post("/api/jobs/<jid>/archive/clear")
def clear_photo_archive(jid):
    with lock:
        if jid not in jobs:
            return jsonify(error="任务不存在"), 404
        if jobs[jid]["status"] not in TERMINAL:
            return jsonify(error="请先停止或等待检测结束，再删除存档照片"), 409
        folder = DATA / "jobs" / jid
        remove_photo_archive(folder)
        update(jid, archive_cleared=True, message="存档照片已删除，检测数据仍保留。")
        return jsonify(jobs[jid])


@app.get("/api/jobs/<jid>/frame")
def playback_frame(jid):
    if jid not in jobs or jobs[jid]["status"] != "completed":
        return jsonify(error="结果尚未生成"), 404
    try:
        seconds = float(request.args.get("time", 0))
    except (TypeError, ValueError):
        raise ValueError("无效的播放时间。")
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("无效的播放时间。")
    job = jobs[jid]
    index = min(job["processed"] - 1, int(seconds * job["source"]["fps"] / job["options"]["stride"]))
    folder = DATA / "jobs" / jid
    if not (folder / "frame-offsets.bin").is_file():
        return jsonify(error="此旧任务没有回放索引，请重新识别。"), 404
    with (folder / "frame-offsets.bin").open("rb") as offsets:
        offsets.seek(index * 8)
        offset = struct.unpack("<Q", offsets.read(8))[0]
    with (folder / "frames.jsonl").open("rb") as frames:
        frames.seek(offset)
        return jsonify(json.loads(frames.readline()))


class Cancelled(Exception):
    pass


def check_cancel(jid):
    if jobs[jid]["cancel"]:
        raise Cancelled()


def save_candidate_crop(folder, frame, candidate, width, height):
    path = folder / "crops" / candidate["crop"]
    if path.exists():
        return
    x1, y1, x2, y2 = [int(v) for v in candidate["bbox"]]
    pad_x, pad_y = max(14, (x2 - x1) // 3), max(14, (y2 - y1) // 3)
    crop = frame[max(0, y1-pad_y):min(height, y2+pad_y), max(0, x1-pad_x):min(width, x2+pad_x)]
    if crop.size:
        write_jpeg(path, crop)


def save_person_crop(folder, frame, box, width, height):
    track_id = box.get("track_id", "")
    if not re.fullmatch(r"P\d{3,}", track_id):
        return
    path = folder / "people" / f"person-{track_id}.jpg"
    x1, y1, x2, y2 = [int(v) for v in box["xyxy"]]
    pad_x, pad_y = max(12, (x2 - x1) // 8), max(12, (y2 - y1) // 12)
    crop = frame[max(0, y1-pad_y):min(height, y2+pad_y), max(0, x1-pad_x):min(width, x2+pad_x)]
    if not crop.size:return
    metadata=path.with_suffix('.json')
    proposed=person_photo_quality(crop,box.get('confidence',.9))
    with lock:
        previous=None
        if path.exists() and metadata.exists():
            try:previous=json.loads(metadata.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
        if not improves_person_photo(proposed,previous):return
        write_jpeg(path,crop,quality=PERSON_JPEG_QUALITY)
        json_write(metadata,proposed)


def save_evidence_snapshot(folder, frame, sequence):
    path = folder / "evidence-frames" / f"frame-{sequence:08d}.jpg"
    if path.exists():
        return
    scale = min(1., 480 / frame.shape[1])
    snapshot = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale))) if scale < 1 else frame
    write_jpeg(path, snapshot, 78)


def remove_photo_archive(folder):
    resolved_folder = folder.resolve()
    for name in ("crops", "people", "evidence-frames", "replays"):
        path = (folder / name).resolve()
        if path.parent == resolved_folder and path.is_dir():
            shutil.rmtree(path)
    (folder / "evidence-index.json").unlink(missing_ok=True)


def run_job(jid, source):
    folder = DATA / "jobs" / jid
    opts = jobs[jid]["options"]
    meta = jobs[jid]["source"]
    cap = writer = process = None
    started = time.monotonic()
    analyzer = SceneAnalyzer(opts.get("linger_seconds", 3))
    try:
        device = detector.load(opts["model"], opts["device"])
        check_cancel(jid)
        cap = cv2.VideoCapture(str(source))
        w, h = meta["width"], meta["height"]
        writer = cv2.VideoWriter(str(folder / "working.avi"), cv2.VideoWriter_fourcc(*"MJPG"),
                                 meta["fps"] / opts["stride"], (w, h))
        if not writer.isOpened():
            raise RuntimeError("无法创建结果视频，请检查磁盘空间。")
        update(jid, status="running", message="正在逐帧识别", device=machine["device"] if device == "0" else "CPU",
               output_width=w, output_height=h)
        (folder / "crops").mkdir(exist_ok=True)
        (folder / "people").mkdir(exist_ok=True)
        (folder / "evidence-frames").mkdir(exist_ok=True)
        frame_index = processed = peak = 0
        last_source_frame = None
        infer_seconds = 0.
        totals, peaks, hit_frames = Counter(), Counter(), Counter()
        labels, timeline = {}, []
        last_publish = 0
        with (folder / "detections.csv").open("w", encoding="utf-8-sig", newline="") as csv_file, \
                (folder / "frames.jsonl").open("wb") as json_file, \
                (folder / "frame-offsets.bin").open("wb") as offset_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["source_frame_1based", "time_seconds", "class_id", "label", "label_zh", "confidence", "x1", "y1", "x2", "y2", "coordinate_width", "coordinate_height"])
            while True:
                check_cancel(jid)
                ok, frame = cap.read()
                if not ok:
                    break
                frame_index += 1
                if (frame_index - 1) % opts["stride"]:
                    continue
                if frame.shape[1] != w or frame.shape[0] != h:
                    raise ValueError("视频在播放中改变了分辨率，请先转换为固定分辨率视频。")
                last_source_frame = frame
                t0 = time.monotonic()
                annotated, boxes = detector.predict(frame, opts, device)
                infer_seconds += time.monotonic() - t0
                processed += 1
                timestamp = (frame_index - 1) / meta["fps"]
                boxes, candidates = analyzer.update(boxes, frame_index, timestamp, w, h, frame=frame)
                annotated = draw_scene(annotated, boxes, candidates)
                for box in boxes:
                    if box.get("class_id") == 0:
                        save_person_crop(folder, frame, box, w, h)
                for box in boxes:
                    if re.fullmatch(r"L\d{3,}", box.get("track_id") or ""):
                        save_candidate_crop(folder, frame, {"bbox": box["xyxy"], "crop": f"crop-{box['track_id']}.jpg"}, w, h)
                if any(re.fullmatch(r"L\d{3,}", box.get("track_id") or "") for box in boxes):
                    save_evidence_snapshot(folder, annotated, processed - 1)
                writer.write(annotated)
                count = Counter(b["class_id"] for b in boxes)
                totals.update(count)
                hit_frames.update(count.keys())
                for b in boxes:
                    labels[b["class_id"]] = (b["label"], b["label_zh"])
                    csv_writer.writerow([frame_index, round(timestamp, 3), b["class_id"], b["label"], b["label_zh"], b["confidence"], *b["xyxy"], w, h])
                for cls, n in count.items():
                    peaks[cls] = max(peaks[cls], n)
                peak = max(peak, len(boxes))
                offset_file.write(struct.pack("<Q", json_file.tell()))
                json_file.write((json.dumps({"frame": frame_index, "time": round(timestamp, 3), "width": w, "height": h,
                                             "boxes": boxes, "luggage_candidates": candidates}, ensure_ascii=False) + "\n").encode("utf-8"))
                if not timeline or timestamp - timeline[-1]["time"] >= 1:
                    timeline.append({"time": round(timestamp, 2), "count": len(boxes)})
                now = time.monotonic()
                if now - last_publish >= .3 or frame_index == 1:
                    json_file.flush()
                    offset_file.flush()
                    for candidate in candidates:
                        save_candidate_crop(folder, frame, candidate, w, h)
                    success, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    with lock:
                        if success:
                            (folder / "preview.jpg").write_bytes(jpg.tobytes())
                        counts = [{"class_id": c, "label": labels[c][0], "label_zh": labels[c][1],
                                   "detections": n, "peak": peaks[c], "hit_frames": hit_frames[c]} for c, n in totals.most_common()]
                        update(jid, processed=processed, frame=frame_index, time=round(timestamp, 2),
                               elapsed=round(now - started, 1), progress=min(99., round(frame_index / max(1, meta["frames"]) * 100, 1)) if meta["frames"] else 0,
                               boxes=boxes, counts=counts, current_count=len(boxes), peak_count=peak,
                               inference_fps=round(processed / max(infer_seconds, .001), 1),
                               timeline=timeline[-120:], preview_version=processed,
                               luggage_candidates=candidates, candidate_summary=analyzer.summary(),
                               alert_count=sum(c["state"] == "疑似遗留" for c in analyzer.summary()))
                    last_publish = now
        cap.release()
        cap = None
        writer.release()
        writer = None
        if not processed:
            raise RuntimeError("未能读取到有效视频帧。")
        if meta["frames"] and frame_index < meta["frames"] - max(3, int(meta["fps"])):
            raise RuntimeError(f"视频提前解码中断（读取 {frame_index}/{meta['frames']} 帧），请转换视频后重试。")
        check_cancel(jid)
        success, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        with lock:
            if success:
                (folder / "preview.jpg").write_bytes(jpg.tobytes())
            for candidate in candidates:
                save_candidate_crop(folder, last_source_frame, candidate, w, h)
        update(jid, status="exporting", message="识别完成，正在生成可播放的 MP4…", processed=processed,
               preview_version=processed,
               frame=frame_index, progress=100, peak_count=peak,
               time=round(timestamp, 2), boxes=boxes, current_count=len(boxes),
               luggage_candidates=candidates, candidate_summary=analyzer.summary(),
               alert_count=sum(c["state"] == "疑似遗留" for c in analyzer.summary()),
               counts=[{"class_id": c, "label": labels[c][0], "label_zh": labels[c][1], "detections": n,
                        "peak": peaks[c], "hit_frames": hit_frames[c]} for c, n in totals.most_common()],
               inference_fps=round(processed / max(infer_seconds, .001), 1))
        with (folder / "encode.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(folder / "working.avi"),
                                        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
                                        "-movflags", "+faststart", str(folder / "result.mp4")], stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            while process.poll() is None:
                check_cancel(jid)
                time.sleep(.2)
            if process.returncode:
                raise RuntimeError("MP4 导出失败，请查看任务目录内的 encode.log。")
        check_cancel(jid)
        with lock:
            report = {**jobs[jid], "status": "completed", "message": "识别完成", "elapsed": round(time.monotonic() - started, 1),
                      "timeline": timeline, "notes": ["统计为逐帧检测结果，不是去重人数或物品数。", "遗留物与所属人由距离、共同出现和静止时长启发式推断，并非模型原生分类或身份识别。",
                                                      "推理保留源视频分辨率，仅在模型输入边缘补齐步长；坐标相对于源画面。", "结果视频不含原音频；抽帧输出帧率为原帧率 / 抽帧间隔。"]}
            json_write(folder / "report.json", report)
            update(jid, status="completed", message="识别完成，可播放或下载结果", elapsed=report["elapsed"],
                   artifacts=["result.mp4", "report.json", "detections.csv", "frames.jsonl"])
    except Cancelled:
        update(jid, message="正在停止检测，保留本地档案…")
    except Exception as exc:
        logging.exception("Job %s failed", jid)
        message = "原分辨率推理显存不足，请选择 yolov10n 或切换 CPU。" if "out of memory" in str(exc).lower() else str(exc)
        update(jid, status="failed", message=message, elapsed=round(time.monotonic() - started, 1))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if cap is not None:
            cap.release()
        if writer is not None:
            writer.release()
        if jobs[jid].get("cancel"):
            update(jid, status="cancelled", message="检测已停止，本地档案和照片已保留。",
                   elapsed=round(time.monotonic() - started, 1), candidate_summary=analyzer.summary())
        (folder / "working.avi").unlink(missing_ok=True)


import sys
from live_monitor import register
monitor = register(sys.modules[__name__])
from event_replay import register_replay
register_replay(sys.modules[__name__])


if __name__ == "__main__":
    from werkzeug.serving import make_server
    import argparse
    import webbrowser
    import socket
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5180)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = None
    for port in range(args.port, args.port + 10):
        try:
            # Werkzeug enables address reuse. On Windows this can silently bind
            # beside an existing service and send requests to the older app.
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if os.name == "nt":
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind(("127.0.0.1", port))
            server = make_server("127.0.0.1", port, app, threaded=True)
            break
        except (OSError, SystemExit):
            continue
    if server is None:
        raise SystemExit("5180 附近端口不可用，请通过 --port 指定其他端口。")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\nYOLOv10 demo: {url}\nClose this console to stop.\n", flush=True)
    if args.open:
        webbrowser.open(url)
    server.serve_forever()
