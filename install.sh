#!/bin/sh
# Install Prime Env Harness from a GitHub Release.
#
#   curl -fsSL https://raw.githubusercontent.com/nicolasakf/Prime-Env-Harness/main/install.sh | sh
#
# Environment:
#   PRIME_ENV_HARNESS_VERSION   release to install, e.g. 0.1.1 (default: the latest release)
#   PRIME_ENV_HARNESS_PREFIX    install root (default: ~/.local/share/prime-env-harness)
#   PRIME_ENV_HARNESS_BIN_DIR   where the launcher goes (default: ~/.local/bin)
#
# The release tarball is verified against its published SHA-256 before it is
# unpacked. Nothing is written outside the two directories above.
set -eu

repo="nicolasakf/Prime-Env-Harness"
prefix="${PRIME_ENV_HARNESS_PREFIX:-$HOME/.local/share/prime-env-harness}"
bin_dir="${PRIME_ENV_HARNESS_BIN_DIR:-$HOME/.local/bin}"

fail() {
  echo "install: $*" >&2
  exit 1
}

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=macos ;;
  *) fail "unsupported OS: $(uname -s) (Linux and macOS only)" ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *) fail "unsupported CPU: $(uname -m)" ;;
esac
platform="$os-$arch"

command -v curl >/dev/null 2>&1 || fail "curl is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"
if command -v sha256sum >/dev/null 2>&1; then
  sha256() { sha256sum "$1" | cut -d' ' -f1; }
elif command -v shasum >/dev/null 2>&1; then
  sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }
else
  fail "sha256sum or shasum is required"
fi

version="${PRIME_ENV_HARNESS_VERSION:-}"
if [ -z "$version" ]; then
  version="$(curl -fsSL "https://api.github.com/repos/$repo/releases/latest" |
    sed -n 's/.*"tag_name": *"v\{0,1\}\([^"]*\)".*/\1/p' | head -n 1)"
  [ -n "$version" ] || fail "could not determine the latest release; set PRIME_ENV_HARNESS_VERSION"
fi
version="${version#v}"

name="prime-env-harness-$version-$platform"
base="https://github.com/$repo/releases/download/v$version"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "Downloading Prime Env Harness $version ($platform)..."
curl -fsSL -o "$tmp/$name.tar.gz" "$base/$name.tar.gz" ||
  fail "no release asset $name.tar.gz for v$version"
curl -fsSL -o "$tmp/$name.tar.gz.sha256" "$base/$name.tar.gz.sha256" ||
  fail "no checksum for $name.tar.gz"

expected="$(cut -d' ' -f1 <"$tmp/$name.tar.gz.sha256")"
actual="$(sha256 "$tmp/$name.tar.gz")"
[ "$expected" = "$actual" ] || fail "checksum mismatch for $name.tar.gz"

mkdir -p "$prefix" "$bin_dir"
rm -rf "${prefix:?}/$version"
tar -xzf "$tmp/$name.tar.gz" -C "$tmp"
mv "$tmp/$name" "$prefix/$version"

# A launcher script, not a symlink: the binary finds its skills and runtime
# next to the real executable.
launcher="$bin_dir/prime-env-harness"
cat >"$launcher" <<EOF
#!/bin/sh
export PI_PACKAGE_DIR="$prefix/$version"
exec "$prefix/$version/prime-env-harness" "\$@"
EOF
chmod 755 "$launcher"

echo "Installed Prime Env Harness $version to $prefix/$version"
echo "Launcher: $launcher"
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo "Add $bin_dir to your PATH to run 'prime-env-harness'." ;;
esac
