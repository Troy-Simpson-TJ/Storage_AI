from PIL import Image
from pathlib import Path

# Build correct path to images folder
images_dir = Path(__file__).parent / "images"

# Open PNG from images folder
img = Image.open(images_dir / "appicon.png")

# Save ICO back into images folder
img.save(
    images_dir / "appicon.ico",
    format="ICO",
    sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)]
)

print("Icon created successfully.")
