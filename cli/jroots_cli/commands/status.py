import click


@click.command()
@click.pass_context
def status(ctx):
    """Check API connectivity and authentication status."""
    obj = ctx.obj

    click.echo(f"API URL: {obj.api_base}")
    click.echo(f"Token:   {'set' if obj.token else 'not set'}")
    click.echo(f"SSL:     {'verified' if obj.session.verify else 'not verified'}")

    click.echo("\nPinging API... ", nl=False)
    if obj.client.ping():
        click.secho("OK", fg="green")
    else:
        click.secho("FAILED", fg="red")
