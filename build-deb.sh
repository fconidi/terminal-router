#!/bin/bash
# Build terminal-router .deb
#
# Usage:  bash ./build-deb.sh
# Output: terminal-router_<VERSION>_all.deb (next to this script)

set -euo pipefail

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
BUILD="${WORKDIR}/build"

[ -d "$BUILD" ] || { echo "ERROR: $BUILD missing" >&2; exit 1; }

PKG_NAME=$(awk '/^Package:/{print $2;exit}' "$BUILD/DEBIAN/control")
PKG_VERSION=$(awk '/^Version:/{print $2;exit}' "$BUILD/DEBIAN/control")
ARCH=$(awk '/^Architecture:/{print $2;exit}' "$BUILD/DEBIAN/control")
OUTPUT_DEB="${WORKDIR}/${PKG_NAME}_${PKG_VERSION}_${ARCH}.deb"

echo "==> $PKG_NAME $PKG_VERSION ($ARCH)"
echo "==> Target: $OUTPUT_DEB"

# Perms
chmod 755 "$BUILD/usr/share/terminal-router/install.sh"
chmod 755 "$BUILD/usr/bin/terminal-router"
chmod 644 "$BUILD/usr/share/applications/terminal-router.desktop"
find "$BUILD/usr/share/icons" -name '*.png' -exec chmod 644 {} \;
find "$BUILD/usr/share/doc" "$BUILD/usr/share/man" -type f -exec chmod 644 {} \;
chmod 755 "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/postrm" 2>/dev/null || true

# md5sums
echo "==> md5sums"
(cd "$BUILD" && find . -type f -not -path './DEBIAN/*' -printf '%P\n' | sort | xargs -d '\n' md5sum > DEBIAN/md5sums)

# Installed-Size
SIZE_KB=$(du -sk "$BUILD" --exclude=DEBIAN | cut -f1)
if grep -q '^Installed-Size:' "$BUILD/DEBIAN/control"; then
    sed -i "s/^Installed-Size:.*/Installed-Size: ${SIZE_KB}/" "$BUILD/DEBIAN/control"
else
    echo "Installed-Size: ${SIZE_KB}" >> "$BUILD/DEBIAN/control"
fi

# Build
echo "==> dpkg-deb --build"
rm -f "$OUTPUT_DEB"
fakeroot dpkg-deb --build "$BUILD" "$OUTPUT_DEB"

# Verify
echo
echo "==> Metadata:"
dpkg-deb -I "$OUTPUT_DEB" | grep -E "^ (Package|Version|Architecture|Maintainer|Installed-Size)"
echo
echo "OK: $OUTPUT_DEB"
echo
echo "Install on host:"
echo "  sudo apt install $OUTPUT_DEB"
echo
echo "Then, as your normal user:  terminal-router install"
