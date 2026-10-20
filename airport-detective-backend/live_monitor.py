"""Four independent video sources, one fair GPU scheduler and persistent evidence."""
import copy
import json
import logging
import threading
import time
import uuid
from datetime import datetime

from flask import jsonify, request

from analytics import SceneAnalyzer, draw_scene
from engine import Detector, cv2, MODEL_NAMES, ROOT


class ShuttleMonitor:
    def __init__(self, server):
        self.s = server
        self.guard = threading.RLock()
        self.stop_event = threading.Event()
        self.worker = None
        self.session = None
        # Reopen the last evidence after a server restart, without claiming it is live.
        saved = server.DATA / "shuttle-04.json"
        if saved.exists():
            try:
                previous = json.loads(saved.read_text(encoding="utf-8"))
                if len(previous.get("cameras", [])) == 4 and all(c["job_id"] in server.jobs for c in previous["cameras"]):
                    self.session = previous
            except (ValueError, KeyError, OSError):
                logging.exception("Unable to recover the previous four-camera session")

    def state(self):
        with self.guard, self.s.lock:
            session = copy.deepcopy(self.session)
            if not session:
                return {"trip_id": "T-04", "status": "idle", "model": "yolov10n.pt", "cameras": [], "alerts": []}
            session.setdefault("model", self.s.jobs[session["cameras"][0]["job_id"]]["options"]["model"])
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
                                   "package_photo": f"/api/jobs/{job['id']}/crops/{record['crop']}",
                                   "owners": [{**owner, "photo": f"/api/jobs/{job['id']}/people/person-{owner['person_id']}.jpg"}
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
                return self.state()
            if any(j["status"] not in self.s.TERMINAL for j in self.s.jobs.values()):
                raise ValueError("已有识别任务正在运行，请先停止该任务再启动四路监控。")
            sources = [self.s.VIDEOS / f"camera-{i}.mp4" for i in range(1, 5)]
            metas = [self.s.video_info(source) for source in sources]
            self.session = {"trip_id": "T-04", "id": uuid.uuid4().hex, "model": model,
                            "created": datetime.now().isoformat(timespec="seconds"), "cameras": []}
            for i, meta in enumerate(metas, 1):
                jid = uuid.uuid4().hex
                folder = self.s.DATA / "jobs" / jid
                for child in ("crops", "people"):
                    (folder / child).mkdir(parents=True, exist_ok=True)
                opts = {"model": model, "device": "auto", "confidence": .25,
                        "imgsz": 640, "scope": "luggage", "stride": 1, "linger_seconds": 3}
                self.s.jobs[jid] = {"id": jid, "created": self.session["created"], "source": {"name": sources[i-1].name, **meta},
                                   "options": opts, "train": {"number": "接驳车 04", "route": "樟宜机场 T1 → T3", "carriage": "04", "camera": f"CAM-{i:02d}"},
                                   "status": "loading", "message": "正在加载四路监控模型…", "live_camera": i,
                                   "progress": 0, "processed": 0, "frame": 0, "time": 0, "elapsed": 0,
                                   "preview_version": 0, "cancel": False, "archive_cleared": False,
                                   "boxes": [], "counts": [], "timeline": [], "artifacts": [], "cycle": 1,
                                   "current_count": 0, "peak_count": 0, "inference_fps": 0,
                                   "luggage_candidates": [], "candidate_summary": [], "alert_count": 0}
                self.s.update(jid)
                self.session["cameras"].append({"id": i, "job_id": jid, "source": sources[i-1].name})
            self.s.json_write(self.s.DATA / "shuttle-04.json", self.session)
            self.stop_event.clear()
            self.worker = threading.Thread(target=self.run, name="shuttle-04-inference", daemon=True)
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
                streams.append({"jid": job["id"], "cap": cv2.VideoCapture(str(self.s.VIDEOS / camera["source"])),
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
                        scale = min(1., 1280 / max(w, h))
                        if scale < 1:
                            frame = cv2.resize(frame, (int(w*scale), int(h*scale)))
                        h, w = frame.shape[:2]
                        annotated, boxes = detector.predict(frame, job["options"], device)
                        timestamp = (stream["frame"] - 1) / job["source"]["fps"]
                        # Use a monotonic video clock in the cumulative archive.
                        evidence_time = timestamp + (stream["cycle"] - 1) * job["source"]["duration"]
                        boxes, candidates = stream["analyzer"].update(boxes, stream["frame"], evidence_time, w, h)
                        folder = self.s.DATA / "jobs" / jid
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
                                confirmed = {c["id"] for c in json.loads(archive_path.read_text(encoding="utf-8")) if c.get("warning_level") == "confirmed"} if archive_path.exists() else set()
                                drawn = [{**c, "risk": "high", "warning_level": "confirmed"} if c["id"] in confirmed else c for c in candidates]
                                annotated = draw_scene(annotated, boxes, drawn)
                                self.s.write_jpeg(folder / "preview.jpg", annotated)
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
                        self.s.update(jid, status="failed", message=str(exc))
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


def register(server):
    monitor = ShuttleMonitor(server)
    def start():
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or ("model" in body and not isinstance(body["model"], str)):
            raise ValueError("无效的模型参数。")
        return jsonify(monitor.start(body.get("model"))), 202
    server.app.add_url_rule("/api/shuttles/04/state", "shuttle_state", lambda: jsonify(monitor.state()))
    server.app.add_url_rule("/api/shuttles/04/start", "shuttle_start", start, methods=["POST"])
    server.app.add_url_rule("/api/shuttles/04/stop", "shuttle_stop", lambda: jsonify(monitor.stop()), methods=["POST"])
    return monitor
