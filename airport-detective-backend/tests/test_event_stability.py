"""Regression cases for ID fragmentation, placement and repeated alarm episodes."""
import unittest
import numpy as np
from analytics import SceneAnalyzer
from handoff import HandoffEvidence
from placement import PlacementEvidence
from test_tracking_robustness import box


def owner(pid='P001',contact=.95,bbox=(100,0,260,400)):
    return {'person_id':pid,'present':True,'probability':contact,'contact_score':contact,
            'association_ambiguous':False,'bbox':list(bbox)}


class EventStabilityTest(unittest.TestCase):
    def test_weak_person_observation_recovers_id_but_cannot_create_one(self):
        analyzer=SceneAnalyzer()
        tracked,_=analyzer.update([box(0,(100,0,200,300),.2)],1,0,1000,600)
        self.assertEqual(tracked[0]['track_id'],'')
        self.assertFalse(analyzer.tracks)
        tracked,_=analyzer.update([box(0,(100,0,200,300),.9)],2,.1,1000,600)
        pid=tracked[0]['track_id']
        for i in range(3,15):
            tracked,_=analyzer.update([box(0,(100,0,200,300),.18)],i,i*.1,1000,600)
            self.assertEqual(tracked[0]['track_id'],pid)

    def test_person_recovers_after_four_seconds_local_occlusion(self):
        analyzer=SceneAnalyzer()
        tracked,_=analyzer.update([box(0,(100,0,200,300))],1,0,1000,600)
        pid=tracked[0]['track_id']
        for i in range(2,42):analyzer.update([],i,i*.1,1000,600)
        tracked,_=analyzer.update([box(0,(102,0,202,300))],42,4.2,1000,600)
        self.assertEqual(tracked[0]['track_id'],pid)

    def test_stationary_package_recovers_id_after_gap_without_duplicate_red(self):
        analyzer=SceneAnalyzer(.2)
        for i in range(10):
            _,items=analyzer.update([box(24,(100,100,160,180))],i+1,i*.1,1000,600)
        first=items[0]
        for i in range(10,60):analyzer.update([],i+1,i*.1,1000,600)
        for i in range(60,75):
            _,items=analyzer.update([box(26,(100,100,160,180))],i+1,i*.1,1000,600)
        self.assertEqual(items[0]['id'],first['id'])
        self.assertEqual(items[0]['alarm_revision'],first['alarm_revision'])
        self.assertEqual(items[0]['alarm_frame'],first['alarm_frame'])

    def test_red_episode_does_not_repeat_after_detection_flickers(self):
        analyzer=SceneAnalyzer(.1)
        for i in range(30):
            detections=[] if i in (9,18) else [box(24,(100,100,160,180))]
            analyzer.update(detections,i+1,i*.1,1000,600)
        self.assertEqual(analyzer.summary()[0]['alarm_revision'],1)

    def test_put_down_then_leave_is_placement_not_handoff(self):
        placement=PlacementEvidence(); handoff=HandoffEvidence()
        events=[]; transfers=[]
        for i in range(5):
            owners=[owner()]; bag=[220,220,260,280]
            placement.update(owners,bag,i*.1,i+1,1000,0)
            handoff.update(owners,(240,250),i*.1,i+1,1000,bag_box=bag)
        for i in range(5,26):
            y=min(330,220+(i-4)*22)
            bag=[220,y,260,y+60]
            owners=([owner()] if i<11 else [owner(contact=.1,bbox=(0,0,120,400)),owner('P002',.9)])
            event=placement.update(owners,bag,i*.1,i+1,1000,max(0,i*.1-.9))
            transfer=handoff.update(owners,(240,y+30),i*.1,i+1,1000,bag_box=bag)
            if event:events.append(event)
            if transfer:transfers.append(transfer)
        self.assertEqual(transfers,[])
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['type'],'suspected_left_behind')
        self.assertIn(events[0]['reason_code'],('placed_pending_review','placed_then_left'))

    def test_put_down_while_holder_stays_warns_for_review_without_asserting_departure(self):
        evidence=PlacementEvidence()
        events=[]
        for i in range(30):
            bag=[220,220,260,280] if i<5 else [220,330,260,390]
            event=evidence.update([owner()],bag,i*.1,i+1,1000,max(0,i*.1-.5))
            if event:events.append(event)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['reason_code'],'placed_pending_review')

    def test_short_dropout_does_not_warn_and_unattended_stillness_warns_once(self):
        evidence=PlacementEvidence(); events=[]
        for i in range(30):
            event=evidence.update([], [220,330,260,390],i*.1,i+1,1000,i*.1)
            if i<15:self.assertIsNone(event)
            if event:events.append(event)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['reason_code'],'unattended_stationary')

    def test_id_switch_without_two_people_coexisting_cannot_be_handoff(self):
        evidence=HandoffEvidence()
        for i in range(5):evidence.update([owner()],(230,250),i*.1,i+1,1000)
        for i in range(5,16):
            self.assertIsNone(evidence.update([owner('P002')],(230+i*4,250),i*.1,i+1,1000))

    def test_downward_movement_beside_second_person_cannot_be_handoff(self):
        evidence=HandoffEvidence()
        for i in range(5):evidence.update([owner()],(230,250),i*.1,i+1,1000)
        for i in range(5,16):
            self.assertIsNone(evidence.update([owner(contact=.4),owner('P002')],(230,250+i*7),i*.1,i+1,1000))

    def test_real_lateral_acquisition_still_warns_once(self):
        evidence=HandoffEvidence(); events=[]
        for i in range(5):evidence.update([owner()],(230,250),i*.1,i+1,1000)
        for i in range(5,16):
            event=evidence.update([owner(contact=.4),owner('P002')],(230+(i-5)*5,250),i*.1,i+1,1000,
                                  bag_box=[210+(i-5)*5,220,250+(i-5)*5,280])
            if event:events.append(event)
        self.assertEqual(len(events),1)

    def test_overhead_view_person_and_bag_move_down_together_is_acquisition(self):
        evidence=HandoffEvidence(); events=[]
        for i in range(5):evidence.update([owner()],(230,250),i*.1,i+1,1000)
        for i in range(5,15):
            step=i-5
            receiver=owner('P002',bbox=(100,step*4,260,400+step*4))
            event=evidence.update([owner(contact=.4),receiver],(230,250+step*5),i*.1,i+1,1000,
                                  bag_box=[210,220+step*5,250,280+step*5])
            if event:events.append(event)
        self.assertEqual(len(events),1)

    def test_full_analyzer_putdown_then_departure_reports_placement(self):
        analyzer=SceneAnalyzer(30)
        first=None; warnings=[]
        for i in range(40):
            y=min(330,220+max(0,i-6)*18)
            a=(100,0,260,400) if i<16 else (0,0,80,400)
            b=(600,0,760,400) if i<16 else (220,0,380,400)
            frame=np.zeros((600,1000,3),dtype=np.uint8)
            frame[a[1]:a[3],a[0]:a[2]]=(240,240,240)
            frame[b[1]:b[3],b[0]:b[2]]=(20,40,100)
            _,items=analyzer.update([box(0,a),box(0,b),box(24,(220,y,260,y+60))],i+1,i*.1,1000,600,frame=frame)
            for item in items:
                if item['first_owner_id'] and first is None:first=item['first_owner_id']
                if item['warning_level']=='suspected':warnings.append(item)
        self.assertIsNotNone(first)
        self.assertTrue(warnings)
        self.assertEqual(warnings[-1]['event_type'],'suspected_left_behind')
        self.assertEqual(warnings[-1]['suspected_transfer_count'],0)
        self.assertEqual(warnings[-1]['transfer_count'],0)

    def test_slow_motion_cannot_accumulate_stationary_placement(self):
        evidence=PlacementEvidence()
        for i in range(40):
            self.assertIsNone(evidence.update([], [220+i*4,330,260+i*4,390],i*.1,i+1,1000,4.))

    def test_ambiguous_nearby_people_still_block_generic_unattended_warning(self):
        evidence=PlacementEvidence()
        for i in range(40):
            nearby={**owner(),'association_ambiguous':True}
            self.assertIsNone(evidence.update([nearby],[220,330,260,390],i*.1,i+1,1000,4.))

    def test_putdown_motion_survives_person_id_switch_without_formal_binding(self):
        evidence=PlacementEvidence();events=[]
        for i in range(30):
            person=owner(f'P{i//3+1:03d}')
            y=220 if i<5 else min(330,220+(i-4)*20)
            event=evidence.update([person],[220,y,260,y+60],i*.1,i+1,1000,max(0,i*.1-.5))
            if event:events.append(event)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['reason_code'],'placed_pending_review')

    def test_person_and_carried_bag_walking_down_is_not_putdown(self):
        evidence=PlacementEvidence()
        for i in range(40):
            dy=i*4
            person=owner(bbox=(100,dy,260,400+dy))
            self.assertIsNone(evidence.update([person],[220,220+dy,260,280+dy],i*.1,i+1,1000,0))


if __name__=='__main__':unittest.main()
