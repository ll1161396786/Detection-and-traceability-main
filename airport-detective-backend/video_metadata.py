"""Bounded fallback for containers whose OpenCV frame-count metadata is absent."""
from functools import lru_cache
from pathlib import Path
import re
import subprocess
import threading
import imageio_ffmpeg

_scan_lock=threading.Lock()


@lru_cache(maxsize=32)
def _count_frames(filename, size, modified):
    # Decode, rather than counting packets (one packet need not mean one frame).
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error',
        '-nostats','-i',filename,'-map','0:v:0','-an','-sn','-dn','-vsync','0','-threads','2',
        '-progress','pipe:1','-f','null','-'],capture_output=True,timeout=60,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    values=re.findall(r'^frame=(\d+)\s*$',result.stdout.decode('utf-8',errors='replace'),re.MULTILINE)
    if result.returncode or not values or int(values[-1])<=0:
        raise ValueError('无法读取视频实际帧数，请确认文件完整或转换为标准帧率MP4。')
    stat=Path(filename).stat()
    if (stat.st_size,stat.st_mtime_ns)!=(size,modified):
        raise ValueError('视频在读取信息时已被替换，请重新加载。')
    return int(values[-1])


def decoded_frame_count(path):
    path=Path(path).resolve();stat=path.stat()
    try:
        with _scan_lock:
            return _count_frames(str(path),stat.st_size,stat.st_mtime_ns)
    except subprocess.TimeoutExpired:
        raise ValueError('视频缺少时长信息且完整扫描超时，请转换为标准帧率MP4后再检测。') from None
