"""Freeze event participants; current nearest neighbours are not event actors."""
import copy
from person_boxes import same_person_box


def snapshot(candidate):
    roles=[]
    if candidate.get('event_type')=='suspected_handoff':
        transfers=candidate.get('suspected_transfers',[])+candidate.get('transfers',[])
        event=next((e for e in reversed(transfers) if e.get('frame')==candidate.get('alarm_frame')),None)
        if event:
            for side,role in (('from','handoff_source'),('to','handoff_recipient')):
                roles.append((event.get(side),role,event.get(side+'_bbox'),event.get(side+'_frame'),event.get(side+'_score')))
    elif candidate.get('event_type')=='suspected_left_behind':
        events=candidate.get('placement_events',[])
        if events:
            e=events[-1]
            roles.append((e.get('person_id'),'placement_actor',e.get('person_bbox'),e.get('person_frame'),None))
    else:
        pid=candidate.get('current_owner_id')
        owner=next((o for o in candidate.get('owners',[]) if o.get('person_id')==pid and o.get('present')),None)
        if owner:roles.append((pid,'last_associated',owner.get('bbox'),candidate.get('alarm_frame'),owner.get('probability')))
    result=[]
    for pid,role,bbox,frame,score in roles:
        if not pid or not bbox or not frame:continue
        if any(o['person_id']==pid or (o['evidence_frame']==frame and same_person_box({'xyxy':o['bbox']},{'xyxy':bbox})) for o in result):
            # Duplicate evidence cannot establish two distinct participants.
            result[0]['event_role']='association_uncertain'
            continue
        result.append({'person_id':pid,'event_role':role,'bbox':list(bbox),'evidence_frame':int(frame),
                       'probability':score,'is_current_owner':False,'is_recent_owner':False})
    return copy.deepcopy(result)
