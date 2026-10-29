"""On-demand, bounded H.264 replay clips from the original local camera input."""
import math
import subprocess
import threading
import uuid

import imageio_ffmpeg
from flask import jsonify, send_file


def replay_window(frame, fps, duration):
    event = (int(frame) - 1) / float(fps)
    if not all(math.isfinite(v) for v in (event, duration)) or not 0 <= event < duration:
        raise ValueError("报警帧超出源视频范围，请重新检测。")
    return max(0., event - 2), min(duration, event + 2), event


def register_replay(server):
    # FFmpeg runs outside the inference/archive lock and never uses the GPU.
    encoder = threading.BoundedSemaphore(1)

    def record_for(jid, candidate_id):
        if (jid not in server.jobs or server.jobs[jid].get("archive_cleared")
                or not server.re.fullmatch(r"L\d{3,}", candidate_id)):
            raise ValueError("遗留物档案不存在或已清理。")
        archive = server.DATA / "jobs" / jid / "archive.json"
        records = server.json.loads(archive.read_text(encoding="utf-8")) if archive.exists() else []
        item = next((row for row in records if row["id"] == candidate_id), None)
        if not item or not item.get("replay"):
            raise ValueError("此旧警报未记录回放帧，请重新启动检测后查看新警报。")
        return item["replay"], dict(server.jobs[jid]["source"])

    @server.app.post("/api/jobs/<jid>/archive/<candidate_id>/replay")
    def prepare_replay(jid, candidate_id):
        with server.lock:
            event, source = record_for(jid, candidate_id)
            revision = int(event["revision"])
            start, end, at = replay_window(event["frame"], source["fps"], source["duration"])
            folder = server.DATA / "jobs" / jid / "replays"
            output = folder / f"{candidate_id}-{revision}.mp4"
            info = {"url": f"/api/jobs/{jid}/replays/{candidate_id}/{revision}.mp4",
                    "start": start, "end": end, "duration": end-start,
                    "event_time": at, "event_offset": at-start, "revision": revision}
            if output.is_file():
                return jsonify(info)
            relative = source.get("video_path")
            if not relative:
                raise ValueError("此旧任务缺少源视频定位信息，请重新检测。")
            path = server.VIDEOS / relative
            if path.is_symlink() or not path.resolve().is_relative_to(server.VIDEOS.resolve()) or not path.is_file():
                raise ValueError("源视频已移走，无法生成事件回放。")
            stat = path.stat()
            if stat.st_size != source["size"] or stat.st_mtime_ns != source.get("mtime_ns"):
                raise ValueError("源视频已被替换，请重新检测后查看对应的新警报。")
        if not encoder.acquire(blocking=False):
            return jsonify(error="另一段回放正在准备，请稍后重试。"), 409
        temporary = None
        try:
            # Keep the in-progress file outside replays so cache cleanup can remove
            # finished clips while encoding is in flight, even on Windows.
            temporary = folder.parent / f"replay-pending-{uuid.uuid4().hex}.mp4"
            command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                       "-ss", str(start), "-i", str(path), "-t", str(end-start), "-map", "0:v:0", "-an",
                       "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart", str(temporary)]
            result = subprocess.run(command, capture_output=True, timeout=60,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode or not temporary.is_file() or temporary.stat().st_size < 100:
                server.logging.error("Replay encode failed: %s", result.stderr.decode("utf-8", errors="replace")[-2000:])
                raise ValueError("回放生成失败，请确认源视频能正常解码。")
            latest = path.stat()
            if (latest.st_size, latest.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise ValueError("源视频在生成回放时被替换，请重新检测。")
            with server.lock:
                current, _ = record_for(jid, candidate_id)
                if current != event:
                    raise ValueError("该遗留物有新的报警事件，请再次点击查看。")
                folder.mkdir(exist_ok=True)
                temporary.replace(output)
            return jsonify(info)
        except subprocess.TimeoutExpired:
            raise ValueError("回放生成超时，请稍后重试。")
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            encoder.release()

    @server.app.get("/api/jobs/<jid>/replays/<candidate_id>/<int:revision>.mp4")
    def replay_media(jid, candidate_id, revision):
        with server.lock:
            record_for(jid, candidate_id)
            path = server.DATA / "jobs" / jid / "replays" / f"{candidate_id}-{revision}.mp4"
            if not path.is_file():
                return jsonify(error="回放尚未生成或已清理，请重新点击遗留物。"), 404
            return send_file(path, mimetype="video/mp4", conditional=True)
