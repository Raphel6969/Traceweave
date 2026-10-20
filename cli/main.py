"""Analyze local files and emit TraceWeave reports."""
from __future__ import annotations
import json
from pathlib import Path
import typer
from api.app import _build_case
app = typer.Typer(help="Analyze evidence files with TraceWeave.")
@app.callback()
def root() -> None:
    """TraceWeave local analysis commands."""
    pass
@app.command()
def analyze(input_dir: Path = typer.Argument(..., exists=True, file_okay=False), output: Path = typer.Option(Path("traceweave-report.json"), "--output", "-o"), format: str = typer.Option("json", "--format")) -> None:
    """Analyze every regular file in INPUT_DIR."""
    files = [(p.name, p.read_bytes()) for p in sorted(input_dir.iterdir()) if p.is_file()]; case = _build_case(files); output.parent.mkdir(parents=True, exist_ok=True)
    if format == "json": output.write_text(json.dumps(case, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    elif format == "html":
        from html import escape
        items = "".join("<li>" + escape(str(x)) + "</li>" for x in case["timeline"])
        output.write_text(f"<!doctype html><html><body><h1>TraceWeave report {case['id']}</h1><ul>{items}</ul></body></html>", encoding="utf-8")
    else: raise typer.BadParameter("format must be json or html")
    typer.echo(str(output))
if __name__ == "__main__": app()
