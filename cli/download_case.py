import requests
import json
import urllib.parse
import os

filename = "File:ДАЖО 680-1-4. 1909. Раскладка суспільного податку з євреїв ремісників Бердичівського (посімейні списки).pdf"

def download_commons_file(filename, output_path):
    # Get imageinfo
    url = f"https://commons.wikimedia.org/w/api.php?action=query&titles={urllib.parse.quote(filename)}&prop=imageinfo&iiprop=url&format=json"
    headers = {'User-Agent': 'jroots-bot/1.0 (michael.akushsky@gmail.com)'}
    
    print(f"Fetching URL for {filename}...")
    r = requests.get(url, headers=headers)
    data = r.json()
    
    pages = data.get('query', {}).get('pages', {})
    for page_id, page_info in pages.items():
        if 'imageinfo' in page_info:
            file_url = page_info['imageinfo'][0]['url']
            print(f"Downloading from {file_url}...")
            
            # Streaming download
            with requests.get(file_url, headers=headers, stream=True) as r_down:
                r_down.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in r_down.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"Saved to {output_path}")
            return
            
    print("File URL not found")

if __name__ == "__main__":
    os.makedirs("cli/dazho_downloads", exist_ok=True)
    download_commons_file(filename, "cli/dazho_downloads/680-1-4.pdf")
