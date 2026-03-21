from pdf2image import convert_from_path
import os

pdf_path = "cli/dazho_downloads/680-1-4.pdf"
out_dir = "cli/dazho_downloads/680-1-4_pages"

os.makedirs(out_dir, exist_ok=True)

print("Converting first 20 pages...")
# We can use first_page and last_page parameters
images = convert_from_path(pdf_path, first_page=1, last_page=20, dpi=200)

for i, img in enumerate(images):
    page_num = i + 1
    out_path = os.path.join(out_dir, f"page_{page_num:03d}.png")
    img.save(out_path, "PNG")
    print(f"Saved {out_path}")

print("Done")
