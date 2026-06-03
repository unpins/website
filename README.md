# website

Source for [unpins.org](https://unpins.org) — the landing page for
[unpins](https://github.com/unpins): portable, statically-linked builds of
common programs that run unchanged on Linux, macOS, and Windows,
plus the `unpin` CLI to install them.

## Layout

```
.
├── index.html          home page
├── packages.html       packages table (generated)
├── styles.css          shared styles
├── unpins-logo.svg     theme-aware wordmark
├── favicon.svg         tab icon: 'u' + arrow
├── _redirects          /unpin-* → latest GitHub release asset
├── wrangler.toml       Cloudflare Workers config
├── .assetsignore       files excluded from the static-assets upload
├── Makefile
└── gen-packages.py     writes packages.html (uses `nix eval`)
```

`packages.html` is committed so the deploy needs no build step in CI.

## Build

```sh
make           # dev PNG preview of the logo
make packages  # regenerate the package table (requires `nix`)
make clean     # remove target/
```

Dependencies: `inkscape`; plus `nix` for `make packages`.

## Preview

Open `index.html` directly in a browser. The wordmark adapts to
`prefers-color-scheme` on its own — to test dark mode in Firefox, open
DevTools → Inspector → click the moon icon.

## Deploy

Hosted on Cloudflare Workers Static Assets. The first deploy binds
`unpins.org` automatically via `wrangler.toml`:

```sh
npx wrangler deploy
```

The `_redirects` file rewrites `unpins.org/unpin-<arch>-<os>[.exe]` to
the latest asset of the [`unpin`](https://github.com/unpins/unpin)
release, so the install snippets on the site work end-to-end without
mirroring any binaries here.
