from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKEN = re.compile(br"p" + br"r" + br"o" + br"v" + br"e" + br"c" + br"t" + br"u" + br"s", re.I)
TEXT_TOKEN = re.compile("p"+"r"+"o"+"v"+"e"+"c"+"t"+"u"+"s", re.I)

name_hits=[]
content_hits=[]
office_hits=[]
for path in ROOT.rglob("*"):
    rel=path.relative_to(ROOT).as_posix()
    if any(part in {"__pycache__", ".venv", "build", "dist"} for part in path.relative_to(ROOT).parts):
        continue
    if TEXT_TOKEN.search(rel):
        name_hits.append(rel)
    if not path.is_file():
        continue
    data=path.read_bytes()
    if TOKEN.search(data):
        content_hits.append(rel)
    if path.suffix.lower() in {".xlsx",".docx",".pptx",".xlsm"}:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                if TEXT_TOKEN.search(member) or TOKEN.search(archive.read(member)):
                    office_hits.append(f"{rel}!{member}")

if name_hits or content_hits or office_hits:
    raise SystemExit(f"Identity scan failed: names={name_hits}, content={content_hits}, office={office_hits}")
print("Identity scan: ZERO forbidden-name occurrences.")
