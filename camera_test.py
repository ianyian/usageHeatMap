"""Minimal camera test: triggers the macOS camera permission prompt and shows
a live preview window. Run from Terminal:  .venv/bin/python camera_test.py
Press q in the preview window to quit.
"""
import sys

import cv2

print("Requesting camera 0 …", flush=True)
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("FAILED: camera not opened — macOS did not grant access.", flush=True)
    print("Check System Settings → Privacy & Security → Camera for this app.")
    sys.exit(1)

ok, frame = cap.read()
if not ok:
    print("FAILED: camera opened but no frame received.")
    sys.exit(1)

print(f"SUCCESS: got frame {frame.shape[1]}x{frame.shape[0]} — camera works.")
print("Showing live preview; press q to quit.")
while True:
    ok, frame = cap.read()
    if not ok:
        break
    cv2.imshow("camera test (press q to quit)", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
cap.release()
cv2.destroyAllWindows()
