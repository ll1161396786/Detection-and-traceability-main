import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import app as server
from engine import cv2
from person_photos import person_crop, mark_target


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

    def test_target_box_matches_crop_coordinates_and_does_not_mark_neighbour(self):
        frame=np.full((480,640,3),100,dtype=np.uint8)
        # A bystander at x=305 remains visible in the contextual margin.
        crop,target=person_crop(frame,[100,60,300,420],640,480)
        self.assertEqual(target,[25,30,224,389])
        marked=mark_target(crop,target)
        self.assertTrue(np.array_equal(marked[30,25],[40,255,90]))
        self.assertTrue(np.array_equal(marked[200,230],crop[200,230]))
        self.assertTrue(np.array_equal(frame,np.full_like(frame,100)))

    def test_saved_photo_has_target_marker_and_metadata(self):
        self.save(np.full((720,1280,3),100,dtype=np.uint8),[300,60,700,650])
        meta=json.loads(self.path.with_suffix('.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['target_bbox'],[50,49,449,638])
        self.assertEqual(meta['target_mark_version'],1)
        self.assertIn('&target=1',server.person_photo_url(self.jid,'P001'))
        image=cv2.imdecode(np.frombuffer(self.path.read_bytes(),np.uint8),cv2.IMREAD_COLOR)
        b,g,r=[int(v) for v in image[200,50]]
        self.assertGreater(g-r,70)
        self.assertGreater(g-b,70)
        # Sharpness is assessed before drawing: the rectangle cannot inflate quality.
        self.assertEqual(meta['sharpness'],0)

    def test_target_clips_to_source_edges_without_wrapping(self):
        frame=np.zeros((80,100,3),np.uint8)
        crop,target=person_crop(frame,[-8,-4,110,90],100,80)
        self.assertEqual(crop.shape[:2],(80,100))
        self.assertEqual(target,[0,0,99,79])
        marked=mark_target(crop,target)
        self.assertTrue(np.array_equal(marked[0,0],[40,255,90]))
        self.assertTrue(np.array_equal(marked[-1,-1],[40,255,90]))

    def test_invalid_person_box_does_not_save_photo(self):
        for coords in ([300,20,400,100],[50,50,20,80],[20,50,40,50]):
            self.save(np.zeros((160,200,3),np.uint8),coords)
        self.assertFalse(self.path.exists())

    def test_legacy_photo_is_not_claimed_as_marked_until_new_observation(self):
        server.write_jpeg(self.path,self.sharp(640,480))
        self.path.with_suffix('.json').write_text(json.dumps({'pixels':9999999,'score':9999999}),encoding='utf-8')
        old=self.path.read_bytes()
        self.assertNotIn('target=1',server.person_photo_url(self.jid,'P001'))
        self.assertEqual(self.client.get(server.person_photo_url(self.jid,'P001')).data,old)
        self.save(np.full((240,320,3),100,np.uint8),[100,40,160,180])
        self.assertIn('&target=1',server.person_photo_url(self.jid,'P001'))
        self.assertNotEqual(self.path.read_bytes(),old)


if __name__=='__main__':unittest.main()
