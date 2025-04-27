import csv
import hashlib
import os
from pathlib import Path

import click
import requests
from tqdm import tqdm

API_BASE = os.getenv("JROOTS_API", "http://localhost:8000")
TOKEN = os.getenv("JROOTS_API_TOKEN")

HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def image_key_reference(image_key: str, image_source_id: int) -> str:
    return f"{image_key}|{image_source_id}"


def calculate_sha512(path: Path) -> str:
    h = hashlib.sha512()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


@click.group(
    context_settings={
        "max_content_width": 120,
    }
)
def cli():
    pass


@cli.command()
@click.option("--images-csv", required=True, type=click.Path(exists=True), help="CSV file with image metadata")
@click.option("--objects-csv", required=True, type=click.Path(exists=True), help="CSV file with search objects")
def upload_all(images_csv, objects_csv):
    """Upload all images and their related search objects from two CSVs."""
    image_map = {}

    # Upload images
    with open(images_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="Uploading images"):
            path = Path(row['path'])
            if not path.exists():
                click.echo(f"[!] Image not found: {path}")
                continue

            sha512 = calculate_sha512(path)
            files = {"image_file": open(path, "rb")}
            data = {
                "image_key": row['image_key'],
                "image_source_id": row['image_source_id'],
                "image_path": row['image_path'],
                "image_file_sha512": sha512
            }
            try:
                response = requests.post(f"{API_BASE}/api/admin/images", files=files, data=data, headers=HEADERS)
                response.raise_for_status()
                image_map[str(path)] = sha512
            except requests.RequestException as e:
                click.echo(f"[!] Failed to upload {path.name}: {e}")

    # Upload search objects
    with open(objects_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="Uploading search objects"):
            path = Path(row['path'])
            sha512 = image_map.get(str(path))
            if not sha512:
                click.echo(f"[!] Skipping search object — image not found or not uploaded: {path}")
                continue

            data = {
                "image_file_sha512": sha512,
                "text_content": row['text_content']
            }
            try:
                response = requests.post(f"{API_BASE}/api/admin/objects", data=data, headers=HEADERS)
                response.raise_for_status()
            except requests.RequestException as e:
                click.echo(f"[!] Failed to create search object for image {path.name}: {e}")


@cli.command()
@click.argument("username")
@click.argument("password")
def login(username, password):
    """Log in to the API and print export command for session token."""
    try:
        response = requests.post(f"{API_BASE}/api/admin/login", data={"username": username, "password": password})
        response.raise_for_status()
        token = response.json().get("access_token")
        if token:
            click.echo(f"export JROOTS_API_TOKEN={token}")
        else:
            click.echo("[!] Login succeeded but no token returned.")
    except requests.RequestException as e:
        click.echo(f"[!] Login failed: {e}")


if __name__ == "__main__":
    cli()
