import click


@click.command()
@click.pass_context
def sources(ctx):
    """List image sources (archives) from the API."""
    try:
        data = ctx.obj.client.list_sources()
    except Exception as e:
        click.secho(f"Error: {e}", fg="red")
        return

    if not data:
        click.echo("No sources found.")
        return

    click.secho(f"{'ID':>4}  {'Code':<12} Description", bold=True)
    click.echo("-" * 60)
    for s in data:
        sid = s.get("id", "?")
        name = s.get("source_name", "?")
        desc = s.get("description", "")
        click.echo(f"{sid:>4}  {name:<12} {desc}")
