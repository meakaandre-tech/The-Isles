#!/usr/bin/env python3
"""Contact sheets of the client screenshots: sheet.py <dir> <prefix> <first> <last> [out.png] (3x3 grid, numbered)"""
import sys
from PIL import Image, ImageDraw
d, pfx, a, b = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
ims = []
for i in range(a, b + 1):
    try: im = Image.open(f'{d}/{pfx}{i:02d}.png').convert('RGB').resize((640, 360))
    except Exception: continue
    dr = ImageDraw.Draw(im); dr.rectangle([0, 0, 46, 18], fill=(0, 0, 0)); dr.text((4, 3), str(i), fill=(255, 255, 0)); ims.append(im)
cols = 3; rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (640 * cols, 360 * rows))
for k, im in enumerate(ims): sheet.paste(im, ((k % cols) * 640, (k // cols) * 360))
out = sys.argv[5] if len(sys.argv) > 5 else f'{d}/sheet-{pfx}{a}-{b}.png'; sheet.save(out); print(out)
