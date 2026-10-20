"""Isolated four-camera inference, loop boundaries and backend warning mapping."""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app as server
from engine import ROOT, cv2
from live_monitor import ShuttleMonitor


class LiveMonitorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="four-camera-tests-")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.videos = self.root / "videos"
        (self.data / "jobs").mkdir(parents=True)
        self.videos.mkdir()
        self.patches = [patch.object(server, "DATA", self.data), patch.object(server, "VIDEOS", self.videos), patch.object(server, "jobs", {})]
        for item in self.patches:
            item.start()
        self.monitor = ShuttleMonitor(server)
        self.client = server.app.test_client()

    def tearDown(self):
        self.monitor.stop()
        if self.monitor.worker:
            self.monitor.worker.join(15)
            self.assertFalse(self.monitor.worker.is_alive())
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_real_four_camera_preview_loop_and_stop(self):
        # Real, distinct frames from each of the user's four videos, shortened
        # solely for an isolated loop-boundary check.
        for i in range(1, 5):
            cap = cv2.VideoCapture(str(ROOT / "videos" / f"camera-{i}.mp4"))
            writer = cv2.VideoWriter(str(self.videos / f"camera-{i}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 25, (640, 360))
            self.assertTrue(writer.isOpened())
            for _ in range(8):
                ok, frame = cap.read()
                self.assertTrue(ok)
                writer.write(cv2.resize(frame, (640, 360)))
            cap.release()
            writer.release()
        started = self.monitor.start()
        self.assertEqual(len(started["cameras"]), 4)
        self.assertEqual(started["id"], self.monitor.start()["id"])
        self.assertEqual(self.client.post("/api/jobs", json={}).status_code, 409)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            state = self.monitor.state()
            if all(c["cycle"] >= 2 and c["preview_version"] > 0 for c in state["cameras"]):
                break
            self.assertFalse(any(c["status"] == "failed" for c in state["cameras"]), state)
            time.sleep(.1)
        self.assertTrue(all(c["cycle"] >= 2 for c in state["cameras"]), state)
        self.assertEqual(len({c["job_id"] for c in state["cameras"]}), 4)
        for camera in state["cameras"]:
            response = self.client.get(camera["preview"])
            self.assertEqual(response.status_code, 200)
            import numpy as np
            self.assertIsNotNone(cv2.imdecode(np.frombuffer(response.data, dtype=np.uint8), cv2.IMREAD_COLOR))
        self.monitor.stop()
        self.monitor.worker.join(10)
        self.assertTrue(all(c["status"] == "cancelled" for c in self.monitor.state()["cameras"]))
        recovered = ShuttleMonitor(server).state()
        self.assertEqual(recovered["id"], started["id"])
        self.assertEqual(recovered["status"], "stopped")

    def test_alert_filter_confirmation_persistence_and_camera_identity(self):
        cameras = []
        for i in (1, 2):
            jid = str(i) * 32
            (self.data / "jobs" / jid).mkdir()
            server.jobs[jid] = {"id": jid, "status": "cancelled", "archive_cleared": False}
            cameras.append({"id": i, "job_id": jid})
            server.save_local_archive(jid, [
                {"id": "L001", "crop": "crop-L001.jpg", "risk": "high", "owners": [{"person_id": "P001", "probability": .8}]},
                {"id": "L002", "crop": "crop-L002.jpg", "risk": "low", "owners": []},
                {"id": "L003", "crop": "crop-L003.jpg", "risk": "medium", "owners": []}])
        self.monitor.session = {"id": "test", "trip_id": "T-04", "cameras": cameras}
        state = self.monitor.state()
        self.assertEqual(len(state["alerts"]), 2)
        self.assertNotEqual(state["alerts"][0]["key"], state["alerts"][1]["key"])
        self.assertIn(cameras[0]["job_id"], state["alerts"][0]["owners"][0]["photo"])
        jid = cameras[0]["job_id"]
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={"confirmed": True}).status_code, 200)
        server.save_local_archive(jid, [{"id": "L001", "crop": "crop-L001.jpg", "risk": "low", "owners": []}])
        self.assertEqual(self.monitor.state()["alerts"][0]["warning_level"], "confirmed")
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L001/confirm", json={"confirmed": False}).status_code, 200)
        self.assertTrue(all(a["warning_level"] == "suspected" for a in self.monitor.state()["alerts"]))


if __name__ == "__main__":
    unittest.main()
