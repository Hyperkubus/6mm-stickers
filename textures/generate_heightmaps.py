import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

# The five final textures (skipping the rejected first v1 attempt 1783202917224)
FILES = {
    "reference": "1783202632474_image.png",
    "v1_rocky":  "1783203031634_image.png",
    "v2_soil":   "1783203165279_image.png",
    "v3_grass":  "1783203267654_image.png",
    "v4_track":  "1783203413664_image.png",
}
SRC = "/mnt/user-data/uploads/"
OUT = "/home/claude/out/"

import os
os.makedirs(OUT, exist_ok=True)

def heightmap(path):
    img = cv2.imread(path)
    img_f = img.astype(np.float32) / 255.0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    H, S, V = hsv[...,0]/179.0, hsv[...,1]/255.0, hsv[...,2]/255.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)/255.0

    # --- Rock mask: dark AND desaturated (basalt is grey; soil/grass is warm/saturated)
    rockness = (1.0 - S) * (1.0 - V)
    rockness = np.clip((rockness - np.percentile(rockness, 55)) /
                       (np.percentile(rockness, 99) - np.percentile(rockness, 55) + 1e-6), 0, 1)
    # smooth into rounded domes rather than hard plateaus
    rock_soft = gaussian_filter(rockness, sigma=2.5)
    rock_soft = rock_soft / (rock_soft.max() + 1e-6)

    # --- Scrub mask: green hue, some saturation -> slight bump
    green = ((H > 0.17) & (H < 0.45) & (S > 0.25)).astype(np.float32)
    green = gaussian_filter(green, sigma=2.0)
    green = np.clip(green * 2.0, 0, 1)

    # --- Fine grain: high-pass of luminance for pebble/grass micro-relief
    lowpass = gaussian_filter(gray, sigma=6)
    highpass = gray - lowpass
    # normalize to +-1, damp
    hp_std = highpass.std() + 1e-6
    grain = np.clip(highpass / (3*hp_std), -1, 1)

    # --- Compose. Base 0.35, rocks up to +0.55, scrub +0.15, grain +-0.08
    h = 0.35 + 0.55*rock_soft + 0.15*green*(1.0 - rock_soft) + 0.08*grain
    h = np.clip(h, 0, 1)
    # gentle overall smoothing to avoid single-pixel spikes the printer can't resolve anyway
    h = gaussian_filter(h, sigma=0.8)
    # renormalize to use full range
    h = (h - h.min()) / (h.max() - h.min() + 1e-6)
    # gamma to keep most of the surface low and rocks prominent
    h = h ** 1.3
    return img, (h * 255).astype(np.uint8)

for name, fn in FILES.items():
    img, hm = heightmap(SRC + fn)
    cv2.imwrite(f"{OUT}heightmap_{name}.png", hm)
    # side-by-side preview: color | heightmap, downscaled
    hm3 = cv2.cvtColor(hm, cv2.COLOR_GRAY2BGR)
    prev = np.hstack([img, hm3])
    prev = cv2.resize(prev, (prev.shape[1]//2, prev.shape[0]//2))
    cv2.imwrite(f"{OUT}preview_{name}.jpg", prev, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(name, "done", hm.shape)
