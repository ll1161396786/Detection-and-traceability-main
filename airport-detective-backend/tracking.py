"""Local multi-object association; appearance is clothing colour, never identity proof."""
import math
import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment


def clothing(frame, box):
    if frame is None:
        return None
    h,w=frame.shape[:2]
    x1,y1,x2,y2=box
    bw,bh=x2-x1,y2-y1
    patch=frame[max(0,int(y1+.2*bh)):min(h,int(y1+.65*bh)),
                max(0,int(x1+.2*bw)):min(w,int(x2-.2*bw))]
    if patch.size < 120:
        return None
    hsv=cv2.cvtColor(patch,cv2.COLOR_BGR2HSV)
    hist=cv2.calcHist([hsv],[0,1,2],None,[8,4,8],[0,180,0,256,0,256])
    return cv2.normalize(hist,None,alpha=1,norm_type=cv2.NORM_L1).flatten()


def contact(bag, person):
    """Distance to the sides/lower torso, normalized by the person's scale."""
    bx=(bag[0]+bag[2])/2;by=(bag[1]+bag[3])/2
    x1,y1,x2,y2=person
    height=max(1,y2-y1)
    # A bag carried at either side or in front, rather than only body centres.
    anchors=[(x,y1+fraction*height) for x in (x1,x2) for fraction in (.58,.9)]
    anchors.append(((x1+x2)/2,y1+.72*height))
    distance=min(math.hypot(bx-x,by-y)/height for x,y in anchors)
    gap=math.hypot(max(x1-bag[2],bag[0]-x2,0),max(y1-bag[3],bag[1]-y2,0))/height
    return .55*max(0.,1-gap/.6)+.45*max(0.,1-distance/.65)


def assign_tracks(boxes, tracks, diagonal, observation, iou, center, frame=None):
    features=[clothing(frame,b['xyxy']) if b['class_id']==0 else None for b in boxes]
    occluded={i for i,b in enumerate(boxes) if b['class_id']==0 and any(
        j!=i and other['class_id']==0 and iou(b['xyxy'],other['xyxy'])>.25 for j,other in enumerate(boxes))}
    for i in occluded:features[i]=None
    ids=list(tracks)
    if not boxes or not ids:
        return {},features,set()
    costs=np.full((len(boxes),len(ids)),10.,dtype=float)
    for i,box in enumerate(boxes):
        bc=center(box['xyxy'])
        for j,tid in enumerate(ids):
            track=tracks[tid]
            same=box['class_id']==track['class_id'] or box['class_id'] in {24,26,28} and track['class_id'] in {24,26,28}
            if not same:
                continue
            gap=observation-track.get('last_observation',observation-1)
            velocity=track.get('velocity',(0.,0.))
            predicted=(track['center'][0]+velocity[0]*min(gap,4),track['center'][1]+velocity[1]*min(gap,4))
            distance=math.dist(bc,predicted)/max(1,diagonal)
            overlap=iou(box['xyxy'],track['bbox'])
            bh=track['bbox'][3]-track['bbox'][1];bw=track['bbox'][2]-track['bbox'][0]
            gate=.045+.65*max(bh,bw)/max(1,diagonal)
            if distance>gate and overlap<.12:
                continue
            appearance=0.
            if features[i] is not None and track.get('appearance') is not None:
                appearance=float(cv2.compareHist(features[i],track['appearance'],cv2.HISTCMP_BHATTACHARYYA))
                if appearance>.72 and overlap<.75:
                    continue
            costs[i,j]=.45*distance/max(gate,.001)+.25*(1-overlap)+.5*appearance+.015*(gap-1)
    rows,cols=linear_sum_assignment(costs)
    matches={}
    ambiguous=set(occluded)
    for i,j in zip(rows,cols):
        if costs[i,j]>=.95:
            continue
        matches[int(i)]=ids[j]
        other=np.delete(costs[i],j)
        if len(other) and min(other)-costs[i,j]<.06:
            ambiguous.add(int(i))
    return matches,features,ambiguous
