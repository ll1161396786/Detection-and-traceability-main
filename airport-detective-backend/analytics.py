"""Lightweight scene tracking and heuristic luggage-owner association.

YOLOv10 supplies detections. This module adds deterministic demo-level temporal
analysis; its probabilities are association scores, not trained probabilities.
"""
import math
from collections import defaultdict, deque
from tracking import assign_tracks, contact
from handoff import HandoffEvidence


LUGGAGE_CLASSES = {24, 26, 28}  # backpack, handbag, suitcase in COCO
OWNER_STABLE_FRAMES = 3
TRANSFER_STABLE_FRAMES = 5
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
        self.observation = 0

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
            "last_observation": self.observation, "velocity": (0.,0.), "appearance": None,
            "scores": deque([box.get("confidence",1.)],maxlen=6), "pending_since": timestamp,
            "owner_last_near": -math.inf, "pending_origin": c,
            "class_scores": {box["class_id"]:box.get("confidence",1.)},
            "package_confirmed": False, "handoff_evidence": HandoffEvidence(), "suspected_transfers": [],
        }
        return track_id

    def update(self, boxes, frame_index, timestamp, width, height, frame=None):
        diagonal = math.hypot(width, height)
        self.observation += 1
        self.tracks = {tid:t for tid,t in self.tracks.items()
                       if self.observation-t["last_observation"]<=60 and timestamp-t["last_time"]<=3.}
        matches,features,ambiguous=assign_tracks(boxes,self.tracks,diagonal,self.observation,box_iou,center,frame)
        for index, box in enumerate(boxes):
            tid = matches.get(index) or self._new_track(box, frame_index, timestamp)
            track = self.tracks[tid]
            previous = track["center"]
            current = center(box["xyxy"])
            gap=max(1,self.observation-track["last_observation"])
            track["velocity"] = ((current[0]-previous[0])/gap,(current[1]-previous[1])/gap)
            track["last_observation"] = self.observation
            track["ambiguous"] = index in ambiguous
            if features[index] is not None and index not in ambiguous:
                old=track.get("appearance")
                track["appearance"]=features[index] if old is None else .85*old+.15*features[index]
            if index in matches:
                track["scores"].append(box.get("confidence",1.))
                if box["class_id"] in LUGGAGE_CLASSES and box.get("confidence",1.)>=.25:
                    votes={cls:value*.85 for cls,value in track["class_scores"].items()}
                    votes[box["class_id"]]=votes.get(box["class_id"],0)+box.get("confidence",1.)
                    winner=max(votes,key=votes.get)
                    if votes[winner]>1.25*votes.get(track["class_id"],0):
                        names={24:("backpack","背包"),26:("handbag","手提包"),28:("suitcase","行李箱")}
                        track["class_id"]=winner
                        track["label"],track["label_zh"]=names[winner]
                    track["class_scores"]=votes
            movement = math.dist(previous, current) / max(1, diagonal)
            if movement > 0.012:
                track["stationary_since"] = timestamp
            track.update(bbox=box["xyxy"], center=current, last_time=timestamp,
                         last_frame=frame_index, hits=track["hits"] + (tid in matches.values()))
            track["path"].append(current)
            supported=(max(track["scores"])>=.35 or len(track["scores"])>=3 and sum(track["scores"])/len(track["scores"])>=.2)
            if supported and track["hits"]>=2:track["package_confirmed"]=True
            box["track_id"] = tid if supported or track["package_confirmed"] or box["class_id"] not in LUGGAGE_CLASSES else ""

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
                evidence.setdefault("recent",deque(maxlen=6)).append(contact(item["bbox"],person["bbox"]))
                evidence["last_observation"] = self.observation
                if distance <= 0.48:
                    proximity = max(0.0, 1.0 - distance / 0.48)
                    evidence["near"] += 1
                    evidence["proximity"] += proximity

        candidates = [self._candidate(t, frame_index, timestamp, diagonal) for t in current_luggage if t["package_confirmed"]]
        candidates.sort(key=lambda c: ({"疑似遗留": 0, "持续观察": 1, "随身携带": 2}[c["state"]], -c["stationary_seconds"], c["id"]))
        return boxes, candidates

    def _candidate(self, item, frame_index, timestamp, diagonal):
        stationary = max(0.0, timestamp - item["stationary_since"])
        owners = []
        for person_id, evidence in item["owner_evidence"].items():
            person = self.tracks.get(person_id)
            if not person or not evidence["near"]:
                continue
            present = person["last_frame"] == frame_index
            current_closeness = contact(item["bbox"],person["bbox"]) if present else 0.
            recent=evidence.get("recent",[current_closeness])
            score = min(.96,.7*current_closeness+.3*sum(recent)/len(recent)) if present else 0.
            owners.append({"person_id": person_id, "probability": round(score, 3),
                           "distance": round(evidence["last_distance"], 3), "present": present,
                           "near_frames": evidence["near"], "first_seen": round(person["first_time"], 2),
                           "contact_score": round(current_closeness,3), "association_ambiguous": person.get("ambiguous",False),
                           "bbox": person["bbox"]})
        owners.sort(key=lambda owner: owner["probability"], reverse=True)
        # Current proximity drives a handoff; lifetime score alone would keep
        # the original owner ranked first long after a transfer.
        eligible = sorted((owner for owner in owners if owner["present"] and owner["contact_score"] >= .5
                           and owner["probability"] >= .55), key=lambda owner: (-owner["probability"],owner["person_id"]))
        best = eligible[0] if eligible else None
        # Ambiguous near-equal candidates do not establish a new holder.
        proposed = best["person_id"] if best and not best["association_ambiguous"] and (len(eligible)==1 or best["probability"]-eligible[1]["probability"]>=.10) else None
        current=next((o for o in eligible if o["person_id"]==item["current_owner_id"]),None)
        if current:
            item["owner_last_near"]=timestamp
        if current and best and best["probability"]-current["probability"]<.15:
            proposed=item["current_owner_id"]
        if proposed and proposed == item["pending_owner_id"]:
            item["owner_streak"] += 1
        else:
            item.update(pending_owner_id=proposed, owner_streak=1 if proposed else 0)
            item["pending_since"]=timestamp
            item["pending_origin"]=item["center"]
        is_transfer=item["current_owner_id"] is not None and proposed!=item["current_owner_id"]
        moved=math.dist(item["center"],item["pending_origin"])/max(1,diagonal)>=.008
        # Require release of the incumbent plus sustained acquisition and package
        # motion. Mere proximity or a stationary-bag bystander cannot cause a handoff.
        released=not current or best and best["probability"]-current["probability"]>=.18
        if is_transfer and released:
            if item.get("release_since") is None:item["release_since"]=timestamp
        else:
            item["release_since"]=None
        transfer_ready=(item.get("release_since") is not None and timestamp-item["release_since"]>=.25 and moved
                        and timestamp-item["owner_last_near"]<=2.)
        stable=item["owner_streak"] >= (TRANSFER_STABLE_FRAMES if is_transfer else OWNER_STABLE_FRAMES)
        duration=timestamp-item["pending_since"] >= (.45 if is_transfer else .16)
        if proposed and stable and duration and (not is_transfer or transfer_ready) and proposed != item["current_owner_id"]:
            old_owner = item["current_owner_id"]
            item["current_owner_id"] = proposed
            if item["first_owner_id"] is None:
                item["first_owner_id"] = proposed
            if proposed not in item["owner_history"]:
                item["owner_history"].append(proposed)
            if old_owner:
                item["transfers"].append({"from": old_owner, "to": proposed, "frame": frame_index, "time": round(timestamp, 3)})
                already_warned=any(event['from']==old_owner and event['to']==proposed and abs(timestamp-event['time'])<2
                                   for event in item['suspected_transfers'])
                if not already_warned:
                    item["alarm_revision"] += 1
                    item["event_warning_level"] = "suspected"
                    item.update(alarm_frame=frame_index, alarm_time=timestamp)
        suspected=item["handoff_evidence"].update(owners,item["center"],timestamp,frame_index,diagonal)
        if suspected and not any(t['from']==suspected['from'] and t['to']==suspected['to'] and abs(t['time']-timestamp)<2 for t in item['transfers']):
            item["suspected_transfers"].append(suspected)
            item["alarm_revision"]+=1
            item["event_warning_level"]="suspected"
            item.update(alarm_frame=frame_index,alarm_time=timestamp)
        abandoned = stationary >= self.linger_seconds and not eligible and timestamp-item["owner_last_near"]>.75 and item["scores"][-1]>=.2
        item["abandoned_streak"] = item["abandoned_streak"] + 1 if abandoned else 0
        if item["abandoned_streak"] == ABANDONED_RED_FRAMES:
            item["alarm_revision"] += 1
            item["event_warning_level"] = "confirmed"
            item.update(alarm_frame=frame_index, alarm_time=timestamp)
        stable_owner=next((owner for owner in owners if owner["person_id"]==item["current_owner_id"] and owner["present"]),None)
        pending=bool(proposed and item["current_owner_id"] and proposed!=item["current_owner_id"])
        association_status="转交确认中" if pending else "稳定关联" if stable_owner else "候选重叠待复核" if best and not proposed else "候选确认中" if proposed else "暂缺稳定关联"
        if abandoned:
            state, risk = "疑似遗留", "high"
            reason = f"已静止 {stationary:.1f} 秒，无稳定近邻所属人，连续遗留 {item['abandoned_streak']}/{ABANDONED_RED_FRAMES} 帧"
        elif stable_owner:
            state, risk = "随身携带", "low"
            reason = f"稳定关联人 {stable_owner['person_id']}" + (f"；候选 {proposed} 的接管证据仍在确认" if pending else "；候选排序变化不会直接改绑")
        elif best:
            state, risk = "持续观察", "medium"
            reason = f"{association_status}，尚未确认首位持有人，候选分数不等于已绑定"
        else:
            state, risk = "持续观察", "medium"
            reason = f"静止时长尚未达到 {self.linger_seconds:g} 秒阈值" if stationary < self.linger_seconds else "所属关系证据仍不充分"
        candidate = {"id": item["id"], "class_id": item["class_id"], "label": item["label"],
                     "label_zh": item["label_zh"], "confidence": round(sum(item["scores"])/len(item["scores"]),3), "bbox": item["bbox"],
                     "first_seen": round(item["first_time"], 2), "last_seen": round(item["last_time"], 2),
                     "stationary_seconds": round(stationary, 1), "state": state, "risk": risk,
                     "reason": reason, "owners": owners, "crop": f"crop-{item['id']}.jpg",
                     "first_owner_id": item["first_owner_id"], "current_owner_id": item["current_owner_id"],
                     "owner_history": list(item["owner_history"]), "transfers": list(item["transfers"]),
                     "transfer_count": len(item["transfers"]), "abandoned_frames": item["abandoned_streak"],
                     "red_frame_threshold": ABANDONED_RED_FRAMES, "alarm_revision": item["alarm_revision"],
                     "event_warning_level": item["event_warning_level"]}
        candidate["suspected_transfers"]=list(item["suspected_transfers"])
        candidate["suspected_transfer_count"]=len(item["suspected_transfers"])
        candidate["handoff_requires_review"]=bool(item["suspected_transfers"] and (not item["transfers"]
            or item["suspected_transfers"][-1]['time']>item["transfers"][-1]['time']))
        candidate["association_status"] = association_status
        candidate["pending_transfer"] = {"person_id": proposed, "frames":item["owner_streak"],
                                         "package_moved":moved,"release_observed":bool(released),
                                         "ready":bool(transfer_ready)} if pending else None
        if "alarm_frame" in item:
            candidate.update(alarm_frame=item["alarm_frame"], alarm_time=item["alarm_time"])
        candidate["automatic_warning_level"] = item["event_warning_level"]
        candidate.update(merge_warning(self.luggage_history.get(item["id"], {}), candidate))
        if candidate["warning_level"] == "confirmed" and item["abandoned_streak"] >= ABANDONED_RED_FRAMES:
            candidate["reason"] = f"连续 {item['abandoned_streak']} 帧满足遗留条件，触发红色警告（阈值 {ABANDONED_RED_FRAMES} 帧）"
        elif candidate["warning_level"] == "confirmed":
            candidate["reason"] = "已记录连续5帧遗留红警；当前画面已变化，保留警报档案供复核"
        elif item["transfers"] and not candidate["handoff_requires_review"]:
            transfer = item["transfers"][-1]
            candidate["reason"] = f"所属关系由 {transfer['from']} 转交至 {transfer['to']}；首位关联人 {item['first_owner_id']}，累计转交 {len(item['transfers'])} 次"
        elif item["suspected_transfers"]:
            transfer=item["suspected_transfers"][-1]
            candidate["reason"]=f"疑似转交：候选关联由 {transfer['from']} 变为 {transfer['to']}，已观察到释放、接管和包移动证据；持有人尚待复核"
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


