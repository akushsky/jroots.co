import click


class Reporter:
    """Collects and reports errors and successes for a batch operation."""

    def __init__(self):
        self.errors: list[str] = []
        self.success_count: int = 0
        self.skip_count: int = 0

    def add_error(self, message: str):
        self.errors.append(message)

    def add_success(self):
        self.success_count += 1

    def add_skip(self):
        self.skip_count += 1

    def report(self, task_name: str):
        if self.errors:
            click.secho(
                f"\n{task_name} completed with {len(self.errors)} error(s):",
                fg="yellow",
            )
            for error in self.errors:
                click.echo(f"  - {error}")
        if self.success_count > 0:
            click.secho(
                f"\n✔ Successfully completed {self.success_count} {task_name.lower()} operation(s).",
                fg="green",
            )
        if self.skip_count > 0:
            click.secho(
                f"  Skipped {self.skip_count} already-existing item(s).",
                fg="blue",
            )
        if self.success_count == 0 and self.skip_count == 0 and not self.errors:
            click.secho(
                f"No operations were performed for {task_name.lower()}.",
                fg="blue",
            )
