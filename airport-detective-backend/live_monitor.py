"""Four independent video sources, one fair GPU scheduler and persistent evidence."""
import copy
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime

from flask import jsonify, request

from analytics import SceneAnalyzer, draw_scene
from engine import Detector, cv2, MODEL_NAMES, ROOT

LIVE_PREVIEW_MAX_EDGE = 1920
LIVE_PREVIEW_JPEG_QUALITY = 95


def shuttle_number(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,2}", value) or int(value) == 0:
        raise ValueError("接驳车编号应为 01–99。")
    return f"{int(value):02d}"


def video_sources(server, number):
    """Read up to four local inputs; an absent/empty folder has no connected lines."""
    number = shuttle_number(number)
    folder = server.VIDEOS / number
    if folder.is_symlink() or folder.resolve().parent != server.VIDEOS.resolve():
        raise ValueError(f"无效的视频目录 videos/{number}/。")
    if not folder.exists():
        return folder, []
    if not folder.is_dir():
        raise ValueError(f"videos/{number}/ 必须是文件夹。")
    def natural_key(path):
        return ([ (1, int(part)) if part.isdigit() else (0, part.casefold())
                  for part in re.split(r"([0-9]+)", path.name) ], path.name)
    sources = sorted((path for path in folder.iterdir()
                      if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
                      and path.suffix.lower() in server.EXTENSIONS), key=natural_key)
    if len(sources) > 4:
        relative = folder.relative_to(server.VIDEOS).as_posix()
        label = "videos/" if relative == "." else f"videos/{relative}/"
        raise ValueError(f"接驳车 {number}：{label} 最多支持四个视频，当前找到 {len(sources)} 个；请移出多余视频。")
    return folder, sources


