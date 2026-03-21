import os
from pathlib import Path
from google import genai
from google.genai import types

def main():
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    image_path = Path("cli/dazho_downloads/680-1-4_pages/page_004.png")
    
    prompt = """
    This is a page from a 1909 ledger of Jewish craftsmen in Berdychiv.
    Please transcribe the table on this page as a markdown table.
    Include the column headers if they are visible, otherwise just infer them based on the content (e.g. Number, Name, Tax Amount).
    Only output the markdown table, nothing else.
    """
    
    print("Calling Gemini...")
    resp = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            types.Content(parts=[
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/png"),
                types.Part.from_text(text=prompt),
            ])
        ],
    )
    
    print("Response:")
    print(resp.text)

if __name__ == "__main__":
    main()
