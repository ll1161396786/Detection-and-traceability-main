"""Run 2,000 real carriage frames while repeatedly requesting preview/archive photos."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as server
from engine import ROOT, cv2


with tempfile.TemporaryDirectory(prefix="yolo-soak-") as tmp:
    root = Path(tmp)
    source = root / "long.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 25, (960, 540))
    if not writer.isOpened():
        raise RuntimeError("Could not create soak fixture")
    for _ in range(10):
        cap = cv2.VideoCapture(str(ROOT / "videos" / "sample-carriage.mp4"))
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(cv2.resize(frame, (960, 540)))
        cap.release()
    writer.release()
    data = root / "data"
    (data / "jobs").mkdir(parents=True)
    (data / "uploads").mkdir()
    with patch.object(server, "DATA", data), patch.object(server, "VIDEOS", root), patch.object(server, "jobs", {}):
        client = server.app.test_client()
        response = client.post("/api/jobs", json={"library_name": "long.avi", "scope": "luggage", "stride": 1})
        assert response.status_code == 202, response.json
        jid = response.json["id"]
        deadline = time.monotonic() + 240
        versions = set()
        requests = 0
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{jid}").json
            if job["preview_version"]:
                preview = client.get(f"/api/jobs/{jid}/preview")
                image = cv2.imdecode(np.frombuffer(preview.data, np.uint8), cv2.IMREAD_COLOR)
                assert image is not None and image.mean() > 1
                preview.close()
                versions.add(job["preview_version"])
                archive = client.get(f"/api/jobs/{jid}/archive").json
                for item in archive["records"][:3]:
                    photo = client.get(item["package_photo"])
                    assert photo.status_code == 200, item["id"]
                    decoded = cv2.imdecode(np.frombuffer(photo.data, np.uint8), cv2.IMREAD_COLOR)
                    assert decoded is not None and decoded.mean() > 1
                    photo.close()
                requests += 1
            if job["status"] in server.TERMINAL:
                break
            time.sleep(.25)
        assert job["status"] == "completed", job["message"]
        archive = client.get(f"/api/jobs/{jid}/archive").json
        for item in archive["records"]:
            for url in [item["package_photo"]] + [owner["photo"] for owner in item["owners"]]:
                photo = client.get(url)
                assert photo.status_code == 200, url
                decoded = cv2.imdecode(np.frombuffer(photo.data, np.uint8), cv2.IMREAD_COLOR)
                assert decoded is not None and decoded.mean() > 1, url
                photo.close()
        print(json.dumps({"frames": job["processed"], "elapsed": job["elapsed"],
                          "preview_versions": len(versions), "poll_rounds": requests,
                          "package_records": archive["record_count"], "all_photos_decoded": True}))
