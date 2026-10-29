import unittest
from unittest.mock import patch
from types import SimpleNamespace
from handoff import HandoffEvidence
from analytics import SceneAnalyzer,draw_scene


def owner(pid,score,contact):
    return {'person_id':pid,'probability':score,'contact_score':contact,'present':True,
            'association_ambiguous':False,'bbox':[0,0,100,200]}


class EarlyHandoffTest(unittest.TestCase):
    def seed(self):
        evidence=HandoffEvidence()
        for i in range(3):
            self.assertIsNone(evidence.update([owner('P026',.96,.97),owner('P027',.92,.91)],(100,100),i*.04,i+1,1000))
        return evidence

    def test_sparse_observations_can_warn_before_formal_binding(self):
        evidence=self.seed()
        changed=[owner('P027',.92,.91),owner('P026',.73,.65)]
        self.assertIsNone(evidence.update(changed,(120,110),1.08,28,1000))
        event=evidence.update(changed,(140,120),1.64,42,1000)
        self.assertEqual((event['from'],event['to']),('P026','P027'))
        self.assertTrue(event['requires_review'])
        self.assertIsNone(evidence.update(changed,(150,130),1.68,43,1000))

    def test_single_new_candidate_does_not_warn(self):
        evidence=self.seed()
        self.assertIsNone(evidence.update([owner('P027',.95,.96)],(140,120),.5,15,1000))

    def test_stationary_package_and_ambiguous_people_do_not_warn(self):
        evidence=self.seed()
        for i in range(10):
            self.assertIsNone(evidence.update([owner('P027',.95,.96),owner('P026',.6,.5)],(100,100),.2+i*.04,i+6,1000))
        evidence=HandoffEvidence()
        for i in range(10):
            self.assertIsNone(evidence.update([owner('P026',.96,.97),owner('P027',.95,.96)],(100+i*10,100),i*.04,i+1,1000))
        self.assertIsNone(evidence.anchor)

    def test_confirmed_package_weak_matches_continue_without_red_from_weak_frames(self):
        analyzer=SceneAnalyzer(.1)
        for i in range(12):
            confidence=.9 if i<2 else .13
            detection={'class_id':24,'label':'backpack','label_zh':'背包','confidence':confidence,'xyxy':[100,100,160,180]}
            _,c=analyzer.update([detection],i+1,i*.04,1000,500)
            if i>=1:
                self.assertEqual(len(c),1)
                self.assertEqual(c[0]['warning_level'],'none')

    def test_unbound_display_is_dashed_and_never_owned(self):
        candidate={'id':'L001','bbox':[100,100,150,180],'state':'随身携带','warning_level':'none',
                   'current_owner_id':None,'owners':[owner('P026',.96,.97)]}
        with patch('analytics.cv2_label') as label,patch('analytics.cv2_rectangle'),patch('analytics.cv2_dashed_line') as dashed,patch('analytics.cv2_line') as solid:
            draw_scene(SimpleNamespace(shape=(300,400,3)),[],[candidate])
            dashed.assert_called_once()
            solid.assert_not_called()
            text=' '.join(call.args[1] for call in label.call_args_list)
            self.assertIn('UNASSIGNED',text)
            self.assertIn('CANDIDATE_NOT_BOUND',text)
            self.assertNotIn('OWNED',text)

    def test_accepted_holder_is_drawn_even_when_another_candidate_ranks_first(self):
        candidate={'id':'L001','bbox':[100,100,150,180],'state':'随身携带','warning_level':'none',
                   'current_owner_id':'P026','owners':[owner('P027',.96,.97),owner('P026',.9,.92)]}
        with patch('analytics.cv2_label') as label,patch('analytics.cv2_rectangle'),patch('analytics.cv2_dashed_line') as dashed,patch('analytics.cv2_line') as solid:
            draw_scene(SimpleNamespace(shape=(300,400,3)),[],[candidate])
            solid.assert_called_once()
            dashed.assert_not_called()
            self.assertTrue(any('ASSOC P026' in call.args[1] for call in label.call_args_list))

    def test_formal_binding_after_early_warning_does_not_duplicate_alarm(self):
        analyzer=SceneAnalyzer(30)
        index=0
        def tick(a,b,offset=0):
            nonlocal index
            index+=1
            boxes=[{'class_id':cls,'label':'person' if cls==0 else 'backpack','label_zh':'人' if cls==0 else '包',
                    'confidence':.95,'xyxy':list(coords)} for cls,coords in [(0,a),(0,b),(24,(220+offset,300,270+offset,370))]]
            return analyzer.update(boxes,index,index*.1,1000,600)[1]
        for _ in range(8):tick((100,0,300,500),(700,0,900,500))
        for step in range(9):tick((max(0,100-step*20),0,max(0,100-step*20)+180,500),(700-step*60,0,900-step*60,500))
        for offset in range(0,49,3):
            candidates=tick((0,0,180,500),(220+offset,0,420+offset,500),offset)
        item=candidates[0]
        self.assertGreaterEqual(item['suspected_transfer_count'],1)
        self.assertGreaterEqual(item['transfer_count'],1)
        self.assertEqual(item['alarm_revision'],1)


if __name__=='__main__':unittest.main()
