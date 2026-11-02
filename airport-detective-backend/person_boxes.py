"""Conservative duplicate-person suppression; overlapping people are not duplicates."""


def same_person_box(a, b):
    ax,ay,ar,ab=a['xyxy'];bx,by,br,bb=b['xyxy']
    aw,ah=max(0,ar-ax),max(0,ab-ay);bw,bh=max(0,br-bx),max(0,bb-by)
    if min(aw,ah,bw,bh)<=0:return False
    intersection=max(0,min(ar,br)-max(ax,bx))*max(0,min(ab,bb)-max(ay,by))
    # A narrow alternate body box can have low IoU yet describe the same person.
    # Require matching head/feet and horizontal centres, not containment alone.
    return (intersection/min(aw*ah,bw*bh)>=.94 and min(ah,bh)/max(ah,bh)>=.85
            and min(aw*ah,bw*bh)/max(aw*ah,bw*bh)>=.35
            and abs((ax+ar-bx-br)/2)<=.12*max(aw,bw)
            and abs(ay-by)<=.08*max(ah,bh) and abs(ab-bb)<=.08*max(ah,bh))


def deduplicate_people(boxes):
    result=[]
    for box in sorted(boxes,key=lambda b:-b['confidence']):
        match=next((i for i,old in enumerate(result) if box['class_id']==old['class_id']==0 and same_person_box(box,old)),None)
        if match is None:
            result.append(box)
        else:
            old=result[match]
            area=lambda b:(b['xyxy'][2]-b['xyxy'][0])*(b['xyxy'][3]-b['xyxy'][1])
            if area(box)>area(old) and box['confidence']>=old['confidence']-.1:
                result[match]=box
    return result
