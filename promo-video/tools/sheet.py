import sys, glob, os
from PIL import Image, ImageDraw
d = sys.argv[1]
files = sorted(glob.glob(f"{d}/t*.jpg"), key=lambda f: float(os.path.basename(f)[1:-4].replace("_", ".")))
for n in range(0, len(files), 4):
    imgs = [Image.open(f) for f in files[n:n+4]]
    w, h = imgs[0].size
    sheet = Image.new("RGB", (w * 2, h * 2), "white")
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % 2) * w, (i // 2) * h))
        ImageDraw.Draw(sheet).text(((i % 2) * w + 10, (i // 2) * h + 10), os.path.basename(files[n+i]), fill="yellow")
    sheet.save(f"{d}/sheet{n//4}.jpg", quality=85)
    print(f"{d}/sheet{n//4}.jpg")
