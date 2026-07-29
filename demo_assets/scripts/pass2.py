import cv2, numpy as np
from PIL import Image
from ultralytics import YOLO
from simple_lama_inpainting import SimpleLama

OUT = "/tmp/claude-0/-home-user-usageHeatMap/631bd056-f74b-565b-a67c-3190618292b8/scratchpad"
img = cv2.imread(f"{OUT}/canteen_base_empty.jpg")
H, W = img.shape[:2]

model = YOLO("yolov8x-seg.pt")
res = model.predict(img, imgsz=2560, conf=0.05, classes=[0], verbose=False, retina_masks=True)[0]
mask = np.zeros((H, W), np.uint8)
n = 0
if res.masks is not None:
    for m in res.masks.data.cpu().numpy():
        mask |= (cv2.resize(m, (W, H)) > 0.5).astype(np.uint8) * 255
        n += 1
print("pass2 detections:", n)

# manual boxes for ghost remnants LaMa/YOLO left behind (x1,y1,x2,y2 at 2856x2142)
manual = [
    (640, 1060, 900, 1280),   # hijab person left-back near counter
    (1000, 1230, 1230, 1420), # grey ghost remnant middle
    (1740, 1120, 1830, 1220), # red object remnant
    (455, 1085, 590, 1300),   # person near counter left
]
for x1, y1, x2, y2 in manual:
    mask[y1:y2, x1:x2] = 255

mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)), 2)
lama = SimpleLama()
out = lama(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), Image.fromarray(mask))
out = cv2.cvtColor(np.array(out), cv2.COLOR_RGB2BGR)[:H, :W]
cv2.imwrite(f"{OUT}/canteen_base_empty.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("saved")
