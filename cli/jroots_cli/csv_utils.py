import csv
from pathlib import Path

from .api_client import calculate_sha512

IMAGES_REQUIRED_COLUMNS = {"path", "image_key", "image_source_id", "image_path"}
OBJECTS_REQUIRED_COLUMNS = {"path", "text_content"}


def read_csv(filepath: str) -> list[dict]:
    with open(filepath, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_images_csv(filepath: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    rows = read_csv(filepath)

    if not rows:
        errors.append(f"Images CSV is empty: {filepath}")
        return rows, errors

    missing = IMAGES_REQUIRED_COLUMNS - set(rows[0].keys())
    if missing:
        errors.append(f"Images CSV missing columns: {', '.join(sorted(missing))}")
        return rows, errors

    for i, row in enumerate(rows, start=2):
        path = Path(row["path"])
        if not path.exists():
            errors.append(f"Row {i}: image file not found: {path}")

    return rows, errors


def validate_objects_csv(
    filepath: str, images_csv: str | None = None
) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    rows = read_csv(filepath)

    if not rows:
        errors.append(f"Objects CSV is empty: {filepath}")
        return rows, errors

    missing = OBJECTS_REQUIRED_COLUMNS - set(rows[0].keys())
    if missing:
        errors.append(f"Objects CSV missing columns: {', '.join(sorted(missing))}")
        return rows, errors

    if images_csv:
        image_rows = read_csv(images_csv)
        image_paths = {row["path"] for row in image_rows}
        for i, row in enumerate(rows, start=2):
            if row["path"] not in image_paths:
                errors.append(
                    f"Row {i}: object references image not in images CSV: {row['path']}"
                )

    return rows, errors


def build_image_map(images_csv: str) -> dict[str, str]:
    """Build a path -> sha512 map by hashing local image files."""
    image_map: dict[str, str] = {}
    rows = read_csv(images_csv)
    for row in rows:
        path = Path(row["path"])
        if path.exists():
            image_map[str(path)] = calculate_sha512(path)
    return image_map
