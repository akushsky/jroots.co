import hashlib

from jroots_cli.csv_utils import (
    build_image_map,
    read_csv,
    validate_images_csv,
    validate_objects_csv,
)


# --- read_csv ---


def test_read_csv(tmp_path):
    f = tmp_path / "test.csv"
    f.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")
    rows = read_csv(str(f))
    assert len(rows) == 2
    assert rows[0] == {"name": "Alice", "age": "30"}


def test_read_csv_headers_only(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("name,age\n", encoding="utf-8")
    assert read_csv(str(f)) == []


# --- validate_images_csv ---


def test_validate_images_valid(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"fake")

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    rows, errors = validate_images_csv(str(csv_file))
    assert len(rows) == 1
    assert errors == []


def test_validate_images_empty(tmp_path):
    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        "path,image_key,image_source_id,image_path\n", encoding="utf-8"
    )
    _, errors = validate_images_csv(str(csv_file))
    assert any("empty" in e.lower() for e in errors)


def test_validate_images_missing_columns(tmp_path):
    csv_file = tmp_path / "images.csv"
    csv_file.write_text("path,image_key\nimg.jpg,key\n", encoding="utf-8")
    _, errors = validate_images_csv(str(csv_file))
    assert any("missing columns" in e.lower() for e in errors)


def test_validate_images_missing_file(tmp_path):
    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        "path,image_key,image_source_id,image_path\nnonexistent.jpg,key,1,p\n",
        encoding="utf-8",
    )
    _, errors = validate_images_csv(str(csv_file))
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_validate_images_multiple_missing_files(tmp_path):
    existing = tmp_path / "exists.jpg"
    existing.write_bytes(b"ok")

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n"
        f"{existing},key,1,p\n"
        f"missing1.jpg,key,1,p\n"
        f"missing2.jpg,key,1,p\n",
        encoding="utf-8",
    )
    rows, errors = validate_images_csv(str(csv_file))
    assert len(rows) == 3
    assert len(errors) == 2


# --- validate_objects_csv ---


def test_validate_objects_valid(tmp_path):
    csv_file = tmp_path / "objects.csv"
    csv_file.write_text(
        "path,text_content,price\nimg.jpg,Name,5000\n", encoding="utf-8"
    )
    rows, errors = validate_objects_csv(str(csv_file))
    assert len(rows) == 1
    assert errors == []


def test_validate_objects_empty(tmp_path):
    csv_file = tmp_path / "objects.csv"
    csv_file.write_text("path,text_content,price\n", encoding="utf-8")
    _, errors = validate_objects_csv(str(csv_file))
    assert any("empty" in e.lower() for e in errors)


def test_validate_objects_missing_columns(tmp_path):
    csv_file = tmp_path / "objects.csv"
    csv_file.write_text("path\nimg.jpg\n", encoding="utf-8")
    _, errors = validate_objects_csv(str(csv_file))
    assert any("missing columns" in e.lower() for e in errors)


def test_validate_objects_cross_reference_finds_mismatch(tmp_path):
    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        "path,image_key,image_source_id,image_path\nimg1.jpg,key,1,p\n",
        encoding="utf-8",
    )

    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        "path,text_content,price\nimg1.jpg,Name1,5000\nimg2.jpg,Name2,5000\n",
        encoding="utf-8",
    )

    _, errors = validate_objects_csv(str(obj_csv), str(img_csv))
    assert len(errors) == 1
    assert "img2.jpg" in errors[0]


def test_validate_objects_no_cross_reference_by_default(tmp_path):
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        "path,text_content,price\nany.jpg,Name,5000\n", encoding="utf-8"
    )
    _, errors = validate_objects_csv(str(obj_csv))
    assert errors == []


# --- build_image_map ---


def test_build_image_map(tmp_path):
    img = tmp_path / "img.jpg"
    content = b"test-image-content"
    img.write_bytes(content)

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )

    image_map = build_image_map(str(csv_file))
    assert image_map[str(img)] == hashlib.sha512(content).hexdigest()


def test_build_image_map_skips_missing_files(tmp_path):
    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        "path,image_key,image_source_id,image_path\nnonexistent.jpg,key,1,p\n",
        encoding="utf-8",
    )
    assert build_image_map(str(csv_file)) == {}
