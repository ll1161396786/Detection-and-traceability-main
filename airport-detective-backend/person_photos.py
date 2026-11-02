"""Select larger, sharper native-pixel person crops without synthetic upscaling."""
import math
import cv2

JPEG_QUALITY = 96
TARGET_MARK_VERSION = 1


def person_crop(frame, bbox, width, height):
    """Keep native context pixels and the exact target box in crop coordinates."""
    height, width = min(height, frame.shape[0]), min(width, frame.shape[1])
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1, x2 = max(0, x1), min(width, x2)
    y1, y2 = max(0, y1), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return None, None
    pad_x, pad_y = max(12, (x2-x1)//8), max(12, (y2-y1)//12)
    left, top = max(0, x1-pad_x), max(0, y1-pad_y)
    right, bottom = min(width, x2+pad_x), min(height, y2+pad_y)
    return frame[top:bottom, left:right], [x1-left, y1-top, x2-left-1, y2-top-1]


def mark_target(crop, bbox):
    """Mark only this tracked person, without changing the source frame or IDs."""
    marked = crop.copy()
    x1, y1, x2, y2 = bbox
    thickness = max(2, min(8, round(max(crop.shape[:2])*.008)))
    cv2.rectangle(marked, (x1,y1), (x2,y2), (0,0,0), thickness+2)
    cv2.rectangle(marked, (x1,y1), (x2,y2), (40,255,90), thickness)
    return marked


def quality(crop, confidence=.9):
    height,width=crop.shape[:2]
    scale=min(1.,480/max(width,height))
    sample=cv2.resize(crop,(max(1,int(width*scale)),max(1,int(height*scale))),interpolation=cv2.INTER_AREA) if scale<1 else crop
    gray=cv2.cvtColor(sample,cv2.COLOR_BGR2GRAY)
    sharpness=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    score=math.sqrt(width*height)*(.25+.75*sharpness/(sharpness+80))*(.75+.25*confidence)
    return {'width':width,'height':height,'pixels':width*height,'sharpness':round(sharpness,3),
            'score':round(score,3),'jpeg_quality':JPEG_QUALITY}


def improves(candidate, previous):
    return not previous or (candidate['pixels']>=previous['pixels']*.85 and candidate['score']>previous['score']*1.10)
