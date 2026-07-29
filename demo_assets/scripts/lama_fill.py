import cv2, numpy as np
from PIL import Image
from simple_lama_inpainting import SimpleLama

OUT = "/tmp/claude-0/-home-user-usageHeatMap/631bd056-f74b-565b-a67c-3190618292b8/scratchpad"
SRC = "/root/.claude/uploads/631bd056-f74b-565b-a67c-3190618292b8/3a4561ce-IMG_5230.jpeg"

img_full = cv2.imread(SRC)
h0, w0 = img_full.shape[:2]
img = cv2.resize(img_full, (w0 // 2, h0 // 2), interpolation=cv2.INTER_AREA)
mask = cv2.imread(f"{OUT}/mask.png", 0)

lama = SimpleLama()
res = lama(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)), Image.fromarray(mask))
res = cv2.cvtColor(np.array(res), cv2.COLOR_RGB2BGR)[: img.shape[0], : img.shape[1]]
cv2.imwrite(f"{OUT}/canteen_base_empty.jpg", res, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("done", res.shape)
