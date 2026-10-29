import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import app as server
from engine import cv2


class PersonPhotoTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='person-hd-')
        self.data=Path(self.temp.name)
        self.jid='c'*32
        self.folder=self.data/'jobs'/self.jid
        (self.folder/'people').mkdir(parents=True)
        self.path=self.folder/'people/person-P001.jpg'
        self.patches=[patch.object(server,'DATA',self.data),patch.object(server,'jobs',{self.jid:{'id':self.jid,'status':'cancelled'}})]
        for item in self.patches:item.start()
        self.client=server.app.test_client()

    def tearDown(self):
        for item in reversed(self.patches):item.stop()
        self.temp.cleanup()

    def sharp(self,width,height):
        pattern=((np.indices((height,width)).sum(axis=0)//8)%2*220).astype(np.uint8)
        return np.repeat(pattern[:,:,None],3,axis=2)

    def save(self,frame,coords):
        height,width=frame.shape[:2]
        server.save_person_crop(self.folder,frame,{'track_id':'P001','xyxy':coords,'confidence':.9},width,height)

    def test_larger_native_photo_replaces_first_small_capture(self):
        self.save(self.sharp(320,240),[100,40,160,180])
        first=cv2.imdecode(np.frombuffer(self.path.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        old_url=server.person_photo_url(self.jid,'P001')
        with patch.object(server,'write_jpeg',wraps=server.write_jpeg) as publish:
            self.save(self.sharp(1920,1080),[500,100,1100,950])
        large=cv2.imdecode(np.frombuffer(self.path.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(large.shape[:2],(990,750))
        self.assertGreater(large.size,first.size)
        self.assertEqual(publish.call_args.kwargs['quality'],96)
        self.assertNotEqual(old_url,server.person_photo_url(self.jid,'P001'))
        meta=json.loads(self.path.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual((meta['width'],meta['height']),(750,990))

    def test_small_blurry_capture_cannot_downgrade_best_photo(self):
        self.save(self.sharp(1280,720),[300,60,700,650])
        saved=self.path.read_bytes()
        self.save(np.full((240,320,3),100,dtype=np.uint8),[100,40,160,180])
        self.assertEqual(self.path.read_bytes(),saved)

    def test_sharper_frame_of_same_size_can_replace_blurry_first_photo(self):
        self.save(np.full((720,1280,3),100,dtype=np.uint8),[300,60,700,650])
        saved=self.path.read_bytes()
        self.save(self.sharp(1280,720),[300,60,700,650])
        self.assertNotEqual(self.path.read_bytes(),saved)

    def test_versioned_photo_is_full_resolution_and_clear_removes_metadata(self):
        self.save(self.sharp(1280,720),[300,60,700,650])
        url=server.person_photo_url(self.jid,'P001')
        self.assertIn('?v=',url)
        result=self.client.get(url)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.data,self.path.read_bytes())
        result.close()
        self.assertEqual(self.client.post(f'/api/jobs/{self.jid}/archive/clear').status_code,200)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_suffix('.json').exists())
        self.assertEqual(self.client.get(url).status_code,404)


if __name__=='__main__':unittest.main()
