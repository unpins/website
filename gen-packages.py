#!/usr/bin/env python3
"""Generate packages.html from the unpins workspace.

Scans sibling directories that contain a flake.nix and writes the full
packages.html (styled via styles.css). Windows support is inferred from the
flake referencing pkgsCross.mingwW64 or "windows-x86_64".
"""
import os
import re
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(SCRIPT_DIR)
OUT_PATH = os.path.join(SCRIPT_DIR, "packages.html")

# Directories that have a flake.nix but aren't end-user packages.
#   nix-lib   — shared build glue, not a tool.
#   unpin-zig — alternate implementation of the unpin CLI itself.
EXCLUDE = {"nix-lib", "unpin-zig"}

# SPDX license per package. Sourced from nixpkgs meta.license at the pinned
# channel, adjusted where build flags change the effective license
# (e.g. ffmpeg with --enable-gpl --enable-version3 → GPL-3.0-or-later).
LICENSE = {
    "bash":   "GPL-3.0-or-later",
    "curl":   "curl",
    "ffmpeg": "GPL-3.0-or-later",
    "git":    "GPL-2.0-only",
    "htop":   "GPL-2.0-only",
    "jq":     "MIT",
    "tmux":   "BSD-3-Clause",
    "tree":   "GPL-2.0-or-later",
    "vim":    "Vim",
}

WIN_RE = re.compile(r"pkgsCross\.mingwW64|windows-x86_64")


def windows_supported(flake_path):
    with open(flake_path) as f:
        return bool(WIN_RE.search(f.read()))


def parse_version_from_symlink(link_path):
    """Parse the version out of a Nix `result` symlink.

    Nix store paths follow the HASH-PNAME-VERSION convention; the version is
    the trailing `-`-delimited segment that starts with a digit.
    """
    try:
        target = os.readlink(link_path)
    except OSError:
        return None
    base = os.path.basename(target)
    if "-" in base:
        base = base.split("-", 1)[1]  # drop hash prefix
    for part in reversed(base.split("-")):
        if part and part[0].isdigit():
            return part
    return None


def get_version(pkg_dir):
    """Authoritative: ask nix (uses flake.lock pins, no build required).
    Fallback: parse a result symlink if one happens to be around.
    """
    try:
        r = subprocess.run(
            ["nix", "eval", "--raw",
             f"{pkg_dir}#packages.x86_64-linux.default.version"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    for cand in ("result", "result-win"):
        link = os.path.join(pkg_dir, cand)
        if os.path.islink(link):
            v = parse_version_from_symlink(link)
            if v:
                return v
    return None


def discover_packages():
    rows = []
    for name in sorted(os.listdir(WORKSPACE)):
        pkg_dir = os.path.join(WORKSPACE, name)
        flake = os.path.join(pkg_dir, "flake.nix")
        if not os.path.isfile(flake) or name in EXCLUDE:
            continue
        rows.append({
            "name":    name,
            "version": get_version(pkg_dir) or "—",
            "license": LICENSE.get(name, "—"),
            "windows": windows_supported(flake),
        })
    return rows


def render_row(pkg):
    win = ('<td class="os yes">✓</td>' if pkg["windows"]
           else '<td class="os">—</td>')
    return (
        '            <tr>'
        f'<td><a href="https://github.com/unpins/{pkg["name"]}">{pkg["name"]}</a></td>'
        f'<td class="version">{pkg["version"]}</td>'
        f'<td class="license">{pkg["license"]}</td>'
        '<td class="os yes">✓</td>'
        '<td class="os yes">✓</td>'
        f'{win}'
        '</tr>'
    )


PAGE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>unpins — available packages</title>
    <link rel="stylesheet" href="styles.css">
  </head>
  <body class="subpage">
    <div class="container">
      <header>
        <h1><a href="index.html"><img src="unpins-logo.svg" alt="unpins" class="logo"></a></h1>
      </header>

      <p class="back"><a href="index.html">← Back to home</a></p>

      <section>
        <table class="pkg-table">
          <thead>
            <tr>
              <th>Package</th>
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
        <p class="pkg-note">
          A few tools have no Windows row by design: the upstream architecture (e.g. <code>bash</code>'s fork-singleton, <code>git</code>'s POSIX assumptions) doesn't reduce cleanly to a single standalone <code>.exe</code>.
        </p>
      </section>

      <footer>
        <p>
          The <code>unpin</code> CLI is MIT-licensed. Each tool above keeps its upstream license.<br>
          View on <a href="https://github.com/unpins">GitHub</a>.
        </p>
      </footer>
    </div>
  </body>
</html>
"""


def main():
    pkgs = discover_packages()
    rows = "\n".join(render_row(p) for p in pkgs)
    with open(OUT_PATH, "w") as f:
        f.write(PAGE.format(rows=rows))
    print(f"Wrote {OUT_PATH} ({len(pkgs)} packages)")


if __name__ == "__main__":
    main()
