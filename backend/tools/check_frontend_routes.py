#!/usr/bin/env python3
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / 'frontend'

href_re = re.compile(r'href\s*=\s*"([^"]+)"')
onclick_href_re = re.compile(r"window\.location\.href\s*=\s*'([^']+)'")
js_loc_re = re.compile(r"window\.location\.href\s*=\s*\"([^\"]+)\"")

skip_prefixes = ('http://','https://','//','mailto:','#')

ADMIN_SLUG_ROUTES = ["admin/garage-detail/"]

issues = []
seen = set()


def normalize(p):
    # strip query and fragment
    return re.split(r'[?#]', p)[0].lstrip('/')


def file_served_by_backend(path):
    """Return True if backend serve_frontend would return a file for this path."""
    if not path:
        return True
    # exact file under frontend
    f = FRONTEND / path
    if f.exists():
        return True
    # html path
    if (FRONTEND / (path + '.html')).exists():
        return True
    # index path
    if (FRONTEND / path / 'index.html').exists():
        return True
    # customer special: if not starting with admin/mechanic/api/css/js/uploads
    if not path.startswith(('admin/','mechanic/','api/','css/','js/','uploads/')):
        # try customer folder
        if (FRONTEND / 'customer' / path).exists():
            return True
        if (FRONTEND / 'customer' / (path + '.html')).exists():
            return True
        if (FRONTEND / 'customer' / path / 'index.html').exists():
            return True
    # slug-based admin routes
    for sp in ADMIN_SLUG_ROUTES:
        if path.startswith(sp):
            remaining = path[len(sp):]
            if '/' in remaining or '.' in remaining:
                return False
            # valid slug: numeric or slug-like ending with -number
            if re.match(r'^[a-z0-9\-]+-\d+$', remaining, re.I) or re.match(r'^\d+$', remaining):
                if (FRONTEND / (sp.rstrip('/') + '.html')).exists():
                    return True
            return False
    return False

print('Scanning frontend for links...')
for root, dirs, files in os.walk(FRONTEND):
    for fname in files:
        if not fname.endswith(('.html','.js')):
            continue
        path = os.path.join(root, fname)
        rel = os.path.relpath(path, FRONTEND).replace('\\','/')
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            data = f.read()
        matches = href_re.findall(data) + onclick_href_re.findall(data) + js_loc_re.findall(data)
        for m in matches:
            # skip external and anchors
            if any(m.startswith(p) for p in skip_prefixes):
                continue
            # skip template variables like ${API} etc
            if '${' in m or '}' in m:
                continue

            # normalize
            raw = m
            norm = normalize(raw)

            # candidate paths to check:
            candidates = []
            # absolute-like (starts with '/'), treat as root-relative
            if raw.startswith('/'):
                candidates.append(norm.lstrip('/'))
            else:
                # relative to source file directory
                src_dir = os.path.dirname(rel)
                if src_dir:
                    candidates.append(os.path.normpath(os.path.join(src_dir, norm)).replace('\\','/'))
                # as-is (root relative)
                candidates.append(norm)

            # de-duplicate
            candidates = [c for c in dict.fromkeys(candidates)]

            ok = any(file_served_by_backend(c) for c in candidates)
            if not ok:
                if norm in seen:
                    continue
                seen.add(norm)
                issues.append((rel, raw, candidates))

print('\nScan complete.\n')
if not issues:
    print('No missing route mappings found. All local links map to frontend files or backend rules.')
else:
    print(f'Found {len(issues)} suspicious links that may not be served by backend:')
    for src, link, cands in issues[:200]:
        print(f'- In {src}: -> {link}  (checked candidates: {cands})')

print('\nNotes:')
print('- Links containing template variables like ${API} are ignored (dynamic).')
print('- Relative links are checked relative to the source file location.')
print('Done.')
