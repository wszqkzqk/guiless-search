import json


def parse_js(data) -> list[dict]:
    """Safely parse the return value of a JS runJavaScript call.

    PySide6 runJavaScript cannot marshal complex JS objects, so the JS side
    returns a JSON string which we parse here.  If Qt already marshalled it
    as a list (shouldn't happen with our JSON.stringify approach, but safe
    to handle), we pass it through.
    """
    if isinstance(data, str) and data:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            pass
    if isinstance(data, list):
        return data
    return []


def format_results_markdown(results: list[dict]) -> str:
    """Render search results to concise Markdown for MCP text output."""
    if not results:
        return "No results found."

    lines: list[str] = []
    for idx, item in enumerate(results, 1):
        title = (item.get("title") or "").strip() or "(untitled)"
        link = (item.get("link") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        snippet = " ".join(snippet.split())

        if link:
            lines.append(f"{idx}. [{title}]({link})")
        else:
            lines.append(f"{idx}. {title}")
        if snippet:
            lines.append(f"   * snippet: {snippet}")
        lines.append("")

    return "\n".join(lines).strip()
