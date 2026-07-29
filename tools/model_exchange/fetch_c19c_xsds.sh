#!/usr/bin/env sh
set -eu

# Fetches the Open Group C19C ArchiMate 3.1 exchange XSDs into a gitignored
# local reference directory. The files are not vendored because the public
# index page states "All Rights Reserved".

target_dir="${1:-spec/c19c-xsd}"
mkdir -p "$target_dir"

fetch() {
  name="$1"
  url="$2"
  sha="$3"
  curl -sS "$url" -o "$target_dir/$name"
  printf '%s  %s\n' "$sha" "$target_dir/$name" | sha256sum -c -
}

fetch \
  archimate3_Model.xsd \
  https://www.opengroup.org/xsd/archimate/3.1/archimate3_Model.xsd \
  dd451abe3e3193f91dd9544b279af9bbbf17e75ff1ef86f65ad52b3f8cd29794

fetch \
  archimate3_View.xsd \
  https://www.opengroup.org/xsd/archimate/3.1/archimate3_View.xsd \
  d708ce176403034b1229b892712cfd69660aefe17da4cc54acea1ac35e4a9854

fetch \
  archimate3_Diagram.xsd \
  https://www.opengroup.org/xsd/archimate/3.1/archimate3_Diagram.xsd \
  6419080f4c4bc43b4a7b8acf870146a7bae6c3487a3ce08d3c521c028ea6056e

fetch \
  dc.xsd \
  https://www.opengroup.org/xsd/archimate/3.1/dc.xsd \
  cea8c7327e80c0bc9244dc8db586a4f21b4f093a869044ebdac878d339ebd5c3

cat > "$target_dir/PROVENANCE.txt" <<'EOF'
C19C ArchiMate 3.1 exchange XSDs fetched from:
https://www.opengroup.org/xsd/archimate/

The public index page identifies the resources as XML Schema Files for 3.1,
last updated 15 November 2019, and states:
Copyright 2015-2019 The Open Group, All Rights Reserved.

These files are local validation inputs only. Do not commit or redistribute them
from this repository.
EOF
