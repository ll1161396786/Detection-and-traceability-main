import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import numpy as np
from engine import Detector


class PackageDetectionTest(unittest.TestCase):
    def test_same_bag_multiple_coco_labels_are_fused(self):
        detector=Detector();detector.model=Mock()
        detector.model.model.stride=32
        result=SimpleNamespace(names={24:'backpack',26:'handbag',28:'suitcase'},boxes=Mock())
        result.boxes.cpu.return_value.numpy.return_value=[SimpleNamespace(cls=[c],conf=[p],xyxy=[[100,100,200,250]]) for c,p in [(24,.3),(26,.2),(28,.15)]]
        detector.model.predict.return_value=[result]
        _,boxes=detector.predict(np.zeros((360,640,3),dtype=np.uint8),{'confidence':.25,'scope':'luggage'},'cpu')
        self.assertEqual(len(boxes),1)
        self.assertEqual(boxes[0]['class_id'],24)
        self.assertEqual(detector.model.predict.call_args.kwargs['conf'],.12)

    def test_supplementary_person_crop_maps_back_to_source_pixels(self):
        detector=Detector()
        person={'class_id':0,'label':'person','label_zh':'人','confidence':.9,'xyxy':[300,0,600,650]}
        bag={'class_id':24,'label':'backpack','label_zh':'包','confidence':.4,'xyxy':[100,100,180,240]}
        with patch.object(detector,'_infer_boxes',side_effect=[[person],[bag]]) as infer:
            _,boxes=detector.predict(np.zeros((720,1280,3),dtype=np.uint8),{'confidence':.25,'scope':'luggage'},'cpu')
        self.assertEqual(infer.call_count,2)
        self.assertEqual(boxes[1]['xyxy'],[325,217,405,357])
        self.assertEqual(boxes[1]['detection_source'],'person_context')
        self.assertEqual(infer.call_args.args[0].shape[:2],(565,450))

if __name__=='__main__':unittest.main()
