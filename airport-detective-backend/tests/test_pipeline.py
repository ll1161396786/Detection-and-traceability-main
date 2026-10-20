"""Integration checks use real video frames and real local YOLOv10 weights.

Temporary test outputs stay separate from the user's uploaded videos and jobs.
"""
import csv
import io
import json
import tempfile
import threading
import time
import unittest
import numpy as np
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import app as server
from engine import ROOT, Detector, cv2
from analytics import SceneAnalyzer


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="yolov10-tests-")
        cls.root = Path(cls.temp.name)
        cls.fixture = cls.root / "short.avi"
        cap = cv2.VideoCapture(str(ROOT / "videos" / "sample-carriage.mp4"))
        writer = cv2.VideoWriter(str(cls.fixture), cv2.VideoWriter_fourcc(*"MJPG"), 25, (960, 540))
        for _ in range(12):
            ok, frame = cap.read()
            if not ok:
                raise AssertionError("Missing real video fixture")
            writer.write(frame)
        writer.release()
        cap.release()
        cls.raw = cls.fixture.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.data = self.root / self._testMethodName
        (self.data / "uploads").mkdir(parents=True)
        (self.data / "jobs").mkdir()
        self.patches = [patch.object(server, "DATA", self.data), patch.object(server, "jobs", {})]
        for p in self.patches:
            p.start()
        self.client = server.app.test_client()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def upload(self):
        response = self.client.post("/api/uploads", data={"video": (io.BytesIO(self.raw), "测试车厢.avi")})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def wait(self, jid):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{jid}").json
            if job["status"] in server.TERMINAL:
                # The worker closes video handles in finally just after publishing status.
                for _ in range(100):
                    if not (self.data / "jobs" / jid / "working.avi").exists():
                        return job
                    time.sleep(.05)
                return job
            time.sleep(.1)
        self.fail("Job timed out")

    def test_invalid_inputs_and_origin(self):
        self.assertEqual(self.client.post("/api/uploads").status_code, 400)
        for filename in ("wrong.exe", "broken.mp4"):
            response = self.client.post("/api/uploads", data={"video": (io.BytesIO(b"not a video"), filename)})
            self.assertEqual(response.status_code, 400)
        for body in ({"library_name":"../app.py"}, {"confidence":"nan"}, {"stride":0},
                     {"model":"../bad.pt"}, {"linger_seconds":0}):
            self.assertEqual(self.client.post("/api/jobs", json=body).status_code, 400)
        self.assertEqual(self.client.post("/api/jobs", json={}, headers={"Origin":"https://example.org"}).status_code, 403)
        self.assertEqual(self.client.get("/api/uploads/invalid/video").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs/missing/files/result.mp4").status_code, 404)
        self.assertEqual(self.client.get("/api/library/media/../app.py").status_code, 404)

    def test_real_video_upload_inference_and_exports(self):
        meta = self.upload()
        self.assertEqual(meta["frames"], 12)
        self.assertEqual(meta["name"], "测试车厢.avi")
        poster = self.client.get(f"/api/uploads/{meta['id']}/poster")
        self.assertEqual(poster.status_code, 200)
        poster.close()
        response = self.client.post("/api/jobs", json={"upload_id":meta["id"], "stride":2, "scope":"luggage"})
        self.assertEqual(response.status_code, 202)
        jid = response.json["id"]
        job = self.wait(jid)
        self.assertEqual(job["status"], "completed", job["message"])
        self.assertEqual(job["processed"], 6)
        self.assertEqual(job["frame"], 12)
        self.assertGreater(job["peak_count"], 0)
        report = self.client.get(f"/api/jobs/{jid}/files/report.json")
        summary = json.loads(report.data)
        report.close()
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["train"]["number"], "DT-0421")
        self.assertTrue(summary["candidate_summary"])
        folder = self.data / "jobs" / jid
        rows = [json.loads(line) for line in (folder / "frames.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["frame"] for r in rows], [1, 3, 5, 7, 9, 11])
        totals = Counter(b["class_id"] for row in rows for b in row["boxes"])
        self.assertTrue(set(totals) <= {0,24,26,28})
        self.assertEqual(totals, Counter({r["class_id"]:r["detections"] for r in summary["counts"]}))
        self.assertIn("luggage_candidates", rows[-1])
        with (folder / "detections.csv").open(encoding="utf-8-sig", newline="") as f:
            self.assertEqual(len(list(csv.DictReader(f))), sum(totals.values()))
        cap = cv2.VideoCapture(str(folder / "result.mp4"))
        self.assertEqual(cap.get(cv2.CAP_PROP_FRAME_COUNT), 6)
        self.assertAlmostEqual(cap.get(cv2.CAP_PROP_FPS), 12.5, places=1)
        self.assertTrue(cap.read()[0])
        cap.release()
        download = self.client.get(f"/api/jobs/{jid}/files/result.mp4?download=1")
        self.assertIn("attachment", download.headers["Content-Disposition"])
        download.close()
        partial = self.client.get(f"/api/jobs/{jid}/files/result.mp4", headers={"Range":"bytes=0-99"})
        self.assertEqual(partial.status_code, 206)
        partial.close()
        crop_name = summary["candidate_summary"][0]["crop"]
        crop = self.client.get(f"/api/jobs/{jid}/crops/{crop_name}")
        self.assertEqual(crop.status_code, 200)
        self.assertGreater(len(crop.data), 500)
        crop.close()
        candidate_id = summary["candidate_summary"][0]["id"]
        evidence = self.client.get(f"/api/jobs/{jid}/evidence/{candidate_id}")
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(evidence.json["candidate"]["id"], candidate_id)
        self.assertEqual(evidence.json["total_frames"], len(evidence.json["frames"]))
        self.assertGreater(evidence.json["total_frames"], 0)
        evidence_frame = evidence.json["frames"][0]
        image = self.client.get(f"/api/jobs/{jid}/evidence/{candidate_id}/frames/{evidence_frame['sequence']}.jpg")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.mimetype, "image/jpeg")
        self.assertGreater(len(image.data), 500)
        image.close()
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/evidence/L999").status_code, 404)
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/evidence/{candidate_id}/frames/99999.jpg").status_code, 404)
        owners = summary["candidate_summary"][0]["owners"]
        self.assertTrue(owners)
        archive = self.client.get(f"/api/jobs/{jid}/archive")
        self.assertEqual(archive.status_code, 200)
        self.assertFalse(archive.json["cleared"])
        self.assertEqual(archive.json["record_count"], len(summary["candidate_summary"]))
        self.assertEqual(archive.json["records"][0]["package_photo"],
                         f"/api/jobs/{jid}/crops/{crop_name}")
        self.assertIn("photo", archive.json["records"][0]["owners"][0])
        person = self.client.get(f"/api/jobs/{jid}/people/person-{owners[0]['person_id']}.jpg")
        self.assertEqual(person.status_code, 200)
        self.assertGreater(len(person.data), 500)
        person.close()
        for seconds, expected in ((0, 1), (.08, 3), (.4, 11), (999, 11)):
            frame = self.client.get(f"/api/jobs/{jid}/frame?time={seconds}")
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.json["frame"], expected)
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/frame?time=nan").status_code, 400)
        cleared = self.client.post(f"/api/jobs/{jid}/archive/clear", json={})
        self.assertEqual(cleared.status_code, 200)
        self.assertTrue(cleared.json["archive_cleared"])
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/crops/{crop_name}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/evidence/{candidate_id}").status_code, 404)
        cleared_archive = self.client.get(f"/api/jobs/{jid}/archive")
        self.assertTrue(cleared_archive.json["cleared"])
        self.assertEqual(cleared_archive.json["records"], [])
        result_file = self.client.get(f"/api/jobs/{jid}/files/result.mp4")
        self.assertEqual(result_file.status_code, 200)
        result_file.close()

    def test_scene_analyzer_owner_and_abandoned_states(self):
        analyzer = SceneAnalyzer(linger_seconds=2)
        def box(class_id, xyxy, label, label_zh):
            return {"class_id":class_id,"xyxy":xyxy,"label":label,"label_zh":label_zh,"confidence":.9}
        last = None
        for frame in range(1, 5):
            _, candidates = analyzer.update([
                box(0, [100,100,220,420], "person", "人"),
                box(28, [230,300,310,410], "suitcase", "行李箱"),
            ], frame, frame - 1, 960, 540)
            last = candidates
        self.assertEqual(last[0]["state"], "随身携带")
        self.assertTrue(last[0]["owners"])
        for frame in range(5, 8):
            _, candidates = analyzer.update([
                box(0, [760,100,880,420], "person", "人"),
                box(28, [230,300,310,410], "suitcase", "行李箱"),
            ], frame, frame - 1, 960, 540)
        self.assertEqual(candidates[0]["state"], "疑似遗留")
        self.assertEqual(candidates[0]["risk"], "high")

    def test_cancel_and_single_job_limit(self):
        meta = self.upload()
        entered, release = threading.Event(), threading.Event()
        def loading(*_):
            entered.set()
            release.wait(10)
            return "cpu"
        with patch.object(server.detector, "load", side_effect=loading):
            response = self.client.post("/api/jobs", json={"upload_id":meta["id"]})
            jid = response.json["id"]
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.client.post("/api/jobs", json={"upload_id":meta["id"]}).status_code, 409)
                self.assertEqual(self.client.post(f"/api/jobs/{jid}/cancel", json={}).status_code, 200)
            finally:
                release.set()
            job = self.wait(jid)
            self.assertEqual(job["status"], "cancelled")
            self.assertFalse(job["archive_cleared"])
            self.assertFalse(self.client.get(f"/api/jobs/{jid}/archive").json["cleared"])
            self.assertEqual(self.client.get(f"/api/jobs/{jid}/files/result.mp4").status_code, 404)

    def test_model_failure_is_reported(self):
        meta = self.upload()
        with patch.object(server.detector, "load", side_effect=RuntimeError("test model failure")):
            response = self.client.post("/api/jobs", json={"upload_id":meta["id"]})
            job = self.wait(response.json["id"])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["artifacts"], [])
        self.assertIn("test model failure", job["message"])

    def test_cpu_inference(self):
        detector = Detector()
        device = detector.load("yolov10n.pt", "cpu")
        cap = cv2.VideoCapture(str(self.fixture))
        ok, frame = cap.read()
        cap.release()
        self.assertTrue(ok)
        image, boxes = detector.predict(frame, {"confidence":.25,"imgsz":320,"scope":"all"}, device)
        self.assertEqual(image.shape, frame.shape)
        self.assertGreater(len(boxes), 0)

    def test_unicode_photos_and_four_digit_track_ids(self):
        jid = "c" * 32
        folder = self.data / "jobs" / jid / "中文照片"
        (folder / "crops").mkdir(parents=True)
        (folder / "people").mkdir()
        frame = np.full((80, 120, 3), 180, dtype=np.uint8)
        server.save_candidate_crop(folder, frame, {"bbox": [10, 10, 60, 65], "crop": "crop-L1001.jpg"}, 120, 80)
        server.save_person_crop(folder, frame, {"track_id": "P1001", "xyxy": [5, 5, 70, 75]}, 120, 80)
        for path in folder.glob("*/*.jpg"):
            decoded = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
            self.assertIsNotNone(decoded)
            self.assertGreater(float(decoded.mean()), 150)
        actual = folder.parent
        for name in ("crops", "people"):
            (actual / name).mkdir()
            for path in (folder / name).glob("*.jpg"):
                (actual / name / path.name).write_bytes(path.read_bytes())
        server.jobs[jid] = {"id": jid, "status": "running"}
        for route in ("crops/crop-L1001.jpg", "people/person-P1001.jpg"):
            response = self.client.get(f"/api/jobs/{jid}/{route}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("max-age", response.headers["Cache-Control"])
            response.close()
        with patch.object(cv2, "imencode", return_value=(False, None)):
            with self.assertRaises(OSError):
                server.write_jpeg(folder / "bad.jpg", frame)
        self.assertFalse((folder / "bad.jpg").exists())

    def test_warning_counts_persist_and_confirmation_survives_live_updates(self):
        jid = "b" * 32
        folder = self.data / "jobs" / jid
        folder.mkdir()
        server.jobs[jid] = {"id": jid, "status": "running", "archive_cleared": False}
        item = {"id": "L001", "crop": "crop-L001.jpg", "risk": "high", "owners": []}
        server.update(jid, candidate_summary=[item])
        server.update(jid, candidate_summary=[{**item, "risk": "low"}])
        archive = self.client.get(f"/api/jobs/{jid}/archive").json
        self.assertEqual(archive["record_count"], 1)
        self.assertEqual(archive["records"][0]["warning_level"], "suspected")
        confirmed = self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={"confirmed": True})
        self.assertEqual(confirmed.status_code, 200)
        server.update(jid, candidate_summary=[{**item, "risk": "low"}])
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/archive").json["records"][0]["warning_level"], "confirmed")
        disk = json.loads((folder / "archive.json").read_text(encoding="utf-8"))
        self.assertEqual(disk[0]["warning_level"], "confirmed")
        reverted = self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={"confirmed": False})
        self.assertEqual(reverted.json["records"][0]["warning_level"], "suspected")
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L999/confirm", json={}).status_code, 404)
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={"confirmed": "yes"}).status_code, 400)
        server.jobs[jid]["archive_cleared"] = True
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={}).status_code, 404)

    def test_disk_archive_survives_memory_reset_and_stop_preserves_outputs(self):
        jid = "a" * 32
        folder = self.data / "jobs" / jid
        folder.mkdir()
        server.jobs[jid] = {"id": jid, "status": "running", "archive_cleared": False}
        candidate = {"id": "L001", "crop": "crop-L001.jpg", "stationary_seconds": 2,
                     "owners": [{"person_id": "P001", "probability": .8, "near_frames": 3}]}
        server.update(jid, candidate_summary=[candidate])
        server.update(jid, candidate_summary=[{**candidate, "owners": [
            {"person_id": "P001", "probability": .4, "near_frames": 5},
            {"person_id": "P002", "probability": .7, "near_frames": 2}]}])
        self.assertTrue((folder / "archive.json").is_file())
        # Simulate a service restart: recover status, then discard summary memory.
        server.jobs[jid] = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        server.jobs[jid]["candidate_summary"] = []
        archive = self.client.get(f"/api/jobs/{jid}/archive").json
        self.assertEqual(archive["record_count"], 1)
        self.assertEqual(len(archive["records"][0]["owners"]), 2)
        self.assertEqual(archive["records"][0]["owners"][0]["probability"], .8)
        self.assertEqual(archive["records"][0]["owners"][0]["near_frames"], 5)
        for name in ("result.mp4", "frames.jsonl", "report.json", "detections.csv", "preview.jpg"):
            (folder / name).write_bytes(b"test output")
        (folder / "people").mkdir()
        (folder / "people" / "person-P001.jpg").write_bytes(b"photo")
        source = self.data / "uploads" / "source.mp4"
        source.write_bytes(b"source video")
        server.jobs[jid]["status"] = "completed"
        response = self.client.post(f"/api/jobs/{jid}/cancel", json={})
        self.assertFalse(response.json["archive_cleared"])
        self.assertTrue((folder / "result.mp4").is_file())
        self.assertTrue((folder / "people" / "person-P001.jpg").is_file())
        self.assertTrue(source.is_file())
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/archive").json["record_count"], 1)
        cleared = self.client.post(f"/api/jobs/{jid}/archive/clear", json={})
        self.assertTrue(cleared.json["archive_cleared"])
        self.assertFalse((folder / "people").exists())
        self.assertTrue((folder / "result.mp4").is_file())
        self.assertTrue(source.is_file())
        self.assertEqual(self.client.get(f"/api/jobs/{jid}/archive").json["records"], [])


if __name__ == "__main__":
    unittest.main()
