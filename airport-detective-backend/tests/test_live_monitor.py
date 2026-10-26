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
from live_monitor import ShuttleMonitor, video_sources


class LiveMonitorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="four-camera-tests-")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.videos = self.root / "videos"
        (self.data / "jobs").mkdir(parents=True)
        self.videos.mkdir()
        self.patches = [patch.object(server, "DATA", self.data), patch.object(server, "VIDEOS", self.videos), patch.object(server, "jobs", {}),
                        patch.object(server.monitor, "monitors", {})]
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
        # Synthetic frames only: tests do not require or publish private videos.
        import numpy as np
        folder = self.videos / "02"
        folder.mkdir()
        self.monitor = ShuttleMonitor(server, "02")
        for i in range(1, 5):
            writer = cv2.VideoWriter(str(folder / f"保留原文件名 {i}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 25, (640, 360))
            self.assertTrue(writer.isOpened())
            for _ in range(8):
                writer.write(np.full((360, 640, 3), i*35, dtype=np.uint8))
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
        recovered = ShuttleMonitor(server, "02").state()
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

    def test_arbitrary_names_natural_order_and_maximum_count(self):
        folder = self.videos / "02"
        folder.mkdir()
        for name in ["旅行 10.MP4", "旅行 2.mp4", "旅行 1.mov", "旅行 3.mkv"]:
            (folder / name).touch()
        (folder / "说明.txt").touch()
        found, sources = video_sources(server, "2")
        self.assertEqual(found, folder)
        self.assertEqual([p.name for p in sources], ["旅行 1.mov", "旅行 2.mp4", "旅行 3.mkv", "旅行 10.MP4"])
        (folder / "第五个.avi").touch()
        with self.assertRaisesRegex(ValueError, "当前找到 5 个"):
            video_sources(server, "02")
        (folder / "第五个.avi").unlink()
        (folder / "旅行 3.mkv").unlink()
        self.assertEqual(len(video_sources(server, "02")[1]), 3)

    def test_automatic_red_persists_and_manual_review_is_scoped_to_event(self):
        jid = "a" * 32
        (self.data / "jobs" / jid).mkdir()
        server.jobs[jid] = {"id":jid,"status":"cancelled","archive_cleared":False}
        item = {"id":"L001","crop":"crop-L001.jpg","owners":[],"risk":"high",
                "automatic_warning_level":"none","warning_level":"none","alarm_revision":0}
        path = self.data / "jobs" / jid / "archive.json"
        server.save_local_archive(jid,[item])
        self.assertEqual(json.loads(path.read_text())[0]["warning_level"],"none")
        red = {**item,"automatic_warning_level":"confirmed","warning_level":"confirmed","alarm_revision":1}
        server.save_local_archive(jid,[red])
        self.assertEqual(json.loads(path.read_text())[0]["warning_level"],"confirmed")
        self.assertEqual(self.client.post(f"/api/jobs/{jid}/archive/L001/confirm",json={"confirmed":False}).status_code,200)
        server.save_local_archive(jid,[red])
        self.assertEqual(json.loads(path.read_text())[0]["warning_level"],"suspected")
        server.save_local_archive(jid,[{**red,"alarm_revision":2}])
        result=json.loads(path.read_text())[0]
        self.assertEqual(result["warning_level"],"confirmed")
        self.assertEqual(result["warning_source"],"automatic")
    def test_each_vehicle_requires_its_own_folder(self):
        for i in range(4):
            (self.videos / f"arbitrary-{i}.mp4").touch()
        for number in ["01", "03", "04"]:
            self.assertEqual(video_sources(server, number)[1], [])
        (self.videos / "01").mkdir()
        for path in self.videos.glob("*.mp4"):
            path.rename(self.videos / "01" / path.name)
        self.assertEqual(video_sources(server, "01")[0], self.videos / "01")
        (self.videos / "04").mkdir()
        self.assertEqual(video_sources(server, "04")[1], [])
        with self.assertRaises(ValueError):
            video_sources(server, "../")

    def test_fleet_routes_discover_new_vehicle_without_root_fallback(self):
        folder = self.videos / "09"
        folder.mkdir()
        for i in range(4):
            (folder / f"unchanged-name-{i}.mp4").touch()
        response = self.client.get("/api/shuttles")
        states = {s["shuttle_id"]: s for s in response.get_json()["shuttles"]}
        self.assertTrue(states["09"]["ready"])
        self.assertFalse(states["02"]["ready"])
        self.assertEqual(self.client.get("/api/shuttles/9/state").get_json()["trip_id"], "T-09")
        self.assertEqual(self.client.post("/api/shuttles/02/start", json={}).status_code, 202)
        self.assertFalse(server.jobs)

    def test_zero_to_four_inputs_create_only_connected_jobs_and_recover(self):
        from unittest.mock import Mock
        worker = Mock()
        worker.is_alive.return_value = False
        meta = {"fps":25,"duration":1,"frames":25}
        with patch("live_monitor.threading.Thread",return_value=worker), patch.object(server,"video_info",return_value=meta):
            for count in range(5):
                with self.subTest(inputs=count):
                    number = str(10+count)
                    folder = self.videos / number
                    folder.mkdir()
                    for i in range(count):
                        (folder / f"video {i}.mp4").touch()
                    before = len(server.jobs)
                    response = self.client.post(f"/api/shuttles/{number}/start",json={})
                    self.assertEqual(response.status_code,202)
                    state = response.get_json()
                    self.assertEqual(len(server.jobs)-before,count)
                    self.assertEqual(state["connected_count"],count)
                    self.assertEqual([s["connected"] for s in state["camera_slots"]],[i<count for i in range(4)])
                    self.assertEqual(len(ShuttleMonitor(server,number).state()["cameras"]),count)
                    self.assertEqual(worker.start.call_count,max(0,count))
                    for slot in state["camera_slots"][count:]:
                        self.assertEqual(slot["message"],"当前未接通线路")
                        self.assertIsNone(slot["job_id"])
                    for job in server.jobs.values():
                        job["status"]="cancelled"

    def test_stopped_removed_inputs_disconnect_without_erasing_historical_jobs(self):
        from unittest.mock import Mock
        folder = self.videos / "02"
        folder.mkdir()
        for i in range(4):
            (folder / f"video{i}.mp4").touch()
        worker=Mock()
        worker.is_alive.return_value=False
        with patch("live_monitor.threading.Thread",return_value=worker), patch.object(server,"video_info",return_value={"fps":25,"duration":1,"frames":25}):
            server.monitor.get("02").start()
        for job in server.jobs.values():
            job["status"]="cancelled"
        for i in range(1,4):
            (folder / f"video{i}.mp4").unlink()
        state=self.client.get("/api/shuttles/02/state").get_json()
        self.assertEqual(state["connected_count"],1)
        self.assertEqual(len(state["cameras"]),4)
        self.assertTrue(all(s["job_id"] is None for s in state["camera_slots"][1:]))

    def test_real_partial_camera_preview_and_stop(self):
        import numpy as np
        folder=self.videos/"03"
        folder.mkdir()
        for i in range(2):
            writer=cv2.VideoWriter(str(folder/f"任意文件名{i}.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),25,(640,360))
            self.assertTrue(writer.isOpened())
            for _ in range(8):
                writer.write(np.full((360,640,3),50+i*30,dtype=np.uint8))
            writer.release()
        self.monitor=ShuttleMonitor(server,"03")
        started=self.monitor.start()
        self.assertEqual(len(started["cameras"]),2)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            state=self.monitor.state()
            self.assertFalse(any(c["status"]=="failed" for c in state["cameras"]),state)
            if all(c["preview_version"]>0 for c in state["cameras"]):
                break
            time.sleep(.1)
        self.assertTrue(all(c["preview_version"]>0 for c in state["cameras"]),state)
        for camera in state["cameras"]:
            self.assertEqual(self.client.get(camera["preview"]).status_code,200)
        self.monitor.stop()
        self.monitor.worker.join(10)

    def test_vehicle_session_and_saved_camera_paths_are_isolated(self):
        from unittest.mock import Mock
        for number in ["02", "03"]:
            folder = self.videos / number
            folder.mkdir()
            for i in range(4):
                (folder / f"original {i}.mp4").touch()
        worker = Mock()
        worker.is_alive.return_value = False
        meta = {"fps": 25, "duration": 1, "frames": 25}
        with patch("live_monitor.threading.Thread", return_value=worker), patch.object(server, "video_info", return_value=meta):
            first = server.monitor.get("02").start()
            self.assertTrue(all(c["source_path"].startswith("02/") for c in first["cameras"]))
            with self.assertRaisesRegex(ValueError, "其他车辆"):
                server.monitor.get("03").start()
            for job in server.jobs.values():
                job["status"] = "cancelled"
            second = server.monitor.get("03").start()
        self.assertNotEqual(first["id"], second["id"])
        recovered = ShuttleMonitor(server, "02").state()
        self.assertEqual(recovered["id"], first["id"])
        self.assertEqual(recovered["trip_id"], "T-02")
        self.assertEqual(server.jobs[second["cameras"][0]["job_id"]]["train"]["number"], "接驳车 03")
        for session in [first, second]:
            jid = session["cameras"][0]["job_id"]
            server.save_local_archive(jid, [{"id": "L001", "risk": "high", "crop": "crop-L001.jpg", "owners": []}])
        alerts02 = self.client.get("/api/shuttles/02/state").get_json()["alerts"]
        alerts03 = self.client.get("/api/shuttles/03/state").get_json()["alerts"]
        self.assertEqual(len(alerts02), 1)
        self.assertEqual(len(alerts03), 1)
        self.assertNotEqual(alerts02[0]["job_id"], alerts03[0]["job_id"])


if __name__ == "__main__":
    unittest.main()
