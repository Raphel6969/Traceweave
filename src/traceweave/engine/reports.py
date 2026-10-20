import json
from html import escape
from typing import Any
from .pipeline import AnalysisResult


def _payload(result: AnalysisResult | dict[str, Any]) -> dict[str, Any]:
    return result if isinstance(result, dict) else result.as_dict()


def json_report(result: AnalysisResult | dict[str, Any], *, indent=None) -> str:
    return json.dumps(_payload(result), sort_keys=True, indent=indent, default=str)


def html_report(result: AnalysisResult | dict[str, Any]) -> str:
    payload = _payload(result)
    title = escape(str(payload.get("title", "TraceWeave report")))
    claims = payload.get("claims", [])
    gaps = payload.get("gaps", [])
    contradictions = payload.get("contradictions", [])
    rows = "".join(
        f"<tr><td>{escape(str(c.get('claim_id', c.get('id', ''))))}</td>"
        f"<td>{escape(str(c.get('epistemic_state', '')))}</td>"
        f"<td>{escape(str(c.get('subject', '')))} {escape(str(c.get('predicate', '')))} {escape(str(c.get('object', '')))}</td></tr>"
        for c in claims
    )
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;background:#0b0d10;color:#e8e6e1}}table{{width:100%;border-collapse:collapse}}td,th{{border-bottom:1px solid #394047;padding:10px;text-align:left}}.Observed{{color:#f2c46d}}.Inferred{{color:#6fd3e8}}.Unknown{{color:#8b7fb8}}li{{margin:8px 0}}</style></head>
<body><h1>{title}</h1><p>Chain valid: <strong>{escape(str(payload.get('chain_valid', 'unknown')))}</strong></p>
<h2>Claims</h2><table><thead><tr><th>ID</th><th>State</th><th>Statement</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Contradictions</h2><ul>{''.join(f'<li>{escape(str(x))}</li>' for x in contradictions) or '<li>None detected.</li>'}</ul>
<h2>Evidence gaps</h2><ul>{''.join(f'<li>{escape(str(x))}</li>' for x in gaps) or '<li>None detected.</li>'}</ul>
<details><summary>Structured report</summary><pre>{escape(json_report(payload, indent=2))}</pre></details></body></html>"""
