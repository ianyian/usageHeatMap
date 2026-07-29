# Demo assets

Generated demo media for showcasing the usage heat map with a canteen scene.

- `canteen_base.jpg` — the original canteen photo with all people removed
  (YOLOv8x segmentation + LaMa deep inpainting), usable as an empty-scene
  base/background picture.
- `canteen_demo_stream.mp4` — 30 s, 24 fps, 1920×1440 CCTV-style demo video
  built on the base picture, with animated people (cut-outs from the original
  photo) walking along the back walkway and the aisles. Loop it to simulate a
  live stream:

  ```bash
  ffmpeg -stream_loop -1 -re -i canteen_demo_stream.mp4 -f mpegts udp://127.0.0.1:5000
  # or simply loop it in VLC/OBS
  ```

- `scripts/` — the generation pipeline, in run order:
  1. `remove_people.py` — detect people, build masks, save sprite cut-outs
  2. `lama_fill.py` — LaMa inpainting of the masked people
  3. `pass2.py` — second detection + inpaint pass for leftovers
  4. `make_video.py` — composite animated walkers and render the MP4

  The scripts reference the session scratchpad paths they were run from;
  adjust `SRC`/`OUT` at the top of each file to rerun them elsewhere.
  Requirements: `ultralytics`, `simple-lama-inpainting`, `opencv-python`,
  `imageio-ffmpeg`.
