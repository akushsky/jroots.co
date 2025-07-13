import csv
import hashlib
import os
import sys
from pathlib import Path

import click
import requests
from tqdm import tqdm

# --- Configuration ---
API_BASE = os.getenv("JROOTS_API", "http://localhost:5173")
TOKEN = os.getenv("JROOTS_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

# --- Helper Class for Structured Reporting ---

class Reporter:
    """A helper to collect and report errors and successes neatly."""
    def __init__(self):
        self.errors = []
        self.success_count = 0

    def add_error(self, message: str):
        self.errors.append(message)

    def add_success(self):
        self.success_count += 1

    def report(self, task_name: str):
        """Prints a final summary report."""
        if self.errors:
            click.secho(f"\n{task_name} completed with {len(self.errors)} errors:", fg="yellow")
            for error in self.errors:
                click.echo(f"  - {error}")
        if self.success_count > 0:
            click.secho(f"\n✔ Successfully completed {self.success_count} {task_name.lower()} operations.", fg="green")
        elif not self.errors:
            click.secho(f"No new operations were performed for {task_name.lower()}.", fg="blue")


# --- Core Logic ---

def calculate_sha512(path: Path) -> str:
    """Calculates the SHA512 hash of a file."""
    h = hashlib.sha512()
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def process_images(images_csv: str, main_pbar: tqdm) -> (dict, Reporter):
    """Processes and uploads images from a CSV file."""
    image_map = {}
    reporter = Reporter()

    with open(images_csv, newline='', encoding='utf-8') as f:
        # Get total number of rows for the progress bar
        rows = list(csv.DictReader(f))
        main_pbar.reset(total=len(rows))
        main_pbar.set_description("Uploading images")

        for row in rows:
            path = Path(row['path'])
            main_pbar.set_postfix_str(f"File: {path.name}", refresh=True)

            if not path.exists():
                reporter.add_error(f"Image file not found: {path}")
                main_pbar.update(1)
                continue

            sha512 = calculate_sha512(path)
            data = {
                "image_key": row['image_key'],
                "image_source_id": row['image_source_id'],
                "image_path": row['image_path'],
                "image_file_sha512": sha512
            }
            try:
                with open(path, "rb") as image_file:
                    files = {"image_file": image_file}
                    response = requests.post(f"{API_BASE}/api/admin/images", files=files, data=data, headers=HEADERS)
                    response.raise_for_status()

                image_map[str(path)] = sha512
                reporter.add_success()

            except requests.RequestException as e:
                reporter.add_error(f"Failed to upload {path.name}: {e}")

            main_pbar.update(1)

    return image_map, reporter

def process_objects(objects_csv: str, image_map: dict, main_pbar: tqdm) -> Reporter:
    """Processes and uploads search objects from a CSV file."""
    reporter = Reporter()

    with open(objects_csv, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        main_pbar.reset(total=len(rows))
        main_pbar.set_description("Uploading search objects")

        for row in rows:
            path = Path(row['path'])
            main_pbar.set_postfix_str(f"Object for: {path.name}", refresh=True)

            sha512 = image_map.get(str(path))
            if not sha512:
                reporter.add_error(f"Skipped search object — image not found or failed to upload: {path}")
                main_pbar.update(1)
                continue

            data = {
                "image_file_sha512": sha512,
                "text_content": row['text_content'],
                "price": row['price'],
            }
            try:
                response = requests.post(f"{API_BASE}/api/admin/objects", data=data, headers=HEADERS)
                response.raise_for_status()
                reporter.add_success()
            except requests.RequestException as e:
                reporter.add_error(f"Failed to create object for {path.name}: {e}")

            main_pbar.update(1)

    return reporter

# --- Click Commands ---

@click.group(context_settings={"max_content_width": 120})
def cli():
    """A CLI tool for interacting with the JROOTS API."""
    if not TOKEN:
        click.secho("Warning: JROOTS_API_TOKEN is not set. API calls may fail.", fg="yellow")
        click.echo("Please log in using the 'login' command.")

@cli.command()
@click.option("--images-csv", required=True, type=click.Path(exists=True, dir_okay=False), help="CSV file with image metadata.")
@click.option("--objects-csv", required=True, type=click.Path(exists=True, dir_okay=False), help="CSV file with search objects.")
def upload_all(images_csv, objects_csv):
    """Upload all images and their related search objects from two CSVs."""
    click.secho("Starting bulk upload process...", fg="cyan")

    with tqdm(total=1, unit="row", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}") as main_pbar:
        # --- Stage 1: Images ---
        image_map, image_reporter = process_images(images_csv, main_pbar)
        main_pbar.set_postfix_str("Image processing complete.")

        # --- Stage 2: Objects ---
        object_reporter = process_objects(objects_csv, image_map, main_pbar)
        main_pbar.set_postfix_str("Object processing complete.")

    # --- Final Report ---
    click.secho("\n--- Upload Summary ---", bold=True)
    image_reporter.report("Image")
    object_reporter.report("Search Object")

# Your login command remains excellent, just including it here for completeness
@cli.command(help="Log in to the API to get a session token.")
@click.option(
    '--api-url',
    default=os.getenv('JROOTS_API_URL', 'http://localhost:5173'),
    help="Base URL of the API. Can also be set with JROOTS_API_URL environment variable."
)
@click.argument("username")
def login(api_url, username):
    """
    Log in to the API using a secure password prompt.
    """
    global API_BASE
    API_BASE = api_url

    try:
        password = click.prompt("Password", hide_input=True, err=True)
        login_url = f"{API_BASE}/api/login"
        click.echo(f"Attempting to log in {username} at {API_BASE}...", err=True)
        response = requests.post(login_url, data={"username": username, "password": password}, timeout=10)
        response.raise_for_status()

        token = response.json().get("access_token")

        if token:
            click.echo("\n\033[92m✔ Login Successful!\033[0m", err=True)
            click.echo("Run the command below to set the token in your current session:", err=True)
            click.echo(f"export JROOTS_API_TOKEN={token}")
        else:
            click.echo("[!] Login succeeded but the server did not return a token.", err=True)

    except requests.exceptions.HTTPError as e:
        error_message = f"[!] Login failed: {e.response.status_code} {e.response.reason}"
        try:
            detail = e.response.json().get("detail", "No details provided.")
            error_message += f"\n    Server said: {detail}"
        except requests.exceptions.JSONDecodeError:
            pass
        click.echo(error_message, err=True)
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        click.echo(f"[!] Connection Error: Could not connect to the API at {api_url}.", err=True)
        click.echo("    Please check that the server is running and the API URL is correct.", err=True)
        sys.exit(1)
    except requests.RequestException as e:
        click.echo(f"[!] An unexpected network error occurred: {e}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    cli()