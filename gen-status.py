#!/usr/bin/env python3
"""Generate status.html — a CI dashboard for the unpins catalog.

Lists every catalog package (the same set as packages.html) with a *live*
GitHub Actions badge for its Build workflow, so a glance shows whether any
package's CI is red. The badges are served by GitHub and always reflect the
latest run on `main` — this script only bakes the package list and the badge
URLs, it does not query run state. Regenerate (e.g. after adding a package)
with `make status`.

The page is intentionally unlisted: it ships to unpins.org/status.html but no
other page links to it (not in the topnav). It's an operator dashboard, not a
visitor-facing page.

Each package repo has two workflows: a Build workflow named `<name>.yml`
(push to main + dispatch) and `release.yml` (dispatch only). The badge points
at the Build workflow — discovered as the lone `.yml` that isn't release.yml,
falling back to `<name>.yml`.
"""
import html
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)
OUT_PATH = os.path.join(SCRIPT_DIR, "status.html")

# Same non-catalog set as gen-packages.py, plus mandoc-sys (build glue for
# `unpin man`, no Build workflow — see gen-packages.py for the rest).
EXCLUDE = {"nix-lib", "cosmocc", "unpin-zig", "unpin",
           "unpin-man", "unpin-readme", "mandoc-sys"}


def build_workflow(name):
    """Filename of the package's Build workflow (the `.yml` that isn't
    release.yml). Falls back to `<name>.yml` when the workflows dir is absent
    from the local checkout or only release.yml is present."""
    wf_dir = os.path.join(WORKSPACE, name, ".github", "workflows")
    default = f"{name}.yml"
    try:
        ymls = [f for f in os.listdir(wf_dir)
                if f.endswith(".yml") and f != "release.yml"]
    except FileNotFoundError:
        return default
    if default in ymls:
        return default
    return ymls[0] if ymls else default


def discover_packages():
    names = []
    for name in sorted(os.listdir(WORKSPACE)):
        flake = os.path.join(WORKSPACE, name, "flake.nix")
        if not os.path.isfile(flake) or name in EXCLUDE:
            continue
        names.append(name)
    return names


def render_row(name):
    wf = build_workflow(name)
    runs = f"https://github.com/unpins/{name}/actions/workflows/{wf}"
    # ?branch=main pins the badge to the default branch (matches the Build
    # trigger); the badge image is live, served from GitHub's camo cache.
    badge = f"{runs}/badge.svg?branch=main"
    return (
        '            <tr>'
        f'<td><a href="https://github.com/unpins/{name}">{html.escape(name)}</a></td>'
        f'<td class="ci"><a href="{runs}">'
        f'<img class="ci-badge" src="{badge}" alt="{html.escape(name)} build status" '
        'loading="lazy" height="20"></a></td>'
        '</tr>'
    )


PAGE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex">
    <title>unpins — CI status</title>
    <link rel="icon" type="image/svg+xml" href="favicon.svg">
    <link rel="stylesheet" href="styles.css">
  </head>
  <body class="subpage">
    <div class="container">
      <header>
        <h1><a href="index.html"><img src="unpins-logo.svg" alt="unpins" class="logo"></a></h1>
        <nav class="topnav">
          <a href="packages.html">Packages</a>
          <a href="why.html">Why?</a>
          <a href="https://github.com/unpins/unpin#usage">Docs</a>
          <a href="https://github.com/unpins">GitHub</a>
        </nav>
      </header>

      <section>
        <h2>CI status</h2>
        <p class="pkg-count">Live build status of all {count} catalog packages. Each badge reflects the latest run of the package's Build workflow on <code>main</code> — click it to open the run history. Red means that package's CI is broken.</p>
        <input type="search" id="pkg-filter" class="pkg-filter" placeholder="Filter packages…" aria-label="Filter packages">
        <div class="table-scroll">
        <table class="pkg-table status-table">
          <thead>
            <tr>
              <th>Package</th>
              <th>CI</th>
            </tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
        </div>
        <p class="pkg-note">
          Badges are served live by GitHub Actions; this page is a static list and only changes when a package is added or removed (regenerate with <code>make status</code>). The <code>unpin</code> CLI and build infrastructure (<code>action-build</code>, <code>nix-lib</code>) aren't catalog packages and aren't listed here.
        </p>
      </section>
    </div>

    <script>
      const filterInput = document.getElementById('pkg-filter');
      const pkgRows = Array.from(document.querySelectorAll('.pkg-table tbody tr'), row => ({{
        row,
        text: row.cells[0].textContent.toLowerCase(),
      }}));
      filterInput.addEventListener('input', () => {{
        const q = filterInput.value.trim().toLowerCase();
        for (const {{row, text}} of pkgRows) {{
          row.style.display = text.includes(q) ? '' : 'none';
        }}
      }});
    </script>
  </body>
</html>
"""


def main():
    pkgs = discover_packages()
    rows = "\n".join(render_row(p) for p in pkgs)
    with open(OUT_PATH, "w") as f:
        f.write(PAGE.format(rows=rows, count=len(pkgs)))
    print(f"Wrote {OUT_PATH} ({len(pkgs)} packages)")


if __name__ == "__main__":
    main()
