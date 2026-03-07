import sys

import click
import requests


@click.command(help="Log in to the API to get a session token.")
@click.argument("username")
@click.option(
    "--password", "-p",
    envvar="JROOTS_PASSWORD",
    default=None,
    help="Password (or set JROOTS_PASSWORD env var). Prompts interactively if omitted.",
)
@click.pass_context
def login(ctx, username, password):
    obj = ctx.obj

    if not password:
        password = click.prompt("Password", hide_input=True, err=True)

    try:
        click.echo(
            f"Attempting to log in {username} at {obj.api_base}...", err=True
        )

        result = obj.client.login(username, password)
        token = result.get("access_token")

        if token:
            click.secho("\n✔ Login Successful!", fg="green", err=True)
            click.echo(
                "Run the command below to set the token in your current session:",
                err=True,
            )
            click.echo(f"export JROOTS_API_TOKEN={token}")
        else:
            click.secho(
                "Login succeeded but the server did not return a token.",
                fg="yellow",
                err=True,
            )

    except requests.exceptions.HTTPError as e:
        msg = f"Login failed: {e.response.status_code} {e.response.reason}"
        try:
            detail = e.response.json().get("detail", "No details provided.")
            msg += f"\n    Server said: {detail}"
        except (requests.exceptions.JSONDecodeError, ValueError):
            pass
        click.secho(msg, fg="red", err=True)
        sys.exit(1)

    except requests.exceptions.ConnectionError:
        click.secho(
            f"Connection Error: Could not connect to {obj.api_base}.",
            fg="red",
            err=True,
        )
        click.echo(
            "Please check that the server is running and the API URL is correct.",
            err=True,
        )
        sys.exit(1)

    except requests.RequestException as e:
        click.secho(f"Unexpected network error: {e}", fg="red", err=True)
        sys.exit(1)
