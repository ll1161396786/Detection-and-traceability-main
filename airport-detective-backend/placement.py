"""Temporal placement/departure warnings from boxes, not action recognition."""
import math
from handoff import near_feet


class PlacementEvidence:
    def __init__(self):
        self.source=None
        self.proposed=None
        self.position=None
        self.last_time=None
        self.still_since=None
        self.still_origin=None
        self.separated_since=None
        self.rest_frames=0
        self.rest_since=None
        self.warned=False

    def update(self, owners, bag, timestamp, frame_index, diagonal, stationary, handoff=False):
        position=((bag[0]+bag[2])/2,(bag[1]+bag[3])/2)
        previous=self.position
        gap=timestamp-self.last_time if self.last_time is not None else 0.
        moved=self.still_origin is None or math.dist(position,self.still_origin)>.01*diagonal or gap>.85
        if moved:
            self.still_since=timestamp
            self.still_origin=position
        self.position=position
        self.last_time=timestamp
        # Ambiguous identity is still a visible nearby human. Excluding these
        # boxes used to turn crowded scenes into false "unattended" warnings.
        visible=[o for o in owners if o.get('present')]
        nearby=any(o.get('contact_score',0)>=.5 for o in visible)
        strong=sorted((o for o in visible if o.get('probability',0)>=.65 and o.get('contact_score',0)>=.65),
                      key=lambda o:-o['probability'])
        best=strong[0] if strong else None
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
            if self.proposed['count']>=2 and timestamp-self.proposed['first']+1e-6>=.04:
                if self.source is None or timestamp-self.source['time']>10.:
                    self.source={'id':best['person_id'] if not best.get('association_ambiguous') else None,
                                 'position':position,'person_box':list(person),'height':height,
                                 'relative':relative,'time':timestamp}
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
        if self.source and best and timestamp-self.source['time']<=10.:
            old=self.source
            floor=(near_feet(bag,person) or bag[3]>=person[3]-.23*height and relative>=.58)
            # Use package motion relative to the body as well as absolute motion;
            # walking toward an overhead camera must not look like putting down.
            lowered=position[1]-old['position'][1]>=.08*old['height'] and relative-old['relative']>=.08
            slow=previous is not None and gap<=.85 and math.dist(position,previous)<=.035*height
            if floor and lowered and slow:
                if not self.rest_frames:self.rest_since=timestamp
                self.rest_frames+=1
            else:
                self.rest_frames=0;self.rest_since=None
            placed=self.rest_frames>=2 and timestamp-self.rest_since+1e-6>=.04
        else:
            self.rest_frames=0;self.rest_since=None
        if placed:
            # This is an early yellow placement warning even if the person stays.
            # It does not assert abandonment or a change of ownership.
            reason='placed_pending_review'
            if not nearby and self.separated_since is not None and timestamp-self.separated_since>=.8:
                reason='placed_then_left'
        elif (not nearby and stationary>=1.5 and timestamp-self.still_since>=.8
              and self.separated_since is not None and timestamp-self.separated_since>=.8):
            reason='unattended_stationary'
        else:
            return None
        self.warned=True
        return {'type':'suspected_left_behind','frame':frame_index,'time':round(timestamp,3),
                'person_id':self.source['id'] if self.source else None,
                'reason_code':reason,'requires_review':True}
