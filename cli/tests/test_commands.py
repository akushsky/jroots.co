from unittest.mock import patch

import requests
import responses

from jroots_cli.main import cli

API = "http://localhost:8000"


# --- CLI group ---


def test_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "CLI tools" in result.output
    assert "upload-all" in result.output
    assert "validate" in result.output
    assert "login" in result.output
    assert "status" in result.output


def test_warns_when_no_token(runner):
    result = runner.invoke(cli, ["validate", "--help"])
    assert "Warning" in result.output


def test_no_warning_for_login(runner):
    result = runner.invoke(cli, ["login", "--help"])
    assert "Warning" not in result.output


def test_no_warning_for_status(runner):
    result = runner.invoke(cli, ["status", "--help"])
    assert "Warning" not in result.output


def test_custom_api_url(runner):
    result = runner.invoke(
        cli, ["--api-url", "https://custom.api", "--token", "t", "status", "--help"]
    )
    assert result.exit_code == 0


# --- status ---


@responses.activate
def test_status_shows_config_and_ping_ok(runner):
    responses.add(responses.GET, f"{API}/", status=200)
    result = runner.invoke(cli, ["--token", "fake", "status"])
    assert result.exit_code == 0
    assert "API URL: http://localhost:8000" in result.output
    assert "Token:   set" in result.output
    assert "SSL:     verified" in result.output
    assert "OK" in result.output


@responses.activate
def test_status_ping_failure(runner):
    responses.add(responses.GET, f"{API}/", body=requests.ConnectionError())
    result = runner.invoke(cli, ["--token", "fake", "status"])
    assert "FAILED" in result.output


# --- validate ---


def test_validate_requires_at_least_one_csv(runner):
    result = runner.invoke(cli, ["--token", "fake", "validate"])
    assert "Provide at least one" in result.output


def test_validate_valid_images_csv(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        cli, ["--token", "fake", "validate", "--images-csv", str(csv_file)]
    )
    assert "All validations passed" in result.output


def test_validate_invalid_images_csv(runner, tmp_path):
    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        "path,image_key,image_source_id,image_path\nmissing.jpg,key,1,p\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        cli, ["--token", "fake", "validate", "--images-csv", str(csv_file)]
    )
    assert "issue(s)" in result.output


def test_validate_cross_reference(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        "path,text_content,price\nother.jpg,Name,5000\n", encoding="utf-8"
    )
    result = runner.invoke(
        cli,
        [
            "--token", "fake", "validate",
            "--images-csv", str(img_csv),
            "--objects-csv", str(obj_csv),
        ],
    )
    assert "issue(s)" in result.output
    assert "other.jpg" in result.output


# --- login ---


@responses.activate
def test_login_success(runner):
    responses.add(
        responses.POST, f"{API}/api/login",
        json={"access_token": "test_token_123"}, status=200,
    )
    result = runner.invoke(cli, ["login", "admin"], input="password\n")
    assert result.exit_code == 0
    assert "export JROOTS_API_TOKEN=test_token_123" in result.output


@responses.activate
def test_login_bad_credentials(runner):
    responses.add(
        responses.POST, f"{API}/api/login",
        json={"detail": "Bad credentials"}, status=401,
    )
    result = runner.invoke(cli, ["login", "admin"], input="wrong\n")
    assert result.exit_code != 0
    assert "Login failed" in result.output


@responses.activate
def test_login_connection_error(runner):
    responses.add(
        responses.POST, f"{API}/api/login",
        body=requests.ConnectionError(),
    )
    with patch("time.sleep"):
        result = runner.invoke(cli, ["login", "admin"], input="pass\n")
    assert result.exit_code != 0
    assert "Connection Error" in result.output


# --- upload-all --dry-run ---


def test_upload_all_dry_run_passes_when_valid(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        f"path,text_content,price\n{img},Name,5000\n", encoding="utf-8"
    )
    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-all",
            "--images-csv", str(img_csv),
            "--objects-csv", str(obj_csv),
            "--dry-run",
        ],
    )
    assert "Validation passed" in result.output


def test_upload_all_dry_run_reports_errors(runner, tmp_path):
    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        "path,image_key,image_source_id,image_path\nmissing.jpg,key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        "path,text_content,price\nmissing.jpg,Name,5000\n", encoding="utf-8"
    )
    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-all",
            "--images-csv", str(img_csv),
            "--objects-csv", str(obj_csv),
            "--dry-run",
        ],
    )
    assert "issue(s)" in result.output


# --- upload-all (actual upload) ---


@responses.activate
def test_upload_all_uploads_images_and_objects(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"image-data")

    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        f"path,text_content,price\n{img},Name,5000\n", encoding="utf-8"
    )

    responses.add(
        responses.POST, f"{API}/api/admin/images", json={"id": 1}, status=200
    )
    responses.add(
        responses.POST, f"{API}/api/admin/objects", json={"id": 1}, status=200
    )

    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-all",
            "--images-csv", str(img_csv),
            "--objects-csv", str(obj_csv),
        ],
    )
    assert result.exit_code == 0
    assert "1 image operation(s)" in result.output
    assert "1 search object operation(s)" in result.output
    assert len(responses.calls) == 2


@responses.activate
def test_upload_all_reports_api_error(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"image-data")

    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        f"path,text_content,price\n{img},Name,5000\n", encoding="utf-8"
    )

    responses.add(
        responses.POST, f"{API}/api/admin/images",
        json={"detail": "forbidden"}, status=403,
    )

    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-all",
            "--images-csv", str(img_csv),
            "--objects-csv", str(obj_csv),
        ],
    )
    assert "error(s)" in result.output
    assert "Failed to upload" in result.output


# --- upload-images ---


@responses.activate
def test_upload_images(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )

    responses.add(
        responses.POST, f"{API}/api/admin/images", json={"id": 1}, status=200
    )

    result = runner.invoke(
        cli, ["--token", "fake", "upload-images", "--csv", str(csv_file)]
    )
    assert result.exit_code == 0
    assert "1 image operation(s)" in result.output


def test_upload_images_dry_run(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    csv_file = tmp_path / "images.csv"
    csv_file.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli,
        ["--token", "fake", "upload-images", "--csv", str(csv_file), "--dry-run"],
    )
    assert "Validation passed" in result.output


# --- upload-objects ---


@responses.activate
def test_upload_objects(runner, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"data")

    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        f"path,image_key,image_source_id,image_path\n{img},key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        f"path,text_content,price\n{img},Name,5000\n", encoding="utf-8"
    )

    responses.add(
        responses.POST, f"{API}/api/admin/objects", json={"id": 1}, status=200
    )

    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-objects",
            "--csv", str(obj_csv),
            "--images-csv", str(img_csv),
        ],
    )
    assert result.exit_code == 0
    assert "1 search object operation(s)" in result.output


@responses.activate
def test_upload_objects_skips_missing_image(runner, tmp_path):
    img_csv = tmp_path / "images.csv"
    img_csv.write_text(
        "path,image_key,image_source_id,image_path\nmissing.jpg,key,1,p\n",
        encoding="utf-8",
    )
    obj_csv = tmp_path / "objects.csv"
    obj_csv.write_text(
        "path,text_content,price\nmissing.jpg,Name,5000\n", encoding="utf-8"
    )

    result = runner.invoke(
        cli,
        [
            "--token", "fake", "upload-objects",
            "--csv", str(obj_csv),
            "--images-csv", str(img_csv),
        ],
    )
    assert "not uploaded or missing" in result.output