def relationship_display(candidate):
    """The rendered binding must use the exact same holder as the alarm state."""
    owners=[owner for owner in candidate.get("owners",[]) if owner.get("present",False)]
    holder=next((owner for owner in owners if owner["person_id"]==candidate.get("current_owner_id")),None)
    if holder:
        return holder,True
    return max(owners,key=lambda owner:owner.get("probability",0),default=None),False


def draw_scene(frame, boxes, candidates):
    """Solid lines mean accepted association; grey dashes mean unbound candidates."""
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
        owner,bound=relationship_display(candidate)
        state_code = "CONFIRMED" if candidate.get("warning_level") == "confirmed" else "TRANSFER" if candidate.get("warning_level") == "suspected" else "HANDOFF_PENDING" if candidate.get("pending_transfer") else "ASSOCIATED" if bound else "UNASSIGNED"
        cv2_label(frame, f"{item_id} {state_code}", x1, min(frame.shape[0] - 5, y2 + 18), color)
        if owner:
            px1, py1, px2, py2 = [int(v) for v in owner["bbox"]]
            start,end=((x1+x2)//2,(y1+y2)//2),((px1+px2)//2,(py1+py2)//2)
            line_color=color if bound else (160,160,160)
            if bound:
                cv2_line(frame,start,end,line_color,2)
            else:
                cv2_dashed_line(frame,start,end,line_color)
            label="ASSOC" if bound else "CANDIDATE_NOT_BOUND"
            cv2_label(frame,f"{label} {owner['person_id']} score={owner.get('probability',0):.2f}",px1,min(frame.shape[0]-5,py2+18),line_color)
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


def cv2_dashed_line(frame, start, end, color):
    length=math.dist(start,end)
    if not length:return
    for offset in range(0,int(length)+1,16):
        a,b=offset/length,min(length,offset+9)/length
        p1=tuple(round(start[i]+(end[i]-start[i])*a) for i in (0,1))
        p2=tuple(round(start[i]+(end[i]-start[i])*b) for i in (0,1))
        cv2_line(frame,p1,p2,color,1)
