"""Lightweight scene tracking and heuristic luggage-owner association.

YOLOv10 supplies detections. This module adds deterministic demo-level temporal
analysis; its probabilities are association scores, not trained probabilities.
"""
import math
from collections import defaultdict, deque


LUGGAGE_CLASSES = {24, 26, 28}  # backpack, handbag, suitcase in COCO
OWNER_STABLE_FRAMES = 3
ABANDONED_RED_FRAMES = 5
WARNING_RANK = {"none": 0, "suspected": 1, "confirmed": 2}


def merge_warning(previous, candidate):
    """Retain alert events, accepting automatic red and revision-scoped manual review."""
    incoming = candidate.get("event_warning_level", candidate.get("automatic_warning_level", candidate.get("warning_level")))
    if incoming is None:  # Compatibility with old archives, not the new frame rule.
        incoming = "suspected" if candidate.get("risk") == "high" else "none"
    old = previous.get("automatic_warning_level", previous.get("warning_level", "none"))
    automatic = max([old, incoming], key=lambda level: WARNING_RANK.get(level, 0))
    revision = candidate.get("alarm_revision", previous.get("alarm_revision", 0))
    manual = previous.get("manual_warning_level")
    if manual and previous.get("manual_alarm_revision", 0) == previous.get("alarm_revision", 0) and revision != previous.get("alarm_revision", 0):
        # A reviewed old red must not revive on a later yellow-only handoff.
        old = manual
        automatic = max([old, incoming], key=lambda level: WARNING_RANK.get(level, 0))
    if manual and previous.get("manual_alarm_revision", 0) == revision:
        level, source = manual, "manual"
    else:
        level, source = automatic, "automatic"
    return {"automatic_warning_level": automatic, "warning_level": level,
            "warning_source": source, "alarm_revision": revision}


def center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def box_iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    overlap = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return overlap / max(1, area_a + area_b - overlap)


