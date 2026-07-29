import cv2, numpy as np, os, pickle
from ultralytics import YOLO

SRC = "/root/.claude/uploads/631bd056-f74b-565b-a67c-3190618292b8/3a4561ce-IMG_5230.jpeg"
OUT = "/tmp/claude-0/-home-user-usageHeatMap/631bd056-f74b-565b-a67c-3190618292b8/scratchpad"

img_full = cv2.imread(SRC)
h0, w0 = img_full.shape[:2]
print("full:", w0, h0)

# work at half resolution (2856x2142) - plenty for a demo camera feed
img = cv2.resize(img_full, (w0 // 2, h0 // 2), interpolation=cv2.INTER_AREA)
H, W = img.shape[:2]

model = YOLO("yolov8x-seg.pt")
# high-res inference + low conf to catch the small far-away people
res = model.predict(img, imgsz=1920, conf=0.12, classes=[0], verbose=False, retina_masks=True)[0]

mask = np.zeros((H, W), np.uint8)
sprites = []  # (crop_bgr, crop_alpha, bbox) for the video stage
n = 0
if res.masks is not None:
    for m, box, conf in zip(res.masks.data.cpu().numpy(), res.boxes.xyxy.cpu().numpy(), res.boxes.conf.cpu().numpy()):
        n += 1
        mm = (cv2.resize(m, (W, H)) > 0.5).astype(np.uint8) * 255
        mask |= mm
        x1, y1, x2, y2 = [int(v) for v in box]
        bw, bh = x2 - x1, y2 - y1
        if bh > 180 and conf > 0.5:  # decent-sized cutouts for animation sprites
            crop = img[y1:y2, x1:x2].copy()
            a = mm[y1:y2, x1:x2].copy()
            sprites.append((crop, a, (x1, y1, x2, y2), float(conf)))
print("people detected:", n, "| sprites kept:", len(sprites))

# grow the mask so shadows/edges around each person are also inpainted
mask_d = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)), iterations=2)
cv2.imwrite(f"{OUT}/mask.png", mask_d)

print("inpainting (this is the slow part)...")
clean = cv2.inpaint(img, mask_d, 7, cv2.INPAINT_TELEA)
# second gentle pass to smooth streaks left by the first
mask_d2 = cv2.dilate(mask_d, np.ones((5, 5), np.uint8))
clean = cv2.inpaint(clean, cv2.erode(mask_d2, np.ones((9, 9), np.uint8)), 5, cv2.INPAINT_NS)

cv2.imwrite(f"{OUT}/canteen_base_empty.jpg", clean, [cv2.IMWRITE_JPEG_QUALITY, 92])
with open(f"{OUT}/sprites.pkl", "wb") as f:
    pickle.dump(sprites, f)
print("done ->", f"{OUT}/canteen_base_empty.jpg")
