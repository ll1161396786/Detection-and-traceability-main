import unittest
from unittest.mock import patch
import numpy as np
from person_boxes import deduplicate_people
from engine import Detector
from analytics import draw_scene


def person(coords,confidence=.9):
    return {'class_id':0,'xyxy':list(coords),'confidence':confidence,'label':'person','label_zh':'人','track_id':'P001'}


class PersonBoxesTest(unittest.TestCase):
    def test_same_box_keeps_only_highest_confidence(self):
        self.assertEqual(deduplicate_people([person((100,10,200,310),.5),person((101,11,201,311),.9)])[0]['confidence'],.9)
        self.assertEqual(len(deduplicate_people([person((100,10,200,310)),person((101,11,201,311),.5)])),1)

    def test_narrow_body_duplicate_prefers_complete_box_when_scores_close(self):
        boxes=deduplicate_people([person((125,10,175,310),.92),person((100,10,200,310),.88)])
        self.assertEqual(len(boxes),1);self.assertEqual(boxes[0]['xyxy'],[100,10,200,310])

    def test_crossing_people_with_distinct_head_positions_are_retained(self):
        boxes=[person((100,10,200,310)),person((118,35,218,335),.85)]
        self.assertEqual(len(deduplicate_people(boxes)),2)

    def test_contained_distant_person_is_not_removed(self):
        self.assertEqual(len(deduplicate_people([person((100,10,240,410)),person((130,60,200,270),.85)])),2)

    def test_package_inside_person_is_not_removed(self):
        bag={**person((130,100,170,200)), 'class_id':24}
        self.assertEqual(len(deduplicate_people([person((100,10,200,310)),bag])),2)

    def test_detector_returns_one_person_for_duplicate_predictions(self):
        detector=Detector()
        with patch.object(detector,'_infer_boxes',return_value=[person((100,10,200,310)),person((125,10,175,310),.85)]):
            _,boxes=detector.predict(np.zeros((360,640,3),np.uint8),{'confidence':.25,'scope':'luggage'},'cpu')
        self.assertEqual(len(boxes),1)

    def test_final_scene_draws_one_person_outline_and_no_id(self):
        with patch('analytics.cv2_rectangle') as rectangle,patch('analytics.cv2_label') as label:
            draw_scene(np.zeros((360,640,3),np.uint8),[person((100,10,200,310))],[])
        rectangle.assert_called_once()
        self.assertEqual(label.call_args.args[1],'PERSON')


if __name__=='__main__':unittest.main()
