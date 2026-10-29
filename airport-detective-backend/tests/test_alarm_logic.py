"""Deterministic detections only; no private media or model inference required."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from analytics import SceneAnalyzer, draw_scene, merge_warning


def detection(class_id, xyxy):
    return {"class_id": class_id, "xyxy": xyxy, "label": "person" if class_id == 0 else "suitcase",
            "label_zh": "人" if class_id == 0 else "行李箱", "confidence": .95}


class AlarmLogicTest(unittest.TestCase):
    def setUp(self):
        self.analyzer = SceneAnalyzer(.2)
        self.frame = 0

    def tick(self, people=(), bag=(200, 220, 240, 260), timestamp=None):
        self.frame += 1
        boxes = [detection(0, box) for box in people]
        if bag is not None:
            boxes.append(detection(28, list(bag)))
        _, candidates = self.analyzer.update(boxes, self.frame, self.frame*.1 if timestamp is None else timestamp, 1000, 500)
        return candidates[0] if candidates else None

    def test_red_only_on_fifth_consecutive_abandoned_observation(self):
        self.tick(timestamp=0)
        for count in range(1, 6):
            item = self.tick(timestamp=.2 + count*.1)
            self.assertEqual(item["abandoned_frames"], count)
            self.assertEqual(item["warning_level"], "confirmed" if count == 5 else "none")
        revision = item["alarm_revision"]
        event_frame, event_time = item["alarm_frame"], item["alarm_time"]
        self.assertEqual(event_frame, self.frame)
        self.tick(bag=None)
        item = self.tick(timestamp=1.5)
        self.assertEqual(item["abandoned_frames"], 1)
        self.assertEqual(item["warning_level"], "confirmed")  # Historical event stays in archive.
        self.assertEqual(item["alarm_revision"], revision)
        self.assertEqual((item["alarm_frame"], item["alarm_time"]), (event_frame, event_time))

    def test_missing_detection_breaks_streak(self):
        self.tick(timestamp=0)
        for i in range(3):
            self.tick(timestamp=.3+i*.1)
        self.assertIsNone(self.tick(bag=None))
        item = self.tick(timestamp=1)
        self.assertEqual(item["abandoned_frames"], 1)
        self.assertEqual(item["warning_level"], "none")

    def test_movement_and_present_nearby_person_reset_streak(self):
        self.tick(timestamp=0)
        for i in range(3):
            self.tick(timestamp=.3+i*.1)
        moved = self.tick(bag=(230, 220, 270, 260), timestamp=.7)
        self.assertEqual(moved["abandoned_frames"], 0)
        for i in range(3):
            self.tick(bag=(230, 220, 270, 260), timestamp=1+i*.1)
        nearby = self.tick(people=[(210, 80, 290, 280)], bag=(230, 220, 270, 260), timestamp=1.4)
        self.assertEqual(nearby["abandoned_frames"], 0)
        self.assertEqual(nearby["warning_level"], "none")

    def test_first_second_third_holder_and_yellow_transfer_history(self):
        self.analyzer = SceneAnalyzer(30)
        for _ in range(7):
            item = self.tick(people=[(100,0,180,200), (600,0,680,200), (600,300,680,400)])
        self.assertEqual(item["first_owner_id"], "P001")
        self.assertEqual(item["warning_level"], "none")
        for step, x in enumerate([500,400,300,200,180,180,180,180]):
            item = self.tick(people=[(max(0,80-20*step),0,max(0,80-20*step)+80,200), (x,0,x+80,200), (600,300,680,400)])
        for offset in range(0,34,3):
            item = self.tick(people=[(0,0,80,200),(180+offset,0,260+offset,200),(600,300,680,400)],bag=(200+offset,220,240+offset,260))
        self.assertEqual(item["current_owner_id"], "P002")
        self.assertEqual(item["warning_level"], "suspected")
        self.assertEqual(item["transfer_count"], 1)
        self.assertLessEqual(item["alarm_frame"], item["transfers"][-1]["frame"])
        for x,y in [(500,300),(400,300),(300,240),(200,180),(180,180),(180,180),(180,180)]:
            item = self.tick(people=[(0,0,80,200), (213,0,293,200), (x,y,x+80,y+100)],bag=(233,220,273,260))
        for step in range(16):
            offset=step*3
            item=self.tick(people=[(0,0,80,200),(max(0,213-step*20),0,max(0,213-step*20)+80,200),(180+offset,180,260+offset,280)],bag=(233+offset,220,273+offset,260))
        self.assertEqual(item["first_owner_id"], "P001")
        self.assertEqual(item["current_owner_id"], "P003")
        self.assertEqual(item["owner_history"], ["P001","P002","P003"])
        self.assertEqual(item["transfer_count"], 2)
        self.assertEqual(item["transfers"][-1]["from"], "P002")
        self.assertEqual(item["owners"][0]["person_id"], "P003")
        self.assertEqual(item["warning_level"], "suspected")

    def test_two_frame_new_holder_does_not_trigger_transfer(self):
        self.analyzer = SceneAnalyzer(30)
        for _ in range(6):
            self.tick(people=[(100,0,180,200),(600,300,680,400)])
        for x,y in [(500,300),(400,300),(300,240),(200,180)]:
            self.tick(people=[(100,0,180,200),(x,y,x+80,y+100)])
        item = self.tick(people=[(100,0,180,200),(180,180,260,280)])
        # The challenger has led for only two processed frames.
        self.assertEqual(item["transfer_count"], 0)
        item = self.tick(people=[(100,0,180,200)])
        self.assertEqual(item["current_owner_id"], "P001")
        self.assertEqual(item["warning_level"], "none")

    def test_overlay_follows_explicit_warning_not_generic_high_risk(self):
        base = {"id":"L001", "bbox":[0,0,20,20], "risk":"high", "state":"疑似遗留", "owners":[]}
        for level, color in [("none",(93,231,169)),("suspected",(69,197,255)),("confirmed",(63,82,245))]:
            with patch('analytics.cv2_rectangle') as rectangle, patch('analytics.cv2_label'):
                draw_scene(SimpleNamespace(shape=(100,100,3)), [], [{**base,"warning_level":level}])
                self.assertEqual(rectangle.call_args.args[3], color)

    def test_new_yellow_transfer_does_not_revive_reviewed_old_red(self):
        old = {"automatic_warning_level":"confirmed","warning_level":"suspected","alarm_revision":1,
               "manual_warning_level":"suspected","manual_alarm_revision":1}
        new = {"automatic_warning_level":"confirmed","event_warning_level":"suspected","alarm_revision":2}
        merged = {**old, **merge_warning(old,new)}
        self.assertEqual(merged["warning_level"],"suspected")
        self.assertEqual(merge_warning(merged,new)["warning_level"],"suspected")
        self.assertEqual(merge_warning(merged,{**new,"event_warning_level":"confirmed","alarm_revision":3})["warning_level"],"confirmed")


if __name__ == '__main__':
    unittest.main()