class ShuttleMonitor:
    def __init__(self, server, number="04"):
        self.s = server
        self.number = shuttle_number(number)
        self.guard = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.session = None
        # Reopen the last evidence after a server restart, without claiming it is live.
        saved = server.DATA / f"shuttle-{self.number}.json"
        if saved.exists():
            try:
                previous = json.loads(saved.read_text(encoding="utf-8"))
                if 1 <= len(previous.get("cameras", [])) <= 4 and all(c["job_id"] in server.jobs for c in previous["cameras"]):
                    self.session = previous
            except (ValueError, KeyError, OSError):
                logging.exception("Unable to recover the previous four-camera session")

    def state(self):
        with self.guard, self.s.lock:
            session = copy.deepcopy(self.session)
            if not session:
                return {"trip_id": f"T-{self.number}", "status": "idle", "model": "yolov10n.pt", "cameras": [], "alerts": []}
            session.setdefault("model", self.s.jobs[session["cameras"][0]["job_id"]].get("options", {}).get("model", "yolov10n.pt"))
            active = self.worker is not None and self.worker.is_alive()
            session["status"] = "running" if active and not self.stop_event.is_set() else "stopped"
            alerts = []
            for camera in session["cameras"]:
                job = self.s.jobs[camera["job_id"]]
                camera.update(status=job["status"], message=job.get("message", ""),
                              archive_cleared=job.get("archive_cleared", False),
                              frame=job.get("frame", 0), video_time=job.get("time", 0),
                              cycle=job.get("cycle", 1), preview_version=job.get("preview_version", 0),
                              fps=job.get("inference_fps", 0),
                              preview=f"/api/jobs/{job['id']}/preview")
                archive = self.s.DATA / "jobs" / job["id"] / "archive.json"
                if job.get("archive_cleared"):
                    continue
                for record in json.loads(archive.read_text(encoding="utf-8")) if archive.exists() else []:
                    if record.get("warning_level") not in {"confirmed", "suspected"}:
                        continue
                    alerts.append({**record, "key": f"{job['id']}:{record['id']}",
                                   "job_id": job["id"], "camera_id": camera["id"],
                                   "package_photo": f"/api/jobs/{job['id']}/crops/{record.get('event_crop', record['crop'])}",
                                   "owners": [{**owner, "photo": self.s.person_photo_url(job['id'],owner['person_id'])}
                                              for owner in record.get("owners", [])]})
            session["alerts"] = sorted(alerts, key=lambda a: (a["warning_level"] != "confirmed", a["camera_id"], a["id"]))
            return session

    def start(self, model=None):
        with self.guard, self.s.lock:
            model = model or (self.session or {}).get("model", "yolov10n.pt")
            if model not in MODEL_NAMES or not (ROOT / "models" / model).is_file():
                raise ValueError("模型文件不存在，请选择本地 YOLOv10 模型。")
            if self.worker and self.worker.is_alive():
                if model != self.state()["model"]:
                    raise ValueError("请先停止检测，再切换模型并启动。")
                if self.stop_event.is_set():
                    raise ValueError("检测正在停止，请稍后再启动。")
                return self.state()
            folder, sources = video_sources(self.s, self.number)
            if not sources:
                return self.state()  # No jobs or GPU worker for disconnected lines.
            if any(j["status"] not in self.s.TERMINAL for j in self.s.jobs.values()):
                raise ValueError("已有其他车辆或识别任务正在运行，请先停止该任务再启动四路监控。")
            metas = [self.s.video_info(source) for source in sources]
            self.session = {"trip_id": f"T-{self.number}", "id": uuid.uuid4().hex, "model": model,
                            "source_directory": folder.relative_to(self.s.VIDEOS).as_posix(),
                            "created": datetime.now().isoformat(timespec="seconds"), "cameras": []}
            for i, meta in enumerate(metas, 1):
                jid = uuid.uuid4().hex
                folder = self.s.DATA / "jobs" / jid
                for child in ("crops", "people"):
                    (folder / child).mkdir(parents=True, exist_ok=True)
                opts = {"model": model, "device": "auto", "confidence": .25,
                        "imgsz": "source", "scope": "luggage", "stride": 1, "linger_seconds": 3}
                source_stat = sources[i-1].stat()
                self.s.jobs[jid] = {"id": jid, "created": self.session["created"], "source": {"name": sources[i-1].name, **meta,
                                   "video_path": sources[i-1].relative_to(self.s.VIDEOS).as_posix(),
                                   "mtime_ns": source_stat.st_mtime_ns},
                                   "options": opts, "train": {"number": f"接驳车 {self.number}", "route": "樟宜机场接驳线路", "carriage": self.number, "camera": f"CAM-{i:02d}"},
                                   "status": "loading", "message": "正在加载四路监控模型…", "live_camera": i,
                                   "progress": 0, "processed": 0, "frame": 0, "time": 0, "elapsed": 0,
                                   "preview_version": 0, "cancel": False, "archive_cleared": False,
                                   "boxes": [], "counts": [], "timeline": [], "artifacts": [], "cycle": 1,
                                   "current_count": 0, "peak_count": 0, "inference_fps": 0,
                                   "luggage_candidates": [], "candidate_summary": [], "alert_count": 0}
                self.s.update(jid)
                self.session["cameras"].append({"id": i, "job_id": jid, "source": sources[i-1].name,
                                                "source_path": sources[i-1].relative_to(self.s.VIDEOS).as_posix()})
            self.s.json_write(self.s.DATA / f"shuttle-{self.number}.json", self.session)
            self.stop_event.clear()
            self.worker = threading.Thread(target=self.run, name=f"shuttle-{self.number}-inference", daemon=True)
            self.worker.start()
            return self.state()

    def stop(self):
        with self.guard:
            self.stop_event.set()
        return self.state()

    def run(self):
        streams = []
        started = time.monotonic()
        try:
            detector = Detector()
            device = detector.load(self.session["model"], "auto")
            for camera in self.session["cameras"]:
                job = self.s.jobs[camera["job_id"]]
                streams.append({"jid": job["id"], "cap": cv2.VideoCapture(str(self.s.VIDEOS / camera.get("source_path", camera["source"]))),
                                "analyzer": SceneAnalyzer(3), "frame": 0, "cycle": 1, "processed": 0,
                                "next_due": 0, "published": 0, "failed": False})
                self.s.update(job["id"], status="running", message="四路实时检测中")
            while not self.stop_event.is_set():
                runnable = False
                for stream in streams:
                    if self.stop_event.is_set():
                        break
                    jid = stream["jid"]
                    job = self.s.jobs[jid]
                    if stream["failed"] or job.get("cancel"):
                        continue
                    runnable = True
                    now = time.monotonic()
                    if now < stream["next_due"]:
                        continue
                    try:
                        ok, frame = stream["cap"].read()
                        if not ok:
                            # Reset trajectories at a loop boundary, but keep ID counters
                            # and all persisted warning records. IDs never collide across loops.
                            stream["cap"].set(cv2.CAP_PROP_POS_FRAMES, 0)
                            ok, frame = stream["cap"].read()
                            if not ok:
                                raise ValueError("无法重新读取示例视频")
                            stream["analyzer"].tracks.clear()
                            stream["analyzer"].luggage_history.clear()
                            stream["frame"] = 0
                            stream["cycle"] += 1
                        stream["frame"] += 1
                        h, w = frame.shape[:2]
                        annotated, boxes = detector.predict(frame, job["options"], device)
                        timestamp = (stream["frame"] - 1) / job["source"]["fps"]
                        # Use a monotonic video clock in the cumulative archive.
                        evidence_time = timestamp + (stream["cycle"] - 1) * job["source"]["duration"]
                        boxes, candidates = stream["analyzer"].update(boxes, stream["frame"], evidence_time, w, h, frame=frame)
                        folder = self.s.DATA / "jobs" / jid
                        for candidate in candidates:
                            if candidate.get("alarm_frame"):
                                candidate["event_crop"] = f"crop-{candidate['id']}-event-{candidate['alarm_revision']}.jpg"
                                if candidate["alarm_frame"] == stream["frame"]:
                                    self.s.save_candidate_crop(folder, frame, {**candidate, "crop": candidate["event_crop"]}, w, h)
                        for box in boxes:
                            if box["class_id"] == 0:
                                self.s.save_person_crop(folder, frame, box, w, h)
                            elif box.get("track_id", "").startswith("L"):
                                self.s.save_candidate_crop(folder, frame, {"bbox": box["xyxy"], "crop": f"crop-{box['track_id']}.jpg"}, w, h)
                        stream["processed"] += 1
                        if candidates:
                            with self.s.lock:
                                self.s.save_local_archive(jid, candidates)
                        now = time.monotonic()
                        if now - stream["published"] >= .25:
                            # Confirmation changes the live bounding box to red as well.
                            with self.s.lock:
                                archive_path = folder / "archive.json"
                                levels = {c["id"]: c.get("warning_level", "none") for c in json.loads(archive_path.read_text(encoding="utf-8"))} if archive_path.exists() else {}
                                drawn = [{**c, "warning_level": levels.get(c["id"], c.get("warning_level", "none"))} for c in candidates]
                                annotated = draw_scene(annotated, boxes, drawn)
                                scale = min(1., LIVE_PREVIEW_MAX_EDGE / max(w, h))
                                if scale < 1:
                                    annotated = cv2.resize(annotated, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
                                self.s.write_jpeg(folder / "preview.jpg", annotated, quality=LIVE_PREVIEW_JPEG_QUALITY)
                                self.s.update(jid, frame=stream["frame"], processed=stream["processed"], time=round(timestamp, 2),
                                              cycle=stream["cycle"], preview_version=stream["processed"],
                                              progress=round(100*stream["frame"]/max(1, job["source"]["frames"]), 1),
                                              boxes=boxes, current_count=len(boxes), output_width=w, output_height=h,
                                              elapsed=round(now-started, 1), inference_fps=round(stream["processed"]/max(.001, now-started), 1),
                                              luggage_candidates=candidates, candidate_summary=stream["analyzer"].summary())
                            stream["published"] = now
                        stream["next_due"] = now + 1 / min(10, job["source"]["fps"])
                    except Exception as exc:
                        logging.exception("Camera %s failed", jid)
                        stream["failed"] = True
                        message = "原分辨率推理显存不足，请停止检测后选择较小的 YOLOv10 模型或使用 CPU。" if "out of memory" in str(exc).lower() else str(exc)
                        self.s.update(jid, status="failed", message=message)
                if not runnable:
                    break
                self.stop_event.wait(.005)
        except Exception as exc:
            logging.exception("Four-camera monitor failed")
            for camera in self.session["cameras"]:
                self.s.update(camera["job_id"], status="failed", message=str(exc))
        finally:
            for stream in streams:
                stream["cap"].release()
                if self.s.jobs[stream["jid"]]["status"] != "failed":
                    self.s.update(stream["jid"], status="cancelled", message="监控已停止，警报档案和照片已保留")


class ShuttleFleet:
    """Separate sessions/evidence per vehicle; preserve one active GPU task group."""
    def __init__(self, server):
        self.s = server
        self.guard = threading.RLock()
        self.monitors = {}

    def get(self, number):
        number = shuttle_number(number)
        with self.guard:
            if number not in self.monitors:
                self.monitors[number] = ShuttleMonitor(self.s, number)
            return self.monitors[number]

    def describe(self, number):
        monitor = self.get(number)
        state = monitor.state()
        state["shuttle_id"] = monitor.number
        sources = []
        try:
            folder, sources = video_sources(self.s, monitor.number)
            state.update(ready=bool(sources), configuration_error="",
                         source_directory="videos/" + (folder.relative_to(self.s.VIDEOS).as_posix().strip(".") + "/").lstrip("/"),
                         source_videos=[p.name for p in sources])
        except ValueError as exc:
            state.update(ready=False, configuration_error=str(exc), source_videos=[],
                         source_directory=f"videos/{monitor.number}/")
        worker = monitor.worker
        active = worker is not None and worker.is_alive()
        slots = []
        for camera_id in range(1, 5):
            camera = next((c for c in state["cameras"] if c["id"] == camera_id), None)
            source = camera["source"] if active and camera else sources[camera_id-1].name if not active and camera_id <= len(sources) else None
            matching_job = camera if source and camera and camera["source"] == source and (
                active or camera.get("source_path", f"{monitor.number}/{source}") == f"{monitor.number}/{source}") else None
            slots.append({"id": camera_id, "connected": source is not None, "source": source,
                          "job_id": matching_job["job_id"] if matching_job else None,
                          "message": "" if source else "当前未接通线路"})
        state.update(camera_slots=slots, connected_count=sum(slot["connected"] for slot in slots))
        return state

    def states(self):
        numbers = {f"{i:02d}" for i in range(1, 9)}
        with self.guard:
            numbers.update(self.monitors)
        for folder in self.s.VIDEOS.iterdir():
            if folder.is_dir() and re.fullmatch(r"[0-9]{2}", folder.name) and folder.name != "00":
                numbers.add(folder.name)
        for saved in self.s.DATA.glob("shuttle-*.json"):
            number = saved.stem.removeprefix("shuttle-")
            if re.fullmatch(r"[0-9]{2}", number) and number != "00":
                numbers.add(number)
        return {"shuttles": [self.describe(number) for number in sorted(numbers)]}

    def stop(self):
        with self.guard:
            monitors = list(self.monitors.values())
        for monitor in monitors:
            monitor.stop()

    @property
    def worker(self):
        with self.guard:
            return next((m.worker for m in self.monitors.values() if m.worker and m.worker.is_alive()), None)


def register(server):
    fleet = ShuttleFleet(server)
    def start(shuttle_id):
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or ("model" in body and not isinstance(body["model"], str)):
            raise ValueError("无效的模型参数。")
        fleet.get(shuttle_id).start(body.get("model"))
        return jsonify(fleet.describe(shuttle_id)), 202
    server.app.add_url_rule("/api/shuttles", "shuttles", lambda: jsonify(fleet.states()))
    server.app.add_url_rule("/api/shuttles/<shuttle_id>/state", "shuttle_state", lambda shuttle_id: jsonify(fleet.describe(shuttle_id)))
    server.app.add_url_rule("/api/shuttles/<shuttle_id>/start", "shuttle_start", start, methods=["POST"])
    def stop(shuttle_id):
        fleet.get(shuttle_id).stop()
        return jsonify(fleet.describe(shuttle_id))
    server.app.add_url_rule("/api/shuttles/<shuttle_id>/stop", "shuttle_stop", stop, methods=["POST"])
    return fleet
