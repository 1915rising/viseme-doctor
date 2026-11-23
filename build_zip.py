"""Build the installable add-on ZIP: viseme-doctor-<version>.zip

    python3 build_zip.py

The ZIP contains the viseme_doctor/ package at its root, which is
what Blender's Preferences > Add-ons > Install expects.
"""

import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "viseme_doctor")


def _version():
    with open(os.path.join(PKG, "__init__.py"), encoding="utf-8") as fh:
        m = re.search(r'"version":\s*\((\d+),\s*(\d+),\s*(\d+)\)', fh.read())
    return ".".join(m.groups()) if m else "0.0.0"


def main():
    out = os.path.join(HERE, "viseme-doctor-%s.zip" % _version())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(PKG)):
            if name.endswith(".py"):
                zf.write(os.path.join(PKG, name),
                         arcname="viseme_doctor/" + name)
    print("Wrote %s" % out)


if __name__ == "__main__":
    main()
