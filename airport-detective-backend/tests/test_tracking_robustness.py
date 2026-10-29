"""Known synthetic truth for occlusions, class flicker, passersby and handoffs."""
import unittest
import numpy as np
from analytics import SceneAnalyzer


def box(cls,xyxy,confidence=.9):
    return {'class_id':cls,'xyxy':list(xyxy),'label':'person' if cls==0 else 'backpack',
            'label_zh':'人' if cls==0 else '包','confidence':confidence}


class RobustTrackingTest(unittest.TestCase):
    def test_class_flip_and_stride_gap_keep_one_package(self):
        analyzer=SceneAnalyzer(30)
        ids=[]
        for step,cls in enumerate([24,26,28,24]):
            tracked,_=analyzer.update([box(cls,(100,100,160,180))],1+step*10,step*.4,1000,500)
            ids.append(tracked[0]['track_id'])
            analyzer.update([],2+step*10,step*.4+.1,1000,500)
        self.assertEqual(len(set(ids)),1)

    def test_flickering_weak_package_never_becomes_an_alarm(self):
        analyzer=SceneAnalyzer(.1)
        for i in range(20):
            _,candidates=analyzer.update([box(24,(100,100,160,180),.13)] if i%3==0 else [],i+1,i*.1,1000,500)
            self.assertEqual(candidates,[])
        self.assertEqual(analyzer.summary(),[])

    def test_bystander_nearer_stationary_package_is_not_a_handoff(self):
        analyzer=SceneAnalyzer(30)
        for i in range(25):
            people=[box(0,(100,0,200,300)),box(0,(450-i*10,0,550-i*10,300))]
            _,c=analyzer.update(people+[box(24,(180,200,220,260))],i+1,i*.1,1000,500)
        self.assertTrue(c)
        self.assertEqual(c[0]['transfer_count'],0)
        self.assertEqual(c[0]['warning_level'],'none')

    def test_appearance_preserves_people_at_crossing(self):
        analyzer=SceneAnalyzer(30)
        ids={}
        for i in range(8):
            frame=np.zeros((400,800,3),dtype=np.uint8)
            a=(100+i*30,20,180+i*30,320)
            b=(520-i*30,20,600-i*30,320)
            frame[a[1]:a[3],a[0]:a[2]]=(230,230,230)
            frame[b[1]:b[3],b[0]:b[2]]=(20,30,70)
            detected=[box(0,a),box(0,b)]
            tracked,_=analyzer.update(detected,i+1,i*.1,800,400,frame=frame)
            for index,name in enumerate(['light','dark']):
                if i==0:ids[name]=tracked[index]['track_id']
                self.assertEqual(tracked[index]['track_id'],ids[name])

    def test_short_person_occlusion_does_not_change_owner(self):
        analyzer=SceneAnalyzer(30)
        latest=None
        for i in range(25):
            people=[] if 10<=i<16 else [box(0,(100,0,200,300))]
            _,c=analyzer.update(people+[box(24,(180,200,220,260))],i+1,i*.1,1000,500)
            if c:latest=c[0]
        self.assertEqual(latest['first_owner_id'],'P001')
        self.assertEqual(latest['current_owner_id'],'P001')
        self.assertEqual(latest['transfer_count'],0)


if __name__=='__main__':unittest.main()
