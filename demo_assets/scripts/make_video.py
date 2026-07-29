import cv2, numpy as np, pickle, math, datetime
import imageio_ffmpeg

OUT = "/tmp/claude-0/-home-user-usageHeatMap/631bd056-f74b-565b-a67c-3190618292b8/scratchpad"
FPS, DUR = 24, 30
W, H = 1920, 1440
NF = FPS * DUR
S = W / 2856.0  # half-res photo coords -> output coords

base = cv2.resize(cv2.imread(f"{OUT}/canteen_base_empty.jpg"), (W, H), interpolation=cv2.INTER_AREA)
stand = pickle.load(open(f"{OUT}/standing.pkl", "rb"))

def prep(idx):
    crop, a, bbox, conf = stand[idx]
    # shrink mask to kill background halo, then feather edges
    a = cv2.erode(a, np.ones((3, 3), np.uint8), iterations=2)
    a = cv2.GaussianBlur(a, (7, 7), 0).astype(np.float32) / 255.0
    return crop.astype(np.float32), a

SPR = {i: prep(i) for i in [0, 1]}
NATIVE_H = {i: stand[i][0].shape[0] for i in SPR}  # sprite height in half-res photo px

def depth_height(fy):
    """person pixel height (half-res coords) as a function of foot y"""
    # anchors: walkway y=1060 -> ~140 ; mid y=1450 -> ~330 ; front y=1900 -> ~560
    return np.interp(fy, [900, 1060, 1450, 1900], [110, 140, 330, 560])

class Walker:
    def __init__(self, spr, f0, f1, x0, x1, y0, y1, flip=False):
        self.spr, self.f0, self.f1 = spr, f0, f1
        self.x0, self.x1, self.y0, self.y1 = x0, x1, y0, y1
        self.flip = flip
        self.dist = 0.0
        self.px = x0
    def draw(self, frame, f):
        if not (self.f0 <= f < self.f1):
            return
        t = (f - self.f0) / (self.f1 - self.f0)
        t = t  # linear pace
        x = self.x0 + (self.x1 - self.x0) * t          # half-res coords
        y = self.y0 + (self.y1 - self.y0) * t
        self.dist += abs(x - self.px); self.px = x
        ph = float(depth_height(y))
        bob = 0.012 * ph * math.sin(2 * math.pi * self.dist / (ph * 0.55) + self.spr * 2)
        crop, a = SPR[self.spr]
        sc = ph / NATIVE_H[self.spr]
        sw, sh = max(2, int(crop.shape[1] * sc)), max(2, int(crop.shape[0] * sc))
        interp = cv2.INTER_CUBIC if sc > 1 else cv2.INTER_AREA
        c = cv2.resize(crop, (sw, sh), interpolation=interp)
        al = cv2.resize(a, (sw, sh), interpolation=interp)
        if self.flip:
            c, al = c[:, ::-1], al[:, ::-1]
        # output coords: foot anchor
        ox = int(x * S - sw * S / 2); oy = int(y * S - sh * S)
        sw2, sh2 = int(sw * S), int(sh * S)
        c = cv2.resize(c, (sw2, sh2)); al = cv2.resize(al, (sw2, sh2))
        oy += int(bob * S)
        # soft shadow under feet
        shw, shh = int(sw2 * 0.9), max(3, int(sh2 * 0.08))
        sx, sy = ox + sw2 // 2, oy + sh2
        sh_mask = np.zeros((H, W), np.float32)
        cv2.ellipse(sh_mask, (sx, sy), (shw // 2, shh), 0, 0, 360, 1.0, -1)
        sh_mask = cv2.GaussianBlur(sh_mask, (31, 31), 0) * 0.35
        frame[:] = frame * (1 - sh_mask[..., None]) + np.zeros(3) * sh_mask[..., None]
        # composite sprite
        x1o, y1o = max(ox, 0), max(oy, 0)
        x2o, y2o = min(ox + sw2, W), min(oy + sh2, H)
        if x2o <= x1o or y2o <= y1o:
            return
        cs = c[y1o - oy:y2o - oy, x1o - ox:x2o - ox]
        als = al[y1o - oy:y2o - oy, x1o - ox:x2o - ox][..., None]
        frame[y1o:y2o, x1o:x2o] = frame[y1o:y2o, x1o:x2o] * (1 - als) + cs * als

WALK_Y = 1075  # back walkway foot line (half-res coords)
walkers = [
    Walker(1, 0,   260, -80,  3000, WALK_Y, WALK_Y, flip=False),         # grey shirt L->R
    Walker(0, 100, 400, 2990, -100, WALK_Y + 5, WALK_Y + 5, flip=True),  # guard R->L
    Walker(1, 150, 430, 1550, 1350, 1780, 1085),                         # grey shirt walks away down aisle
    Walker(1, 330, 560, 2990, -80,  WALK_Y, WALK_Y, flip=True),          # grey shirt back R->L
    Walker(0, 450, 720, -100, 3000, WALK_Y + 5, WALK_Y + 5),             # guard L->R
    Walker(1, 500, 720, 900, 1000, 1085, 1650),                          # grey shirt walks toward camera
]

writer = imageio_ffmpeg.write_frames(
    f"{OUT}/canteen_demo_stream.mp4", (W, H), fps=FPS, codec="libx264",
    output_params=["-crf", "21", "-preset", "medium", "-pix_fmt", "yuv420p"])
writer.send(None)

t0 = datetime.datetime(2026, 7, 29, 12, 15, 0)
font = cv2.FONT_HERSHEY_SIMPLEX
for f in range(NF):
    frame = base.astype(np.float32).copy()
    for wkr in walkers:
        wkr.draw(frame, f)
    fr = frame.astype(np.uint8)
    # CCTV overlay
    ts = (t0 + datetime.timedelta(seconds=f / FPS)).strftime("%Y-%m-%d  %H:%M:%S")
    cv2.rectangle(fr, (0, 0), (W, 54), (0, 0, 0), -1)
    fr[0:54] = (fr[0:54] * 0.35).astype(np.uint8)
    cv2.putText(fr, "CAM 01  -  CANTEEN", (18, 38), font, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(fr, ts, (W - 520, 38), font, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    if (f // 12) % 2 == 0:
        cv2.circle(fr, (W - 580, 28), 10, (0, 0, 255), -1)
    cv2.putText(fr, "LIVE", (W - 660, 38), font, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
    writer.send(np.ascontiguousarray(fr[..., ::-1]))  # BGR->RGB
    if f % 120 == 0:
        print("frame", f, "/", NF)
writer.close()
print("video done")
