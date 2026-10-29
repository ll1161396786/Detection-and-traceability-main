"""Select larger, sharper native-pixel person crops without synthetic upscaling."""
import math
import cv2

JPEG_QUALITY = 96


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
