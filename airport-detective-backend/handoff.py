"""Early yellow handoff evidence, separate from a formally accepted holder change."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class HandoffPolicy:
    source_frames: int = 3
    source_seconds: float = .08
    destination_frames: int = 2
    destination_seconds: float = .04
    evidence_gap_seconds: float = .8
    transition_seconds: float = 2.
    minimum_score: float = .75
    minimum_contact: float = .75
    candidate_margin: float = .03
    release_margin: float = .18
    movement_ratio: float = .008


class HandoffEvidence:
    def __init__(self, policy=None):
        self.policy=policy or HandoffPolicy()
        self.phase=None
        self.anchor=None

    def update(self, owners, position, timestamp, frame_index, diagonal):
        p=self.policy
        eligible=sorted((o for o in owners if o.get('present') and not o.get('association_ambiguous')
                         and o.get('contact_score',0)>=p.minimum_contact and o.get('probability',0)>=p.minimum_score),
                        key=lambda o:-o['probability'])
        if not eligible or len(eligible)>1 and eligible[0]['probability']-eligible[1]['probability']<p.candidate_margin:
            return None
        best=eligible[0]
        if self.anchor and timestamp-self.anchor['last_time']>p.transition_seconds:
            self.anchor=None
        if (not self.phase or self.phase['person_id']!=best['person_id']
                or timestamp-self.phase['last_time']>p.evidence_gap_seconds):
            self.phase={'person_id':best['person_id'],'frames':0,'start':timestamp,'last_time':timestamp,
                        'position':position,'released_frames':0}
        phase=self.phase
        phase['frames']+=1
        phase['last_time']=timestamp
        if self.anchor and self.anchor['person_id']==best['person_id']:
            self.anchor.update(last_time=timestamp,position=position,frames=phase['frames'])
            return None
        if not self.anchor:
            if phase['frames']>=p.source_frames and timestamp-phase['start']+1e-6>=p.source_seconds:
                self.anchor={'person_id':best['person_id'],'frames':phase['frames'],
                             'last_time':timestamp,'position':position}
            return None
        previous=next((o for o in owners if o['person_id']==self.anchor['person_id'] and o.get('present')),None)
        released=previous is None or best['contact_score']-previous.get('contact_score',0)>=p.release_margin
        phase['released_frames']=phase['released_frames']+1 if released else 0
        moved=math.dist(position,self.anchor['position'])/max(1,diagonal)>=p.movement_ratio
        if (phase['frames']<p.destination_frames or phase['released_frames']<p.destination_frames
                or timestamp-phase['start']+1e-6<p.destination_seconds or not moved):
            return None
        event={'from':self.anchor['person_id'],'to':best['person_id'],'time':round(timestamp,3),
               'frame':frame_index,'source_frames':self.anchor['frames'],'destination_frames':phase['frames'],
               'type':'suspected_handoff','requires_review':True}
        self.anchor={'person_id':best['person_id'],'frames':phase['frames'],'last_time':timestamp,'position':position}
        return event
