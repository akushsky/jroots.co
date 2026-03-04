from pathlib import Path

import click
from tqdm import tqdm

from ..api_client import calculate_sha512
from ..csv_utils import (
    build_image_map,
    read_csv,
    validate_images_csv,
    validate_objects_csv,
)
from ..reporter import Reporter

_PBAR_FMT = (
    "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}] {postfix}"
)


def _process_images(client, rows, pbar) -> tuple[dict[str, str], Reporter]:
    image_map: dict[str, str] = {}
    reporter = Reporter()
    pbar.reset(total=len(rows))
    pbar.set_description("Uploading images")

    for row in rows:
        path = Path(row["path"])
        pbar.set_postfix_str(f"File: {path.name}", refresh=True)

        if not path.exists():
            reporter.add_error(f"Image file not found: {path}")
            pbar.update(1)
            continue

        sha512 = calculate_sha512(path)
        try:
            client.upload_image(
                path=path,
                image_key=row["image_key"],
                image_source_id=row["image_source_id"],
                image_path=row["image_path"],
                sha512=sha512,
            )
            image_map[str(path)] = sha512
            reporter.add_success()
        except Exception as e:
            reporter.add_error(f"Failed to upload {path.name}: {e}")

        pbar.update(1)

    return image_map, reporter


def _process_objects(client, rows, image_map, pbar) -> Reporter:
    reporter = Reporter()
    pbar.reset(total=len(rows))
    pbar.set_description("Uploading search objects")

    for row in rows:
        path = row["path"]
        pbar.set_postfix_str(f"Object for: {Path(path).name}", refresh=True)

        sha512 = image_map.get(path)
        if not sha512:
            reporter.add_error(
                f"Skipped — image not uploaded or missing: {path}"
            )
            pbar.update(1)
            continue

        try:
            client.upload_object(
                sha512=sha512,
                text_content=row["text_content"],
                price=row["price"],
            )
            reporter.add_success()
        except Exception as e:
            reporter.add_error(f"Failed to create object for {Path(path).name}: {e}")

        pbar.update(1)

    return reporter


def _run_validation(images_csv, objects_csv) -> bool:
    """Run pre-upload validation. Returns True if valid."""
    errors: list[str] = []

    if images_csv:
        _, img_errors = validate_images_csv(images_csv)
        errors.extend(img_errors)

    if objects_csv:
        _, obj_errors = validate_objects_csv(objects_csv, images_csv)
        errors.extend(obj_errors)

    if errors:
        click.secho(f"\nValidation found {len(errors)} issue(s):", fg="yellow")
        for err in errors:
            click.echo(f"  - {err}")
        return False

    click.secho("✔ Validation passed.", fg="green")
    return True


@click.command("upload-images")
@click.option(
    "--csv",
    "images_csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with image metadata.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate without uploading.")
@click.pass_context
def upload_images(ctx, images_csv, dry_run):
    """Upload images from a CSV file."""
    if dry_run:
        _run_validation(images_csv, None)
        return

    rows = read_csv(images_csv)
    with tqdm(total=1, unit="row", bar_format=_PBAR_FMT) as pbar:
        _, reporter = _process_images(ctx.obj.client, rows, pbar)

    click.secho("\n--- Upload Summary ---", bold=True)
    reporter.report("Image")


@click.command("upload-objects")
@click.option(
    "--csv",
    "objects_csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with search objects.",
)
@click.option(
    "--images-csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Images CSV (used to compute sha512 hashes for linking).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate without uploading.")
@click.pass_context
def upload_objects(ctx, objects_csv, images_csv, dry_run):
    """Upload search objects from a CSV file."""
    if dry_run:
        _run_validation(images_csv, objects_csv)
        return

    click.echo("Computing image hashes...")
    image_map = build_image_map(images_csv)
    rows = read_csv(objects_csv)

    with tqdm(total=1, unit="row", bar_format=_PBAR_FMT) as pbar:
        reporter = _process_objects(ctx.obj.client, rows, image_map, pbar)

    click.secho("\n--- Upload Summary ---", bold=True)
    reporter.report("Search Object")


@click.command("upload-all")
@click.option(
    "--images-csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with image metadata.",
)
@click.option(
    "--objects-csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with search objects.",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate CSVs without uploading.")
@click.pass_context
def upload_all(ctx, images_csv, objects_csv, dry_run):
    """Upload all images and their related search objects from two CSVs."""
    if dry_run:
        _run_validation(images_csv, objects_csv)
        return

    click.secho("Starting bulk upload process...", fg="cyan")

    image_rows = read_csv(images_csv)
    object_rows = read_csv(objects_csv)

    with tqdm(total=1, unit="row", bar_format=_PBAR_FMT) as pbar:
        image_map, image_reporter = _process_images(ctx.obj.client, image_rows, pbar)
        pbar.set_postfix_str("Image processing complete.")

        object_reporter = _process_objects(ctx.obj.client, object_rows, image_map, pbar)
        pbar.set_postfix_str("Object processing complete.")

    click.secho("\n--- Upload Summary ---", bold=True)
    image_reporter.report("Image")
    object_reporter.report("Search Object")
