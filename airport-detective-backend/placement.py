"""Temporal placement/departure warnings from boxes, not action recognition."""
import math
from dataclasses import dataclass
from handoff import near_feet


@dataclass(frozen=True)
class PlacementPolicy:
    carry_frames: int = 3
    carry_seconds: float = .12
    rest_frames: int = 3
    rest_seconds: float = .20
    observation_gap: float = .85
    source_seconds: float = 10.
    lost_person_seconds: float = .8
    occlusion_grace_seconds: float = 2.
    lift_frames: int = 2
    lift_seconds: float = .04


class PlacementEvidence:
    def __init__(self, policy=None):
        self.policy=policy or PlacementPolicy()
        self.source=None
        self.proposed=None
        self.position=None
        self.last_time=None
        self.still_since=None
        self.still_origin=None
        self.separated_since=None
        self.rest_frames=0
        self.rest_since=None
        self.rest_origin=None
        self.warned=False
        self.last_nearby=-math.inf
        self.floor=None
        self.floor_event=None
        self.floor_frame=None

    def observe_floor(self, owners, bag, timestamp, frame_index):
        """Keep weak but repeated floor observations; only confirmed bags may emit."""
        if frame_index==self.floor_frame:return
        self.floor_frame=frame_index
        position=((bag[0]+bag[2])/2,(bag[1]+bag[3])/2)
        if self.floor and timestamp-self.floor['last']>2.:
            self.floor=None
        old=self.floor
        if old:
            same=[o for o in owners if o.get('present') and o.get('bbox') and
                  (abs(o['bbox'][3]-old['body'][3])<=.18*old['height'] or o['person_id']==old['person_id']) and
                  abs((o['bbox'][0]+o['bbox'][2]-old['body'][0]-old['body'][2])/2)<=.35*old['height']]
            lifted=(old['position'][1]-position[1]>=.08*old['height'] and
                    abs(position[0]-old['position'][0])<=.3*old['height'] and
                    .4<=max(1,(bag[2]-bag[0])*(bag[3]-bag[1]))/old['area']<=2.5)
            relative_lift=any(old['position'][1]-position[1]-(0 if o['person_id']==old['person_id'] and
                             o['bbox'][3]-o['bbox'][1]<.65*old['height'] else old['body'][3]-o['bbox'][3])
                             >=.06*old['height'] for o in same)
            lifted=lifted and relative_lift
            if same and old['bent'] and old['count']>=3 and old['last']-old['start']>=.12 and lifted:
                old['lift_start']=old.get('lift_start',timestamp)
                old['lift_count']=old.get('lift_count',0)+1
                if old['lift_count']>=self.policy.lift_frames and timestamp-old['lift_start']+1e-6>=self.policy.lift_seconds:
                    self.floor_event={'type':'suspected_left_behind','frame':frame_index,'time':round(timestamp,3),
                                      'person_id':old['person_id'],'person_bbox':list(old['body']),'person_frame':old['body_frame'],
                                      'reason_code':'floor_then_pickup','requires_review':True}
                return  # Keep the ground reference while accumulating the lift.
            else:
                old.pop('lift_start',None);old['lift_count']=0
            if same and old['bent'] and old['count']>=3 and old['position'][1]-position[1]>.04*old['height']:
                return  # Do not replace the ground reference midway through a lift.
        possible=[]
        for owner in owners:
            if not owner.get('present') or not owner.get('bbox') or owner.get('contact_score',0)<.65:continue
            body=owner['bbox'];height=max(1,body[3]-body[1]);width=body[2]-body[0]
            if (abs(bag[3]-body[3])<=.25*height and position[1]>=body[1]+.55*height
                    and body[0]-.15*height<=position[0]<=body[2]+.15*height):
                possible.append((abs(bag[3]-body[3])/height,owner,height,width))
        if not possible:return
        _,person,height,width=min(possible,key=lambda x:x[0])
        if (not self.floor or math.dist(position,self.floor['position'])>.04*height
                or abs(person['bbox'][3]-self.floor['body'][3])>.18*height):
            self.floor={'position':position,'body':list(person['bbox']),'height':height,'area':max(1,(bag[2]-bag[0])*(bag[3]-bag[1])),
                        'person_id':person['person_id'],'body_frame':frame_index,'start':timestamp,'last':timestamp,'count':0,'bent':False}
        self.floor.update(last=timestamp,count=self.floor['count']+1,
                          bent=self.floor['bent'] or width/height>=.65)

    def update(self, owners, bag, timestamp, frame_index, diagonal, stationary, handoff=False):
        p=self.policy
        position=((bag[0]+bag[2])/2,(bag[1]+bag[3])/2)
        previous=self.position
        gap=timestamp-self.last_time if self.last_time is not None else 0.
        if gap>p.observation_gap:
            self.source=None;self.proposed=None
            self.rest_frames=0;self.rest_since=None;self.rest_origin=None
        moved=self.still_origin is None or math.dist(position,self.still_origin)>.01*diagonal or gap>.85
        if moved:
            self.still_since=timestamp
            self.still_origin=position
        self.position=position
        self.last_time=timestamp
        # Ambiguous identity is still a visible nearby human. Excluding these
        # boxes used to turn crowded scenes into false "unattended" warnings.
        visible=[o for o in owners if o.get('present')]
        self.observe_floor(owners,bag,timestamp,frame_index)
        if not self.warned and self.floor_event and timestamp-self.floor_event['time']<=1.:
            self.warned=True
            event=self.floor_event;self.floor_event=None
            return event
        nearby=any(o.get('contact_score',0)>=.5 for o in visible)
        if nearby:self.last_nearby=timestamp
        strong=sorted((o for o in visible if o.get('probability',0)>=.65 and o.get('contact_score',0)>=.65),
                      key=lambda o:-o['probability'])
        best=strong[0] if strong else None
        if (best and best.get('association_ambiguous') and len(strong)>1
                and best['probability']-strong[1]['probability']<.05):
            best=None  # Do not derive a body scale from a near-tie in a crowd.
        # Prefer the observed source over an unrelated nearer passer-by.
        original=next((o for o in strong if self.source and o['person_id']==self.source['id']),None)
        if original:best=original
        if self.source:
            observed=next((o for o in visible if o['person_id']==self.source['id']),None)
            if observed:self.source['last_seen']=timestamp
        if best:
            person=best['bbox'];height=max(1,person[3]-person[1])
            relative=(position[1]-person[1])/height
            carrying=bag[3]<person[3]-.18*height and relative<.76
        else:
            person=None;height=max(1,(self.source or {}).get('height',1));relative=None;carrying=False
        if carrying:
            # Placement evidence belongs to the package trajectory. A person ID
            # switch must not reset the observed carrying-to-floor movement.
            if not self.proposed or timestamp-self.proposed['last']>.8:
                self.proposed={'count':0,'first':timestamp,'last':timestamp,'position':position}
            self.proposed['count']+=1
            self.proposed['last']=timestamp
            if self.proposed['count']>=p.carry_frames and timestamp-self.proposed['first']+1e-6>=p.carry_seconds:
                # Follow sustained carrying so a later put-down is measured from
                # the latest carried pose, not an obsolete image position.
                if (self.source is None or timestamp-self.source['time']>p.source_seconds
                        or relative<=self.source['relative']+.025):
                    self.source={'id':best['person_id'] if not best.get('association_ambiguous') else None,
                                 'position':position,'person_box':list(person),'height':height,
                                 'relative':relative,'time':timestamp,'last_seen':timestamp,
                                 'person_frame':frame_index,
                                 'bag_size':max(1,(bag[2]-bag[0])*(bag[3]-bag[1]))}
                # A new episode requires real sustained carrying, not jitter.
                if (self.warned and timestamp-self.proposed['first']>=1.
                        and math.dist(position,self.proposed['position'])>.03*diagonal
                        and relative<=self.source['relative']+.04):
                    self.warned=False
                    self.source=None
        else:
            self.proposed=None
        if handoff:
            self.source=None
            self.separated_since=None
            self.rest_frames=0
            return None
        if self.warned or self.still_since is None:
            return None
        source_person=next((o for o in visible if self.source and self.source['id'] and o['person_id']==self.source['id']),None)
        separated=source_person is None or source_person.get('contact_score',0)<.5
        self.separated_since=(self.separated_since if self.separated_since is not None else timestamp) if separated else None
        placed=False
        if self.source and timestamp-self.source['time']<=p.source_seconds:
            old=self.source
            # Brief loss of the source must not suppress an otherwise observed
            # put-down. Never borrow an unrelated person's scale as evidence.
            reference=person
            compatible=bool(reference and .65<=height/old['height']<=1.55
                            and abs((reference[0]+reference[2]-old['person_box'][0]-old['person_box'][2])/2)<=.35*old['height'])
            if not compatible and timestamp-old['last_seen']<=p.lost_person_seconds:
                reference=old['person_box'];height=old['height']
            elif not compatible:
                reference=None
            relative=(position[1]-reference[1])/height if reference else old['relative']
            floor=bool(reference and (near_feet(bag,reference) or bag[3]>=reference[3]-.23*height and relative>=.58))
            # Use package motion relative to the body as well as absolute motion;
            # walking toward an overhead camera must not look like putting down.
            body_dy=((reference[1]+reference[3]-old['person_box'][1]-old['person_box'][3])/2) if reference else 0.
            scale_ok=.5<=max(1,(bag[2]-bag[0])*(bag[3]-bag[1]))/old['bag_size']<=2.
            lowered=(scale_ok and position[1]-old['position'][1]>=.08*old['height']
                     and position[1]-old['position'][1]-body_dy>=.08*old['height'] and relative-old['relative']>=.08)
            slow=previous is not None and gap<=p.observation_gap and math.dist(position,previous)<=.035*height
            if floor and lowered and slow:
                if not self.rest_frames or math.dist(position,self.rest_origin)>.03*height:
                    self.rest_since=timestamp;self.rest_origin=position;self.rest_frames=0
                self.rest_frames+=1
            else:
                self.rest_frames=0;self.rest_since=None
            placed=self.rest_frames>=p.rest_frames and timestamp-self.rest_since+1e-6>=p.rest_seconds
        else:
            self.rest_frames=0;self.rest_since=None
        if placed:
            # This is an early yellow placement warning even if the person stays.
            # It does not assert abandonment or a change of ownership.
            reason='placed_pending_review'
            if not nearby and self.separated_since is not None and timestamp-self.separated_since>=.8:
                reason='placed_then_left'
        elif (not nearby and timestamp-self.last_nearby>p.occlusion_grace_seconds
              and stationary>=1.5 and timestamp-self.still_since>=.8
              and self.separated_since is not None and timestamp-self.separated_since>=.8):
            reason='unattended_stationary'
        else:
            return None
        self.warned=True
        return {'type':'suspected_left_behind','frame':frame_index,'time':round(timestamp,3),
                'person_id':self.source['id'] if self.source else None,
                'person_bbox':list(self.source['person_box']) if self.source else None,
                'person_frame':self.source.get('person_frame') if self.source else None,
                'reason_code':reason,'requires_review':True}