class SceneAnalyzer:
    """Greedy class-aware tracking suited to a fixed-camera demo."""

    def __init__(self, linger_seconds=3.0):
        self.linger_seconds = float(linger_seconds)
        self.tracks = {}
        self.next_ids = defaultdict(int)
        self.luggage_history = {}

    def _new_id(self, class_id):
        prefix = "P" if class_id == 0 else "L" if class_id in LUGGAGE_CLASSES else "D"
        self.next_ids[prefix] += 1
        return f"{prefix}{self.next_ids[prefix]:03d}"

    def _new_track(self, box, frame_index, timestamp):
        track_id = self._new_id(box["class_id"])
        c = center(box["xyxy"])
        self.tracks[track_id] = {
            "id": track_id, "class_id": box["class_id"], "label": box["label"],
            "label_zh": box["label_zh"], "bbox": box["xyxy"], "center": c,
            "first_time": timestamp, "last_time": timestamp, "last_frame": frame_index,
            "hits": 1, "stationary_since": timestamp, "path": deque([c], maxlen=20),
            "owner_evidence": defaultdict(lambda: {"near": 0, "proximity": 0.0, "last_distance": 1.0}),
            "first_owner_id": None, "current_owner_id": None, "pending_owner_id": None,
            "owner_streak": 0, "owner_history": [], "transfers": [],
            "abandoned_streak": 0, "alarm_revision": 0, "event_warning_level": "none",
        }
        return track_id

    def update(self, boxes, frame_index, timestamp, width, height):
        diagonal = math.hypot(width, height)
        active_before = {tid: t for tid, t in self.tracks.items() if frame_index - t["last_frame"] <= 12}
        unmatched_tracks = set(active_before)
        matches = {}
        # Match confident, same-class pairs first. Center distance allows motion;
        # IoU stabilizes crowded scenes when boxes overlap between frames.
        pairs = []
        for index, box in enumerate(boxes):
            bc = center(box["xyxy"])
            for tid, track in active_before.items():
                if track["class_id"] != box["class_id"]:
                    continue
                distance = math.dist(bc, track["center"]) / max(1, diagonal)
                iou = box_iou(box["xyxy"], track["bbox"])
                if distance <= 0.12 or iou >= 0.12:
                    pairs.append((distance - iou * 0.08, index, tid))
        used_boxes = set()
        for _, index, tid in sorted(pairs):
            if index not in used_boxes and tid in unmatched_tracks:
                used_boxes.add(index); unmatched_tracks.remove(tid); matches[index] = tid
        for index, box in enumerate(boxes):
            tid = matches.get(index) or self._new_track(box, frame_index, timestamp)
            track = self.tracks[tid]
            previous = track["center"]
            current = center(box["xyxy"])
            movement = math.dist(previous, current) / max(1, diagonal)
            if movement > 0.012:
                track["stationary_since"] = timestamp
            track.update(bbox=box["xyxy"], center=current, last_time=timestamp,
                         last_frame=frame_index, hits=track["hits"] + (tid in matches.values()))
            track["path"].append(current)
            box["track_id"] = tid

        current_people = [t for t in self.tracks.values() if t["class_id"] == 0 and t["last_frame"] == frame_index]
        current_luggage = [t for t in self.tracks.values() if t["class_id"] in LUGGAGE_CLASSES and t["last_frame"] == frame_index]
        for item in self.tracks.values():
            if item["class_id"] in LUGGAGE_CLASSES and item["last_frame"] != frame_index:
                item.update(abandoned_streak=0, owner_streak=0, pending_owner_id=None)
        for item in current_luggage:
            for person in current_people:
                distance = math.dist(item["center"], person["center"]) / max(1, diagonal)
                evidence = item["owner_evidence"][person["id"]]
                evidence["last_distance"] = distance
                if distance <= 0.48:
                    proximity = max(0.0, 1.0 - distance / 0.48)
                    evidence["near"] += 1
                    evidence["proximity"] += proximity

        candidates = [self._candidate(t, frame_index, timestamp, diagonal) for t in current_luggage if t["hits"] >= 2]
        candidates.sort(key=lambda c: ({"疑似遗留": 0, "持续观察": 1, "随身携带": 2}[c["state"]], -c["stationary_seconds"], c["id"]))
        return boxes, candidates

    def _candidate(self, item, frame_index, timestamp, diagonal):
        stationary = max(0.0, timestamp - item["stationary_since"])
        owners = []
        for person_id, evidence in item["owner_evidence"].items():
            person = self.tracks.get(person_id)
            if not person or not evidence["near"]:
                continue
            avg_proximity = evidence["proximity"] / evidence["near"]
            cooccurrence = min(1.0, evidence["near"] / max(1, item["hits"]))
            present = person["last_frame"] == frame_index
            current_closeness = max(0.0, 1.0 - evidence["last_distance"] / 0.48) if present else 0.0
            score = min(0.96, 0.08 + 0.43 * avg_proximity + 0.30 * cooccurrence + 0.15 * current_closeness)
            owners.append({"person_id": person_id, "probability": round(score, 3),
                           "distance": round(evidence["last_distance"], 3), "present": present,
                           "near_frames": evidence["near"], "first_seen": round(person["first_time"], 2),
                           "bbox": person["bbox"]})
        owners.sort(key=lambda owner: owner["probability"], reverse=True)
        # Current proximity drives a handoff; lifetime score alone would keep
        # the original owner ranked first long after a transfer.
        eligible = sorted((owner for owner in owners if owner["present"] and owner["distance"] <= .24
                           and owner["probability"] >= .55), key=lambda owner: (owner["distance"], -owner["probability"], owner["person_id"]))
        best = eligible[0] if eligible else None
        # Ambiguous near-equal candidates do not establish a new holder.
        proposed = best["person_id"] if best and (len(eligible) == 1 or eligible[1]["distance"] - best["distance"] >= .03) else None
        if proposed and proposed == item["pending_owner_id"]:
            item["owner_streak"] += 1
        else:
            item.update(pending_owner_id=proposed, owner_streak=1 if proposed else 0)
        if proposed and item["owner_streak"] >= OWNER_STABLE_FRAMES and proposed != item["current_owner_id"]:
            old_owner = item["current_owner_id"]
            item["current_owner_id"] = proposed
            if item["first_owner_id"] is None:
                item["first_owner_id"] = proposed
            if proposed not in item["owner_history"]:
                item["owner_history"].append(proposed)
            if old_owner:
                item["transfers"].append({"from": old_owner, "to": proposed, "frame": frame_index, "time": round(timestamp, 3)})
                item["alarm_revision"] += 1
                item["event_warning_level"] = "suspected"
        abandoned = stationary >= self.linger_seconds and not eligible
        item["abandoned_streak"] = item["abandoned_streak"] + 1 if abandoned else 0
        if item["abandoned_streak"] == ABANDONED_RED_FRAMES:
            item["alarm_revision"] += 1
            item["event_warning_level"] = "confirmed"
        if abandoned:
            state, risk = "疑似遗留", "high"
            reason = f"已静止 {stationary:.1f} 秒，无稳定近邻所属人，连续遗留 {item['abandoned_streak']}/{ABANDONED_RED_FRAMES} 帧"
        elif best:
            state, risk = "随身携带", "low"
            reason = "人与物持续近距离共同出现"
        else:
            state, risk = "持续观察", "medium"
            reason = f"静止时长尚未达到 {self.linger_seconds:g} 秒阈值" if stationary < self.linger_seconds else "所属关系证据仍不充分"
        candidate = {"id": item["id"], "class_id": item["class_id"], "label": item["label"],
                     "label_zh": item["label_zh"], "confidence": None, "bbox": item["bbox"],
                     "first_seen": round(item["first_time"], 2), "last_seen": round(item["last_time"], 2),
                     "stationary_seconds": round(stationary, 1), "state": state, "risk": risk,
                     "reason": reason, "owners": owners, "crop": f"crop-{item['id']}.jpg",
                     "first_owner_id": item["first_owner_id"], "current_owner_id": item["current_owner_id"],
                     "owner_history": list(item["owner_history"]), "transfers": list(item["transfers"]),
                     "transfer_count": len(item["transfers"]), "abandoned_frames": item["abandoned_streak"],
                     "red_frame_threshold": ABANDONED_RED_FRAMES, "alarm_revision": item["alarm_revision"],
                     "event_warning_level": item["event_warning_level"]}
        candidate["automatic_warning_level"] = item["event_warning_level"]
        candidate.update(merge_warning(self.luggage_history.get(item["id"], {}), candidate))
        if candidate["warning_level"] == "confirmed" and item["abandoned_streak"] >= ABANDONED_RED_FRAMES:
            candidate["reason"] = f"连续 {item['abandoned_streak']} 帧满足遗留条件，触发红色警告（阈值 {ABANDONED_RED_FRAMES} 帧）"
        elif candidate["warning_level"] == "confirmed":
            candidate["reason"] = "已记录连续5帧遗留红警；当前画面已变化，保留警报档案供复核"
        elif item["transfers"]:
            transfer = item["transfers"][-1]
            candidate["reason"] = f"所属关系由 {transfer['from']} 转交至 {transfer['to']}；首位关联人 {item['first_owner_id']}，累计转交 {len(item['transfers'])} 次"
        for owner in owners:
            owner["is_first_owner"] = owner["person_id"] == item["first_owner_id"]
            owner["is_current_owner"] = owner["person_id"] == item["current_owner_id"]
        owners.sort(key=lambda owner: (not owner["is_current_owner"], not owner["is_first_owner"], -owner["probability"]))
        candidate["owners"] = owners[:3]
        self.luggage_history[item["id"]] = candidate
        return candidate

    def summary(self):
        values = list(self.luggage_history.values())
        values.sort(key=lambda c: ({"疑似遗留": 0, "持续观察": 1, "随身携带": 2}[c["state"]], c["id"]))
        return values


