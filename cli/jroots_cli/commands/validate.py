import click

from ..csv_utils import validate_images_csv, validate_objects_csv


@click.command()
@click.option(
    "--images-csv",
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with image metadata.",
)
@click.option(
    "--objects-csv",
    type=click.Path(exists=True, dir_okay=False),
    help="CSV file with search objects.",
)
@click.pass_context
def validate(ctx, images_csv, objects_csv):
    """Validate CSV files without uploading anything."""
    if not images_csv and not objects_csv:
        click.secho("Provide at least one CSV file to validate.", fg="red")
        ctx.exit(1)
        return

    errors: list[str] = []

    if images_csv:
        click.echo(f"Validating images CSV: {images_csv}")
        _, img_errors = validate_images_csv(images_csv)
        errors.extend(img_errors)

    if objects_csv:
        click.echo(f"Validating objects CSV: {objects_csv}")
        _, obj_errors = validate_objects_csv(objects_csv, images_csv)
        errors.extend(obj_errors)

    if errors:
        click.secho(f"\n✗ Found {len(errors)} issue(s):", fg="red")
        for err in errors:
            click.echo(f"  - {err}")
        ctx.exit(1)
    else:
        click.secho("\n✔ All validations passed.", fg="green")
