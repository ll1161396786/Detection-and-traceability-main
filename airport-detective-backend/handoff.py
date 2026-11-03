"""Early yellow handoff evidence, separate from a formally accepted holder change."""
from dataclasses import dataclass
import math


def near_feet(bag, person):
    """Image-plane floor proxy, not a calibrated ground-plane estimate."""
    height=max(1.,person[3]-person[1])
    return abs(bag[3]-person[3])/height<=.14 and (bag[1]+bag[3])/2>=person[1]+.78*height


def usable_body(bag, person, reference=None):
    if not person or bag is None:return True
    height=max(1,person[3]-person[1])
    if bag[3]-bag[1]>.85*height:return False
    return reference is None or .6<=height/max(1,reference[3]-reference[1])<=1.7


def acquisition_motion(origin, position, person_origin, person_box, diagonal, movement_ratio=.012):
    dx,dy=position[0]-origin[0],position[1]-origin[1]
    length=math.hypot(dx,dy)
    if length/max(1,diagonal)<movement_ratio:
        return False
    if dy<=-.008*diagonal or abs(dx)>=1.2*abs(dy):
        return True
    if person_origin is None or person_box is None:
        return False
    old=((person_origin[0]+person_origin[2])/2,(person_origin[1]+person_origin[3])/2)
    new=((person_box[0]+person_box[2])/2,(person_box[1]+person_box[3])/2)
    px,py=new[0]-old[0],new[1]-old[1]
    motion=math.hypot(px,py)
    # In an overhead camera a carried bag can move down the image along with
    # its recipient. Preserve that case, but reject a stationary bystander.
    alignment=(dx*px+dy*py)/max(1e-6,length*motion)
    drift=math.hypot(dx-px,dy-py)/max(1,person_box[3]-person_box[1])
    return motion>=.008*diagonal and alignment>=.6 and drift<=.18


@dataclass(frozen=True)
class HandoffPolicy:
    source_frames: int = 3
    source_seconds: float = .08
    destination_frames: int = 2
    destination_seconds: float = .3
    evidence_gap_seconds: float = .8
    transition_seconds: float = 2.
    minimum_score: float = .75
    minimum_contact: float = .75
    candidate_margin: float = .03
    release_margin: float = .18
    movement_ratio: float = .012


class HandoffEvidence:
    def __init__(self, policy=None):
        self.policy=policy or HandoffPolicy()
        self.phase=None
        self.anchor=None
        self.last_acquisition=None

    def acquired(self, person_id, timestamp):
        return bool(self.last_acquisition and self.last_acquisition['to']==person_id
                    and 0<=timestamp-self.last_acquisition['time']<=2.)

    def update(self, owners, position, timestamp, frame_index, diagonal, bag_box=None):
        p=self.policy
        eligible=sorted((o for o in owners if o.get('present') and not o.get('association_ambiguous')
                         and usable_body(bag_box,o.get('bbox'))
                         and o.get('contact_score',0)>=p.minimum_contact and o.get('probability',0)>=p.minimum_score),
                        key=lambda o:-o['probability'])
        if self.anchor and timestamp-self.anchor['last_time']>p.transition_seconds:
            self.anchor=None
        if not eligible or len(eligible)>1 and eligible[0]['probability']-eligible[1]['probability']<p.candidate_margin:
            self.phase=None
            return None
        best=eligible[0]
        if (not self.phase or self.phase['person_id']!=best['person_id']
                or timestamp-self.phase['last_time']>p.evidence_gap_seconds):
            self.phase={'person_id':best['person_id'],'frames':0,'start':timestamp,'last_time':timestamp,
                        'position':position,'released_frames':0,'person_origin':best.get('bbox')}
        phase=self.phase
        phase['frames']+=1
        phase['last_time']=timestamp
        if self.anchor and self.anchor['person_id']==best['person_id']:
            self.anchor.update(last_time=timestamp,position=position,frames=phase['frames'],person_box=best.get('bbox'),
                               frame=frame_index,score=best['probability'])
            return None
        if not self.anchor:
            if phase['frames']>=p.source_frames and timestamp-phase['start']+1e-6>=p.source_seconds:
                self.anchor={'person_id':best['person_id'],'frames':phase['frames'],
                             'last_time':timestamp,'position':position,'person_box':best.get('bbox'),
                             'frame':frame_index,'score':best['probability']}
            return None
        previous=next((o for o in owners if o['person_id']==self.anchor['person_id'] and o.get('present')),None)
        if previous and not usable_body(bag_box,previous.get('bbox'),self.anchor.get('person_box')):
            self.phase=None
            return None  # A collapsed/head-only box is not evidence of release.
        # A vanished source may just have received a new tracking ID. Require
        # observations of both people near the package before reporting a transfer.
        if previous is not None:
            phase['both_seen']=True
        released=previous is None or best['contact_score']-previous.get('contact_score',0)>=p.release_margin
        phase['released_frames']=phase['released_frames']+1 if released else 0
        # Downward motion alone is placement, not receiver acquisition.
        acquired_motion=acquisition_motion(phase['position'],position,phase['person_origin'],best.get('bbox'),diagonal,p.movement_ratio)
        floor=bool(bag_box is not None and best.get('bbox') and near_feet(bag_box,best['bbox']))
        if (phase['frames']<p.destination_frames or phase['released_frames']<p.destination_frames
                or timestamp-phase['start']+1e-6<p.destination_seconds or not acquired_motion
                or not phase.get('both_seen') or floor):
            return None
        event={'from':self.anchor['person_id'],'to':best['person_id'],'time':round(timestamp,3),
               'frame':frame_index,'source_frames':self.anchor['frames'],'destination_frames':phase['frames'],
               'from_bbox':self.anchor.get('person_box'),'from_frame':self.anchor.get('frame'),'from_score':self.anchor.get('score'),
               'to_bbox':best.get('bbox'),'to_frame':frame_index,'to_score':best['probability'],
               'type':'suspected_handoff','requires_review':True}
        self.last_acquisition=event
        self.anchor={'person_id':best['person_id'],'frames':phase['frames'],'last_time':timestamp,'position':position,'person_box':best.get('bbox'),
                     'frame':frame_index,'score':best['probability']}
        return event
