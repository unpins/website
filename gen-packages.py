#!/usr/bin/env python3
"""Generate packages.html from the unpins workspace.

Scans sibling directories that contain a flake.nix and, for each, runs a single
`nix eval` that pulls everything the page needs straight from the flake — no
per-package table in this script.

Data sources (all from `nix eval <pkg>#packages`):
  - version      packages.x86_64-linux.default.version
  - license      packages.x86_64-linux.default.meta.license, normalized to SPDX
  - description  packages.x86_64-linux.default.meta.description
  - Linux        always (every catalog flake builds it)
  - macOS        packages.x86_64-darwin has a `default`
  - Windows      packages.x86_64-linux has a `windows-x86_64`

license/description reach the artifact via nix-lib's `strippedOrJoined`, which
carries the upstream meta onto the final derivation. Package flakes still pinning
an older nix-lib don't expose it yet, so we evaluate with
`--override-input unpins-lib <local nix-lib>` to read the current behavior
without bumping every package's flake.lock; it's a no-op once a lock catches up.
Flakes that declare no input named `unpins-lib` (e.g. the unpin CLI itself) are
retried without the override.

A package whose flake sets no `meta.license` (a custom mkDerivation — ffmpeg, the
codec libs) comes back as "—"; a package that inherits nixpkgs' multi-component
license list (util-linux) comes back as "A / B / C". Both are resolved by
declaring an explicit `meta.license` in that flake — authoritative and reusable
(`unpin info`, SBOMs) — not by a lookup table here. `main()` prints both lists at
the end of a run so they're easy to find.
"""
import html
import json
import os
import re
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)
OUT_PATH = os.path.join(SCRIPT_DIR, "packages.html")
INDEX_PATH = os.path.join(SCRIPT_DIR, "index.html")
NIX_LIB = os.path.join(WORKSPACE, "nix-lib")

# Directories that have a flake.nix but aren't catalog packages.
#   nix-lib      — shared build glue, not a tool.
#   cosmocc      — Cosmopolitan toolchain derivation (build dep, not a CLI).
#   unpin-zig    — alternate implementation of the unpin CLI itself.
#   unpin        — the installer itself, not a catalog program (its MIT license
#                  is stated in the page footer).
#   unpin-man    — helper-verb package (`unpin man`), never on PATH
#                  (docs/helper-verbs.md); not user-installable.
#   unpin-readme — helper-verb package, same as unpin-man.
EXCLUDE = {"nix-lib", "cosmocc", "unpin-zig", "unpin",
           "unpin-man", "unpin-readme"}

# One eval per package returns everything the page needs. Pure Nix (no `lib`)
# so it doesn't depend on a particular nixpkgs being in scope.
EVAL_APPLY = r"""
ps:
let
  linux = ps.x86_64-linux.default or null;
  licRaw = if linux == null then null else (linux.meta.license or null);
  spdx = x:
    if builtins.isAttrs x then (x.spdxId or x.shortName or x.fullName or "?")
    else (if builtins.isString x then x else "?");
  lic = if licRaw == null then null
        else map spdx (if builtins.isList licRaw then licRaw else [ licRaw ]);
in {
  version = if linux == null then null else (linux.version or null);
  license = lic;
  description = if linux == null then null else (linux.meta.description or null);
  macos = (ps ? x86_64-darwin) && (ps.x86_64-darwin ? default);
  windows = (ps ? x86_64-linux) && (ps.x86_64-linux ? "windows-x86_64");
}
"""


def _run(cmd):
    try:
        # 400s: gvim's static-GTK2 override cascade can take minutes to
        # evaluate cold (several pkgsStatic overrides + patches).
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=400)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def eval_package(pkg_dir):
    """version/license/description/platforms in one eval.

    Prefer the local-nix-lib override (so meta propagation is visible even
    before a package's lock bumps); fall back to a plain eval for flakes with
    no `unpins-lib` input. Returns a dict, or None if both evals fail.
    """
    target = f"{pkg_dir}#packages"
    with_override = [
        "nix", "eval", "--json", target,
        "--override-input", "unpins-lib", f"path:{NIX_LIB}",
        "--apply", EVAL_APPLY,
    ]
    plain = ["nix", "eval", "--json", target, "--apply", EVAL_APPLY]
    return _run(with_override) or _run(plain)


def discover_packages():
    rows = []
    for name in sorted(os.listdir(WORKSPACE)):
        pkg_dir = os.path.join(WORKSPACE, name)
        flake = os.path.join(pkg_dir, "flake.nix")
        if not os.path.isfile(flake) or name in EXCLUDE:
            continue
        data = eval_package(pkg_dir) or {}
        lic = data.get("license")
        rows.append({
            "name":        name,
            "version":     data.get("version") or "—",
            "license":     " / ".join(lic) if lic else "—",
            "multi":       bool(lic) and len(lic) > 1,
            "description": data.get("description") or "",
            "macos":       bool(data.get("macos")),
            "windows":     bool(data.get("windows")),
        })
    return rows


# The ✓/— glyphs are decoration to a screen reader; pair them with visually
# hidden yes/no text (announced after the column header).
YES_CELL = ('<td class="os yes"><span aria-hidden="true">✓</span>'
            '<span class="sr-only">yes</span></td>')
NO_CELL = ('<td class="os"><span aria-hidden="true">—</span>'
           '<span class="sr-only">no</span></td>')


def os_cell(supported):
    return YES_CELL if supported else NO_CELL


