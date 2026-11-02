"""Real browser-compatible encoding and immutable event indexing, no private media."""
import json
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import app as server
from engine import cv2
from event_replay import replay_window


class EventReplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="event-replay-")
        self.root = Path(self.temp.name)
        self.data, self.videos = self.root / "data", self.root / "videos"
        self.jid = "a" * 32
        self.folder = self.data / "jobs" / self.jid
        self.folder.mkdir(parents=True)
        (self.videos / "02").mkdir(parents=True)
        self.source = self.videos / "02" / "原文件名.mp4"
        writer = cv2.VideoWriter(str(self.source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
        self.assertTrue(writer.isOpened())
        for i in range(60):
            writer.write(np.full((90, 160, 3), i * 4, dtype=np.uint8))
        writer.release()
        meta = {**server.video_info(self.source), "video_path": "02/原文件名.mp4", "mtime_ns": self.source.stat().st_mtime_ns}
        self.patches = [patch.object(server, "DATA", self.data), patch.object(server, "VIDEOS", self.videos),
                        patch.object(server, "jobs", {self.jid: {"id": self.jid, "source": meta, "status": "cancelled"}})]
        for p in self.patches:
            p.start()
        self.client = server.app.test_client()
        self.candidate = {"id": "L001", "crop": "crop-L001.jpg", "owners": [], "alarm_frame": 31,
                          "alarm_time": 9., "alarm_revision": 1, "warning_level": "confirmed"}
        server.save_local_archive(self.jid, [self.candidate])
        self.endpoint = f"/api/jobs/{self.jid}/archive/L001/replay"

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_window_middle_start_end_and_invalid(self):
        self.assertEqual(replay_window(31, 10, 6), (.5, 5.5, 3.))
        self.assertEqual(replay_window(1, 10, 6), (0., 5., 0.))
        self.assertEqual(replay_window(1, 10, 2), (0., 2., 0.))
        start, end, event = replay_window(60, 10, 6)
        self.assertAlmostEqual(start, 1.)
        self.assertEqual(end, 6)
        self.assertAlmostEqual(event, 5.9)
        with self.assertRaises(ValueError):
            replay_window(70, 10, 6)

    def test_missing_mkv_style_duration_is_repaired_for_existing_alarm(self):
        server.jobs[self.jid]['source'].update(frames=0,duration=0.)
        result=self.client.post(self.endpoint)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['duration'],5.)
        self.assertEqual(server.jobs[self.jid]['source']['frames'],60)
        self.assertEqual(server.jobs[self.jid]['source']['duration'],6.)
        self.assertEqual(result.json['event_time'],3.)

    def test_live_matroska_missing_frame_count_can_be_detected_and_replayed(self):
        import imageio_ffmpeg
        mkv=self.source.with_suffix('.mkv')
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-i',str(self.source),
                        '-map','0:v:0','-c:v','copy','-live','1',str(mkv)],check=True,capture_output=True)
        info=server.video_info(mkv)
        self.assertEqual(info['frames'],60)
        self.assertEqual(info['duration'],6.)
        server.jobs[self.jid]['source']={**info,'video_path':'02/'+mkv.name,'mtime_ns':mkv.stat().st_mtime_ns}
        result=self.client.post(self.endpoint)
        self.assertEqual(result.status_code,200,result.json)
        self.assertAlmostEqual(server.video_info(self.folder/'replays'/'L001-1-5s.mp4')['duration'],5.,delta=.12)

    def test_real_clip_range_cache_and_clear(self):
        (self.folder/'replays').mkdir()
        (self.folder/'replays'/'L001-1.mp4').write_bytes(b'old-short-cache')
        response = self.client.post(self.endpoint)
        self.assertEqual(response.status_code, 200, response.json)
        info = response.json
        self.assertEqual((info["start"], info["end"], info["event_offset"]), (.5, 5.5, 2.5))
        output = self.folder / "replays" / "L001-1-5s.mp4"
        meta = server.video_info(output)
        self.assertAlmostEqual(meta["duration"], 5., delta=.12)
        cap = cv2.VideoCapture(str(output))
        ok, frame = cap.read()
        cap.release()
        self.assertTrue(ok)
        self.assertAlmostEqual(float(frame.mean()), 20., delta=8)
        media = self.client.get(info["url"], headers={"Range": "bytes=0-99"})
        self.assertEqual(media.status_code, 206)
        self.assertEqual(media.content_type, "video/mp4")
        self.assertEqual(len(media.data), 100)
        media.close()
        with patch("event_replay.subprocess.run", side_effect=AssertionError("must use cached clip")):
            self.assertEqual(self.client.post(self.endpoint).status_code, 200)
        self.assertEqual(self.client.post(f"/api/jobs/{self.jid}/archive/clear").status_code, 200)
        self.assertFalse(output.exists())
        self.assertEqual(self.client.get(info["url"]).status_code, 400)

    def test_loop_event_frame_does_not_drift_and_revision_changes(self):
        # alarm_time=9 is the second loop; the exact source frame still means 3 seconds.
        server.save_local_archive(self.jid, [{**self.candidate, "last_seen": 12.5}])
        record = json.loads((self.folder / "archive.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(record["replay"]["time"], 3.)
        server.save_local_archive(self.jid, [{**self.candidate, "alarm_frame": 10, "alarm_revision": 2}])
        record = json.loads((self.folder / "archive.json").read_text(encoding="utf-8"))[0]
        self.assertEqual(record["replay"], {"frame": 10, "revision": 2, "time": .9})

    def test_replaced_missing_and_legacy_sources_fail_without_wrong_video(self):
        self.source.touch()
        result = self.client.post(self.endpoint)
        self.assertEqual(result.status_code, 400)
        self.assertIn("替换", result.json["error"])
        self.source.unlink()
        self.assertIn("移走", self.client.post(self.endpoint).json["error"])
        (self.folder / "archive.json").write_text('[{"id":"L001"}]', encoding="utf-8")
        self.assertIn("旧警报", self.client.post(self.endpoint).json["error"])

    def test_boundary_clips_decode_without_wrapping(self):
        for frame, expected in [(1, 5.), (60, 5.)]:
            server.save_local_archive(self.jid, [{**self.candidate, "alarm_frame": frame, "alarm_revision": 100+frame}])
            result = self.client.post(self.endpoint)
            self.assertEqual(result.status_code, 200, result.json)
            output = self.folder / "replays" / f"L001-{100+frame}-5s.mp4"
            self.assertAlmostEqual(server.video_info(output)["duration"], expected, delta=.12)

    def test_cache_clear_during_encoding_cannot_republish_deleted_evidence(self):
        real_run = subprocess.run
        def encode_then_clear(*args, **kwargs):
            result = real_run(*args, **kwargs)
            with server.app.test_client() as other:
                self.assertEqual(other.post(f"/api/jobs/{self.jid}/archive/clear").status_code, 200)
            return result
        with patch("event_replay.subprocess.run", side_effect=encode_then_clear):
            result = self.client.post(self.endpoint)
        self.assertEqual(result.status_code, 400)
        self.assertFalse((self.folder / "replays").exists())
        self.assertEqual(list(self.folder.glob("replay-pending-*.mp4")), [])

    def test_alert_thumbnail_can_use_its_immutable_event_frame(self):
        (self.folder / "crops").mkdir()
        server.write_jpeg(self.folder / "crops/crop-L001-event-1.jpg", np.full((30,30,3),100,dtype=np.uint8))
        server.save_local_archive(self.jid, [{**self.candidate, "event_crop":"crop-L001-event-1.jpg"}])
        archive = self.client.get(f"/api/jobs/{self.jid}/archive").json
        url = archive["records"][0]["package_photo"]
        self.assertTrue(url.endswith("crop-L001-event-1.jpg"))
        photo = self.client.get(url)
        self.assertEqual(photo.status_code, 200)
        photo.close()

    def test_suspected_handoff_without_formal_holder_has_alert_and_replay(self):
        from live_monitor import ShuttleMonitor
        candidate={**self.candidate,'warning_level':'suspected','event_warning_level':'suspected',
                   'first_owner_id':None,'current_owner_id':None,'transfers':[],
                   'suspected_transfer_count':1,'suspected_transfers':[{'from':'P026','to':'P027','requires_review':True}]}
        (self.folder/'archive.json').unlink()
        server.save_local_archive(self.jid,[candidate])
        monitor=ShuttleMonitor(server,'03')
        monitor.session={'trip_id':'T-03','model':'yolov10n.pt','cameras':[{'id':1,'job_id':self.jid}]}
        alerts=monitor.state()['alerts']
        self.assertEqual(len(alerts),1)
        self.assertEqual(alerts[0]['warning_level'],'suspected')
        self.assertIsNone(alerts[0]['current_owner_id'])
        self.assertEqual(alerts[0]['suspected_transfer_count'],1)
        result=self.client.post(self.endpoint)
        self.assertEqual(result.status_code,200,result.json)


    def test_loop_repeated_event_keeps_original_ids_and_manual_review(self):
        base={**self.candidate,'cycle':1,'event_type':'suspected_left_behind','bbox':[100,100,160,180],
              'event_bbox':[100,100,160,180],'owners':[{'person_id':'P001','probability':.9}]}
        server.save_local_archive(self.jid,[base])
        self.client.post(f'/api/jobs/{self.jid}/archive/L001/confirm',json={'confirmed':False})
        repeated={**base,'id':'L009','cycle':2,'owners':[{'person_id':'P019','probability':.9}]}
        server.save_local_archive(self.jid,[repeated])
        records=json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['id'],'L001')
        self.assertEqual(records[0]['warning_source'],'manual')
        self.assertEqual([o['person_id'] for o in records[0]['owners']],['P001'])
        # Even if the first loop later escalates to red, its earlier yellow
        # signature must prevent a second yellow row during a new video loop.
        server.save_local_archive(self.jid,[{**base,'event_type':'abandoned','alarm_revision':2,'alarm_frame':41}])
        server.save_local_archive(self.jid,[repeated])
        records=json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['event_type'],'abandoned')
        server.save_local_archive(self.jid,[{**repeated,'id':'L010','bbox':[300,100,360,180],'event_bbox':[300,100,360,180]}])
        self.assertEqual(len(json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))),2)

    def test_placement_warning_round_trips_through_fleet_and_replay(self):
        from live_monitor import ShuttleMonitor
        item={**self.candidate,'warning_level':'suspected','event_warning_level':'suspected',
              'event_type':'suspected_left_behind','placement_requires_review':True,
              'placement_events':[{'reason_code':'placed_then_left','time':3.,'frame':31}]}
        (self.folder/'archive.json').unlink()
        server.save_local_archive(self.jid,[item])
        monitor=ShuttleMonitor(server,'03')
        monitor.session={'trip_id':'T-03','model':'yolov10n.pt','cameras':[{'id':1,'job_id':self.jid}]}
        alerts=monitor.state()['alerts']
        self.assertEqual(alerts[0]['event_type'],'suspected_left_behind')
        self.assertTrue(alerts[0]['placement_requires_review'])
        result=self.client.post(self.endpoint)
        self.assertEqual(result.status_code,200,result.json)
        self.assertAlmostEqual(result.json['duration'],5.)


if __name__ == "__main__":
    unittest.main()
