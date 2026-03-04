from jroots_cli.reporter import Reporter


def test_initial_state():
    r = Reporter()
    assert r.errors == []
    assert r.success_count == 0
    assert r.skip_count == 0


def test_add_error():
    r = Reporter()
    r.add_error("something failed")
    r.add_error("another failure")
    assert len(r.errors) == 2
    assert r.errors[0] == "something failed"


def test_add_success():
    r = Reporter()
    r.add_success()
    r.add_success()
    r.add_success()
    assert r.success_count == 3


def test_add_skip():
    r = Reporter()
    r.add_skip()
    r.add_skip()
    assert r.skip_count == 2


def test_report_with_errors(capsys):
    r = Reporter()
    r.add_error("file not found")
    r.add_success()
    r.report("Upload")
    output = capsys.readouterr().out
    assert "1 error(s)" in output
    assert "file not found" in output
    assert "1 upload operation(s)" in output


def test_report_only_successes(capsys):
    r = Reporter()
    r.add_success()
    r.add_success()
    r.report("Upload")
    output = capsys.readouterr().out
    assert "2 upload operation(s)" in output
    assert "error" not in output.lower()


def test_report_with_skips(capsys):
    r = Reporter()
    r.add_success()
    r.add_skip()
    r.report("Upload")
    output = capsys.readouterr().out
    assert "1 already-existing" in output


def test_report_no_operations(capsys):
    r = Reporter()
    r.report("Upload")
    output = capsys.readouterr().out
    assert "No operations" in output
