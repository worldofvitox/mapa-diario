from PIL import Image

# 1. Open your original high-res image
img_path = "image_469bff.png"
try:
    img = Image.open(img_path)
except FileNotFoundError:
    print(f"❌ Could not find {img_path}")
    exit()

width, height = img.size

# 2. Calculate the crop to remove the excess blue on the sides
# Since we need a perfect square for favicons, we will crop the width to match the height
# This naturally cuts off the wide blue margins on the left and right.
if width > height:
    left = (width - height) / 2
    top = 0
    right = (width + height) / 2
    bottom = height
else:
    # If it's already square or taller than wide, adjust accordingly
    left = 0
    top = (height - width) / 2
    right = width
    bottom = (height + width) / 2

print("✂️ Cropping image to a perfect square...")
img_square = img.crop((left, top, right, bottom))

# 3. Generate the specific modern sizes
sizes = {
    "apple-touch-icon.png": (180, 180),
    "favicon-32x32.png": (32, 32),
    "favicon-16x16.png": (16, 16)
}

for filename, size in sizes.items():
    resized_img = img_square.resize(size, Image.Resampling.LANCZOS)
    resized_img.save(filename)
    print(f"✅ Generated {filename} ({size[0]}x{size[1]})")

# 4. Generate the legacy .ico file (which actually contains multiple sizes inside it)
img_square.save("favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print("✅ Generated legacy favicon.ico")

print("🎉 All icons successfully created! You can now push these to GitHub.")