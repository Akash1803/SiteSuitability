"""Teardrop map pin (PIL)."""
import math
from PIL import Image, ImageDraw
def teardrop(r=34, h=118, col=(220,30,30), outline=(255,255,255), ow=5, ss=4):
    """Return an RGBA pin image and the tip offset (x,y) inside it."""
    R, Hh, OW = r*ss, h*ss, ow*ss
    cy = Hh - math.hypot(R, 0) - (Hh - 2*R) if False else R + OW      # circle centre from top
    tipy = Hh + OW
    W = 2*(R+OW)+2; Ht = tipy+OW+2
    cx = W/2
    d_ = tipy - cy; a = math.acos(R/d_)                                   # tangent angle
    pts=[]
    for k in range(0,361):
        t = math.radians(90) + a + (2*math.pi-2*a)*k/360                  # arc around the top
        pts.append((cx + R*math.cos(t), cy + R*math.sin(t)))
    pts.append((cx, tipy))
    im = Image.new("RGBA",(int(W),int(Ht)),(0,0,0,0)); d = ImageDraw.Draw(im)
    d.polygon(pts, fill=outline)                                          # white rim
    inner=[(cx+(x-cx)*(1-OW/R*0.9), cy+(y-cy)*(1-OW/R*0.9)) for x,y in pts[:-1]]+[(cx, tipy-OW*1.6)]
    d.polygon(inner, fill=col)
    dr = R*0.38; d.ellipse([cx-dr, cy-dr, cx+dr, cy+dr], fill=(255,255,255))
    im = im.resize((int(W/ss), int(Ht/ss)), Image.LANCZOS)
    return im, (W/ss/2, tipy/ss)
