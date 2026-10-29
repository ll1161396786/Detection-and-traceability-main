"""Source pixels must reach YOLO without resizing, including non-stride dimensions."""
import unittest
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from engine import Detector, cv2


class SourceResolutionTest(unittest.TestCase):
    def test_mixed_camera_sizes_preserve_pixels_and_clip_padding_boxes(self):
        detector = Detector()
        model = Mock()
        model.model.stride = np.array([8,16,32])
        detector.model = model
        for h,w in [(1080,1920),(1440,2560),(361,641),(1920,1080)]:
            with self.subTest(shape=(h,w)):
                frame = np.random.default_rng(4).integers(0,255,(h,w,3),dtype=np.uint8)
                result = SimpleNamespace(names={28:'suitcase'}, boxes=Mock())
                result.boxes.cpu.return_value.numpy.return_value = [
                    SimpleNamespace(cls=[28],conf=[.9],xyxy=[[w-20,h-20,w+10,h+10]]),
                    SimpleNamespace(cls=[28],conf=[.9],xyxy=[[w+1,h+1,w+10,h+10]])]
                model.predict.return_value = [result]
                annotated, boxes = detector.predict(frame, {'imgsz':640,'confidence':.25,'scope':'luggage'}, 'cpu')
                args, kwargs = model.predict.call_args
                image = args[0]
                self.assertEqual(kwargs['imgsz'], [((h+31)//32)*32,((w+31)//32)*32])
                np.testing.assert_array_equal(image[:h,:w],frame)
                self.assertEqual(annotated.shape,frame.shape)
                self.assertEqual(len(boxes),1)
                self.assertEqual(boxes[0]['xyxy'],[w-20,h-20,w,h])

    def test_real_model_preprocess_keeps_the_native_padded_tensor(self):
        detector = Detector()
        device = detector.load('yolov10n.pt','auto')
        options = {'imgsz':'source','confidence':.95,'scope':'luggage'}
        frame = np.zeros((360,640,3),dtype=np.uint8)
        detector.predict(frame,options,device)
        predictor = detector.model.predictor
        original = predictor.preprocess
        shapes = []
        def preprocess(images):
            tensor = original(images)
            shapes.append(tuple(tensor.shape))
            return tensor
        predictor.preprocess = preprocess
        try:
            annotated,_ = detector.predict(np.zeros((1080,1920,3),dtype=np.uint8),options,device)
        finally:
            predictor.preprocess = original
        self.assertEqual(shapes,[(1,3,1088,1920)])
        self.assertEqual(annotated.shape,(1080,1920,3))

    def test_offline_pipeline_preserves_source_dimensions(self):
        import app as server
        with tempfile.TemporaryDirectory(prefix='native-offline-') as temp:
            root=Path(temp)
            jid='f'*32
            folder=root/'jobs'/jid
            folder.mkdir(parents=True)
            source=root/'source.mp4'
            writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),2,(1920,1080))
            self.assertTrue(writer.isOpened())
            for _ in range(2): writer.write(np.zeros((1080,1920,3),dtype=np.uint8))
            writer.release()
            job={'id':jid,'source':server.video_info(source),'cancel':False,'status':'loading',
                 'options':{'model':'yolov10n.pt','device':'auto','confidence':.95,'imgsz':'source',
                            'scope':'luggage','stride':1,'linger_seconds':3}}
            fake=Mock()
            fake.load.return_value='cpu'
            fake.predict.side_effect=lambda frame,opts,device:(frame.copy(),[])
            with patch.object(server,'DATA',root),patch.object(server,'jobs',{jid:job}),patch.object(server,'detector',fake):
                server.run_job(jid,source)
            self.assertEqual(job['status'],'completed',job.get('message'))
            self.assertTrue(all(call.args[0].shape[:2]==(1080,1920) for call in fake.predict.call_args_list))
            meta=server.video_info(folder/'result.mp4')
            self.assertEqual((meta['width'],meta['height']),(1920,1080))
            row=json.loads((folder/'frames.jsonl').read_text(encoding='utf-8').splitlines()[0])
            self.assertEqual((row['width'],row['height']),(1920,1080))


if __name__ == '__main__':
    unittest.main()
