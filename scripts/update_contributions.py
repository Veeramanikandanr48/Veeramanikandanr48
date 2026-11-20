#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

MARKER_START = "<!-- CONTRIBUTIONS:START -->"
MARKER_END = "<!-- CONTRIBUTIONS:END -->"
USERNAME = os.environ.get("GITHUB_USERNAME", "Veeramanikandanr48")
README_PATH = os.environ.get("README_PATH", "README.md")
MAX_MERGED = int(os.environ.get("MAX_MERGED", "200"))
MAX_OPEN = int(os.environ.get("MAX_OPEN", "200"))


def run(cmd):
    return subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace")


def fetch_all_prs():
    items = []
    page = 1
    while True:
        out = run([
            "gh", "api", "-X", "GET", "search/issues",
            "-f", f"q=is:pr author:{USERNAME}",
            "-f", "sort=updated",
            "-f", "order=desc",
            "-f", "per_page=100",
            "-f", f"page={page}",
        ])
        data = json.loads(out)
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < 100 or page >= 10:
            break
        page += 1
    return items


def normalize_pr(item):
    repo = item["repository_url"].replace("https://api.github.com/repos/", "")
    pr = item.get("pull_request") or {}
    merged_at = pr.get("merged_at")
    if merged_at:
        state = "Merged"
        sort_key = merged_at
    elif item.get("state") == "open":
        state = "Open"
        sort_key = item.get("updated_at") or ""
    elif item.get("draft"):
        state = "Draft"
        sort_key = item.get("updated_at") or ""
    else:
        state = "Closed"
        sort_key = item.get("closed_at") or item.get("updated_at") or ""
    return {
        "repo": repo,
        "number": item.get("number"),
        "title": (item.get("title") or "").strip(),
        "url": item.get("html_url"),
        "state": state,
        "sort_key": sort_key,
    }


def is_external(repo):
    return not repo.lower().startswith(f"{USERNAME.lower()}/")


def short_title(title):
    title = re.sub(r"\s+", " ", title).strip()
    return title


def group_by_repo(prs):
    grouped = defaultdict(list)
    for pr in prs:
        grouped[pr["repo"]].append(pr)
    return grouped


def escape_cell(text):
    return text.replace("|", "\\|").replace("\n", " ").strip()


def format_repo_row(repo, prs):
    nums = " · ".join(f"[#{pr['number']}]({pr['url']})" for pr in prs)
    titles = [short_title(p["title"]) for p in prs]
    if len(titles) == 1:
        desc = titles[0]
    else:
        desc = "; ".join(titles[:2])
        if len(titles) > 2:
            desc += f"; +{len(titles)-2} more"
    return f"| [{repo}](https://github.com/{repo}) | {escape_cell(nums)} | {escape_cell(desc)} |"


def render_status_table(title, prs, limit=None):
    lines = [f"**{title}**", "", "| Repository | Pull Requests | Details |", "| --- | --- | --- |"]
    subset = prs if limit is None else prs[:limit]
    grouped = group_by_repo(subset)

    def group_key(item):
        repo, repo_prs = item
        return max(p["sort_key"] for p in repo_prs)

    for repo, repo_prs in sorted(grouped.items(), key=group_key, reverse=True):
        prs_sorted = sorted(repo_prs, key=lambda p: p["sort_key"], reverse=True)
        lines.append(format_repo_row(repo, prs_sorted))
    lines.append("")
    return lines


def render_section(merged, open_prs, closed):
    lines = [MARKER_START, "## Open source", "", "Live snapshot of my external pull requests (auto-updated).", ""]
    lines.append(f"**Summary:** {len(merged)} merged · {len(open_prs)} open · {len(closed)} closed (external repositories)")
    lines.append("")
    activity_graph = (
        '<p align="center">\n'
        '  <a href="https://github.com/Ashutosh00710/github-readme-activity-graph">\n'
        '    <picture>\n'
        f'      <source media="(prefers-color-scheme: dark)" srcset="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&theme=github-compact&hide_border=true&area=true" />\n'
        f'      <source media="(prefers-color-scheme: light)" srcset="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&theme=github-light&hide_border=true&area=true" />\n'
        f'      <img alt="Contribution activity graph" src="https://github-readme-activity-graph.vercel.app/graph?username={USERNAME}&theme=github-light&hide_border=true&area=true" />\n'
        '    </picture>\n'
        '  </a>\n'
        '</p>'
    )
    lines.append(activity_graph)
    lines.append("")

    if merged:
        lines.extend(render_status_table("Merged", merged, MAX_MERGED))

    if open_prs:
        lines.extend(render_status_table("Open", open_prs, MAX_OPEN))

    if closed:
        lines.extend(render_status_table("Closed (unmerged)", closed))

    if not merged and not open_prs and not closed:
        lines.append("_No external pull requests found yet._")
        lines.append("")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"[All pull requests →](https://github.com/pulls?q=is%3Apr+author%3A{USERNAME})")
    lines.append("")
    lines.append(f"<sub>Last updated: {now}</sub>")
    lines.append(MARKER_END)
    return "\n".join(lines) + "\n"


def replace_section(readme, new_section):
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    if pattern.search(readme):
        return pattern.sub(new_section.rstrip("\n"), readme)

    # Fallback: replace legacy static section from ## Open source to just before the next centered block/stats image
    legacy = re.compile(r"\n## Open source\n.*?\n(?=<p align=\"center\">\n  <img src=\"https://skillicons)", re.DOTALL)
    if legacy.search(readme):
        return legacy.sub("\n" + new_section + "\n", readme)

    raise SystemExit("Could not find contribution markers or legacy Open source section in README.md")


def main():
    prs = [normalize_pr(x) for x in fetch_all_prs()]
    external = [p for p in prs if is_external(p["repo"])]
    merged = sorted([p for p in external if p["state"] == "Merged"], key=lambda x: x["sort_key"], reverse=True)
    open_prs = sorted([p for p in external if p["state"] in ("Open", "Draft")], key=lambda x: x["sort_key"], reverse=True)
    closed = sorted([p for p in external if p["state"] == "Closed"], key=lambda x: x["sort_key"], reverse=True)

    new_section = render_section(merged, open_prs, closed)

    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    updated = replace_section(readme, new_section)

    with open(README_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print(f"Updated {README_PATH}: merged={len(merged)} open={len(open_prs)} closed={len(closed)} external={len(external)}")


if __name__ == "__main__":
    main()