def render_row(pkg):
    return (
        '            <tr>'
        f'<td><a href="https://github.com/unpins/{pkg["name"]}">{pkg["name"]}</a></td>'
        f'<td class="desc">{html.escape(pkg["description"])}</td>'
        f'<td class="version">{pkg["version"]}</td>'
        f'<td class="license">{pkg["license"]}</td>'
        f'{os_cell(True)}'  # Linux: every catalog flake builds it
        f'{os_cell(pkg["macos"])}'
        f'{os_cell(pkg["windows"])}'
        '</tr>'
    )


PAGE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>unpins — available packages</title>
    <meta name="description" content="The unpins catalog: {count} programs built as single self-contained binaries for Linux, macOS, and Windows — htop, ffmpeg, python, vim, jq, and more.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://unpins.org/packages.html">
    <meta property="og:title" content="unpins — available packages">
    <meta property="og:description" content="The unpins catalog: {count} programs built as single self-contained binaries for Linux, macOS, and Windows — htop, ffmpeg, python, vim, jq, and more.">
    <meta property="og:image" content="https://unpins.org/og.png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta name="twitter:card" content="summary_large_image">
    <link rel="icon" type="image/svg+xml" href="favicon.svg">
    <link rel="stylesheet" href="styles.css">
  </head>
  <body class="subpage">
    <div class="container">
      <header>
        <h1><a href="index.html"><img src="unpins-logo.svg" alt="unpins" class="logo"></a></h1>
        <nav class="topnav">
          <a href="packages.html" aria-current="page">Packages</a>
          <a href="why.html">Why?</a>
          <a href="https://github.com/unpins/unpin#usage">Docs</a>
          <a href="https://github.com/unpins">GitHub</a>
        </nav>
      </header>

      <section>
        <p class="pkg-count">{count} packages, each a single self-contained binary. Install any of them with <code>unpin install &lt;name&gt;</code>.</p>
        <input type="search" id="pkg-filter" class="pkg-filter" placeholder="Filter packages…" aria-label="Filter packages">
        <div class="table-scroll">
        <table class="pkg-table">
          <thead>
            <tr>
              <th>Package</th>
              <th>Description</th>
              <th>Version</th>
              <th>License</th>
              <th class="os">Linux</th>
              <th class="os">macOS</th>
              <th class="os">Windows</th>
            </tr>
          </thead>
          <tbody>
{rows}
          </tbody>
        </table>
        </div>
        <p class="pkg-note">
          A few programs have no Windows row: some are Linux-specific (<code>util-linux</code>, <code>shadow</code>, <code>kmod</code>), others rely on platform APIs that aren't available or portable on Windows (<code>htop</code>, <code>tmux</code>). Support is tracked per program in the table above.
        </p>
      </section>

      <footer>
        <p>
          The <code>unpin</code> CLI is MIT-licensed. Each program above keeps its upstream license.
        </p>
      </footer>
    </div>

    <script>
      const filterInput = document.getElementById('pkg-filter');
      // Match on name / description / version / license; skip the OS columns
      // so their hidden yes/no text doesn't match queries like "windows".
      const pkgRows = Array.from(document.querySelectorAll('.pkg-table tbody tr'), row => ({{
        row,
        text: Array.from(row.cells).slice(0, 4).map(c => c.textContent).join(' ').toLowerCase(),
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


# Home-page "Available Packages" blurb, kept in sync with the table so the
# count never goes stale. Rewritten between the gen:pkg-blurb markers in
# index.html on every run.
FEATURED = ["ffmpeg", "python", "vim", "jq", "htop"]
BLURB_RE = re.compile(
    r"(<!-- gen:pkg-blurb[^>]*-->\n).*?(\n\s*<!-- /gen:pkg-blurb -->)", re.S)


def update_index_blurb(pkgs):
    names = {p["name"] for p in pkgs}
    codes = ", ".join(f"<code>{n}</code>" for n in FEATURED if n in names)
    blurb = (
        f"        <p>{len(pkgs)} programs in the catalog — {codes}, and more — "
        "each a single self-contained binary for Linux, macOS, and (where viable) "
        'Windows; see <a href="packages.html">the full list</a>.</p>'
    )
    with open(INDEX_PATH) as f:
        page = f.read()
    new = BLURB_RE.sub(lambda m: m.group(1) + blurb + m.group(2), page, count=1)
    if new != page:
        with open(INDEX_PATH, "w") as f:
            f.write(new)
        print(f"Updated {INDEX_PATH} blurb ({len(pkgs)} packages)")


def main():
    pkgs = discover_packages()
    rows = "\n".join(render_row(p) for p in pkgs)
    with open(OUT_PATH, "w") as f:
        f.write(PAGE.format(rows=rows, count=len(pkgs)))
    print(f"Wrote {OUT_PATH} ({len(pkgs)} packages)")
    update_index_blurb(pkgs)

    nodesc = [p["name"] for p in pkgs if not p["description"]]
    if nodesc:
        print(f"\n{len(nodesc)} package(s) with no meta.description "
              f"(declare it in the flake):\n  {', '.join(nodesc)}")

    missing = [p["name"] for p in pkgs if p["license"] == "—"]
    multi = [p["name"] for p in pkgs if p["multi"]]
    if missing:
        print(f"\n{len(missing)} package(s) with no meta.license "
              f"(declare it in the flake):\n  {', '.join(missing)}")
    if multi:
        print(f"\n{len(multi)} package(s) with a multi-license list "
              f"(consider a curated meta.license in the flake):\n  {', '.join(multi)}")


if __name__ == "__main__":
    main()
