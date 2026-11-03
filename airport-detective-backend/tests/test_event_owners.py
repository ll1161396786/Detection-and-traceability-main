import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import app as s
from engine import cv2
from event_owners import snapshot


class EventOwnersTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.jid='e'*32;self.folder=self.root/'jobs'/self.jid
        (self.folder/'people').mkdir(parents=True)
        self.source=self.root/'source.mp4'
        writer=cv2.VideoWriter(str(self.source),cv2.VideoWriter_fourcc(*'mp4v'),5,(160,100))
        self.frames=[]
        for i in range(10):
            frame=np.zeros((100,160,3),np.uint8)
            frame[10:90,10:50]=(0,0,220) if i==0 else (0,220,0)
            frame[10:90,100:140]=(220,0,0)
            writer.write(frame);self.frames.append(frame)
        writer.release()
        self.patches=[patch.object(s,'DATA',self.root),patch.object(s,'jobs',{
            self.jid:{'id':self.jid,'status':'cancelled','source':{'fps':5,'mtime_ns':self.source.stat().st_mtime_ns}}})]
        for p in self.patches:p.start()
        self.event={'id':'L001','crop':'crop-L001.jpg','alarm_frame':5,'alarm_revision':1,'event_type':'suspected_handoff',
                    'event_warning_level':'suspected','owners':[],
                    'suspected_transfers':[{'from':'P001','to':'P002','frame':5,'from_bbox':[10,10,50,90],
                        'from_frame':1,'from_score':.9,'to_bbox':[100,10,140,90],'to_frame':5,'to_score':.88}]}
        self.event['event_owners']=snapshot(self.event)

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_handoff_uses_only_event_source_and_recipient_not_nearby_people(self):
        self.event['owners']=[{'person_id':'P099','probability':.99}]
        result=snapshot(self.event)
        self.assertEqual([o['person_id'] for o in result],['P001','P002'])
        self.assertEqual([o['event_role'] for o in result],['handoff_source','handoff_recipient'])
        self.assertEqual([o['evidence_frame'] for o in result],[1,5])

    def test_placement_uses_actor_instead_of_current_nearest_candidate(self):
        result=snapshot({'event_type':'suspected_left_behind','owners':[{'person_id':'P099'}],
                         'placement_events':[{'person_id':'P007','person_bbox':[10,10,50,90],'person_frame':3}]})
        self.assertEqual(len(result),1);self.assertEqual(result[0]['person_id'],'P007')
        self.assertEqual(result[0]['event_role'],'placement_actor')

    def test_missing_actor_evidence_does_not_guess_an_owner(self):
        result=snapshot({'event_type':'suspected_left_behind','owners':[{'person_id':'P099','probability':.99}],
                         'placement_events':[{'person_id':None}]})
        self.assertEqual(result,[])

    def test_duplicate_identity_or_same_frame_duplicate_box_is_not_two_people(self):
        for same_id in (True,False):
            event=json.loads(json.dumps(self.event));e=event['suspected_transfers'][0]
            e.update(to='P001' if same_id else 'P002',from_frame=5,to_bbox=[10,10,50,90])
            result=snapshot(event)
            self.assertEqual(len(result),1);self.assertEqual(result[0]['event_role'],'association_uncertain')

    def test_event_photos_use_exact_source_frame_and_are_immutable(self):
        s.save_event_owner_photos(self.jid,[self.event],self.frames[4],5,self.source)
        first=self.event['event_owners'][0]
        path=self.folder/'people'/first['event_photo'];data=path.read_bytes()
        crop=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
        self.assertGreater(int(crop[crop.shape[0]//2,crop.shape[1]//2,2]),150)
        s.save_event_owner_photos(self.jid,[self.event],self.frames[9],10,self.source)
        self.assertEqual(data,path.read_bytes())
        self.assertNotIn('person-P001.jpg',s.owner_photo_url(self.jid,first))

    def test_archive_freezes_roles_and_photos_until_new_event_revision(self):
        s.save_event_owner_photos(self.jid,[self.event],self.frames[4],5,self.source)
        s.save_local_archive(self.jid,[self.event])
        frozen=json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))[0]['event_owners']
        changed={**self.event,'event_owners':[],'owners':[{'person_id':'P099','probability':.99}]}
        s.save_local_archive(self.jid,[changed])
        record=json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(record['event_owners'],frozen)
        s.save_local_archive(self.jid,[{**changed,'alarm_revision':2}])
        self.assertEqual(json.loads((self.folder/'archive.json').read_text(encoding='utf-8'))[0]['event_owners'],[])

    def test_missing_photo_never_falls_back_to_later_best_portrait(self):
        self.assertIsNone(s.owner_photo_url(self.jid,self.event['event_owners'][0]))

    def test_event_photo_endpoint_and_archive_clear(self):
        s.save_event_owner_photos(self.jid,[self.event],self.frames[4],5,self.source)
        s.save_local_archive(self.jid,[self.event]);client=s.app.test_client()
        url=s.owner_photo_url(self.jid,self.event['event_owners'][0])
        response=client.get(url);self.assertEqual(response.status_code,200);response.close()
        records=client.get(f'/api/jobs/{self.jid}/archive').get_json()['records']
        self.assertTrue(records[0]['association_snapshot_available'])
        self.assertEqual([o['event_role'] for o in records[0]['owners']],['handoff_source','handoff_recipient'])
        self.assertEqual(records[0]['owners'][0]['photo'],url)
        self.assertEqual(client.post(f'/api/jobs/{self.jid}/archive/clear').status_code,200)
        self.assertEqual(client.get(url).status_code,404)


if __name__=='__main__':unittest.main()