def draw_scene(frame, boxes, candidates):
    """Overlay stable IDs and the strongest luggage-owner relationship."""
    candidate_by_id = {c["id"]: c for c in candidates}
    for box in boxes:
        tid = box.get("track_id")
        if not tid:
            continue
        x1, y1, _, _ = [int(v) for v in box["xyxy"]]
        color = (93, 231, 169) if tid.startswith("P") else (73, 173, 255)
        cv2_label(frame, tid, x1, max(16, y1 - 5), color)
    for item_id, candidate in candidate_by_id.items():
        x1, y1, x2, y2 = [int(v) for v in candidate["bbox"]]
        color = (63, 82, 245) if candidate.get("warning_level") == "confirmed" else (69, 197, 255) if candidate.get("warning_level") == "suspected" else (93, 231, 169)
        cv2_rectangle(frame, (x1, y1), (x2, y2), color, 3)
        state_code = "CONFIRMED" if candidate.get("warning_level") == "confirmed" else "TRANSFER" if candidate.get("warning_level") == "suspected" else "OWNED" if candidate["state"] == "随身携带" else "WATCH"
        cv2_label(frame, f"{item_id} {state_code}", x1, min(frame.shape[0] - 5, y2 + 18), color)
        if candidate["owners"]:
            owner = candidate["owners"][0]
            px1, py1, px2, py2 = [int(v) for v in owner["bbox"]]
            cv2_line(frame, ((x1+x2)//2, (y1+y2)//2), ((px1+px2)//2, (py1+py2)//2), color, 2)
            cv2_label(frame, f"{owner['person_id']} {owner['probability']:.0%}", px1, min(frame.shape[0]-5, py2+18), color)
    return frame


def cv2_label(frame, text, x, y, color):
    import cv2
    cv2.putText(frame, text, (max(0, x), max(14, y)), cv2.FONT_HERSHEY_SIMPLEX, .47, (10, 18, 20), 3, cv2.LINE_AA)
    cv2.putText(frame, text, (max(0, x), max(14, y)), cv2.FONT_HERSHEY_SIMPLEX, .47, color, 1, cv2.LINE_AA)


def cv2_rectangle(frame, p1, p2, color, thickness):
    import cv2
    cv2.rectangle(frame, p1, p2, color, thickness)


def cv2_line(frame, p1, p2, color, thickness):
    import cv2
    cv2.line(frame, p1, p2, color, thickness, cv2.LINE_AA)
