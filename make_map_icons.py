from PIL import Image

def process_icon(input_name, output_name, make_transparent=False):
    try:
        # Open the image and convert to RGBA (adds an alpha channel for transparency)
        img = Image.open(input_name).convert("RGBA")
        
        # Resize to standard map icon size (40x40)
        img = img.resize((40, 40), Image.Resampling.LANCZOS)
        
        if make_transparent:
            # Strip white backgrounds (specifically for the Peugeot JPEG)
            datas = img.getdata()
            new_data = []
            for item in datas:
                # If pixel is very close to pure white, make it fully transparent
                if item[0] > 240 and item[1] > 240 and item[2] > 240:
                    new_data.append((255, 255, 255, 0))
                else:
                    new_data.append(item)
            img.putdata(new_data)
            
        img.save(output_name, "PNG")
        print(f"✅ Successfully created {output_name}")
    except Exception as e:
        print(f"❌ Error processing {input_name}: {e}")

if __name__ == "__main__":
    print("Processing map icons...")
    # 1. Base Logo
    process_icon("Square Logo - Chum.PNG", "base_icon.png")
    # 2. Seba's F1 Van
    process_icon("F1.svg.png", "seba_icon.png")
    # 3. Juan's Peugeot Van (with white background removal!)
    process_icon("peugeot logo.jpeg", "juan_icon.png", make_transparent=True)