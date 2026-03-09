import click
import requests
import urllib3

from .api_client import ApiClient
from .commands.login import login
from .commands.sources import sources
from .commands.status import status
from .commands.upload import upload_all, upload_images, upload_objects
from .commands.validate import validate


class JRootsContext:
    def __init__(
        self,
        api_base: str,
        token: str | None,
        verify_ssl: bool,
        verbose: bool,
    ):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.verbose = verbose
        self.session = requests.Session()
        self.session.verify = verify_ssl
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.client = ApiClient(self.session, self.api_base)


@click.group(context_settings={"max_content_width": 120})
@click.option(
    "--api-url",
    envvar="JROOTS_API_URL",
    default="http://localhost:8000",
    show_default=True,
    help="Base URL of the JRoots API.",
)
@click.option(
    "--token",
    envvar="JROOTS_API_TOKEN",
    default=None,
    help="Bearer token for authentication.",
)
@click.option(
    "--no-verify-ssl",
    is_flag=True,
    default=False,
    help="Disable SSL certificate verification.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output.",
)
@click.pass_context
def cli(ctx, api_url, token, no_verify_ssl, verbose):
    """CLI tools for interacting with the JRoots API."""
    ctx.ensure_object(dict)
    ctx.obj = JRootsContext(api_url, token, not no_verify_ssl, verbose)

    if not token and ctx.invoked_subcommand not in ("login", "status"):
        click.secho(
            "Warning: No API token set. Use 'jroots login' or set JROOTS_API_TOKEN.",
            fg="yellow",
            err=True,
        )


cli.add_command(login)
cli.add_command(sources)
cli.add_command(status)
cli.add_command(upload_all)
cli.add_command(upload_images)
cli.add_command(upload_objects)
cli.add_command(validate)


if __name__ == "__main__":
    cli()
