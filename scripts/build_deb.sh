#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 022
read -r version app_id <<VERSIONS
$(/usr/bin/python3 -I -c 'import sys; sys.path.insert(0, "."); from termspace import APP_ID, VERSION; print(VERSION, APP_ID)')
VERSIONS
mkdir -p dist
stage=$(mktemp -d)
trap 'rm -r -- "$stage"' EXIT HUP INT TERM
chmod 755 "$stage"
install -d "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/lib/termspace/termspace" \
    "$stage/usr/share/doc/termspace" "$stage/usr/share/applications"
cat > "$stage/DEBIAN/control" <<CONTROL
Package: termspace
Version: $version
Architecture: all
Section: utils
Priority: optional
Maintainer: TermSpace contributors <35392326+ishafayetul@users.noreply.github.com>
Depends: python3 (>= 3.12), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0 (>= 4.14), gir1.2-vte-3.91 (>= 0.76), libvte-2.91-gtk4-0 (>= 0.76.0-1ubuntu0.1)
Homepage: https://github.com/ishafayetul/TermSpace
Description: Native GTK terminal workspace manager
 TermSpace provides independent shell sessions, split panes, tabbed windows,
 reusable workspaces and reviewed terminal pastes on Ubuntu.
CONTROL
install -m 644 termspace/*.py termspace/style.css "$stage/usr/lib/termspace/termspace/"
install -m 755 main.py "$stage/usr/lib/termspace/main.py"
ln -s ../lib/termspace/main.py "$stage/usr/bin/termspace"
install -m 644 "packaging/$app_id.desktop" "$stage/usr/share/applications/"
for size in 48 128 256; do
    install -D -m 644 "packaging/icon-$size.png" "$stage/usr/share/icons/hicolor/${size}x${size}/apps/$app_id.png"
done
install -m 644 LICENSE "$stage/usr/share/doc/termspace/copyright"
install -m 644 SECURITY.md THIRD_PARTY_NOTICES.md "$stage/usr/share/doc/termspace/"
gzip -n -9c packaging/changelog.Debian > "$stage/usr/share/doc/termspace/changelog.Debian.gz"
package="termspace_${version}_all.deb"
dpkg-deb --root-owner-group --build "$stage" "dist/$package"
(cd dist && sha256sum "$package" > "$package.sha256")
