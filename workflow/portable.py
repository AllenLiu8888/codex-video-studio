"""Portable paths and font discovery; never silently download fonts or models."""
from pathlib import Path
import os, hashlib, json, shutil, subprocess

CODE_ROOT=Path(__file__).resolve().parents[1]
def project_root(): return Path(os.environ.get('STUDIO_PROJECT_ROOT',str(CODE_ROOT))).expanduser().resolve()
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def resolve_font(value='auto', root=None):
    root=Path(root or project_root())
    configured=os.environ.get('STUDIO_FONT') or (value if value!='auto' else None)
    if configured:
        p=Path(configured).expanduser();p=p if p.is_absolute() else root/p
        if not p.is_file(): raise ValueError('Font is missing: '+str(p))
        return str(p.resolve())
    # Prefer CJK-capable fonts; no font is redistributed by the runtime.
    candidates=[str(CODE_ROOT/'assets/fonts/NotoSerifSC-VF.ttf'),'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/System/Library/Fonts/PingFang.ttc',
                '/System/Library/Fonts/Supplemental/Arial.ttf']
    for name in candidates:
        if Path(name).is_file(): return name
    if shutil.which('fc-match'):
        found=subprocess.check_output(['fc-match','-f','%{file}','sans-serif'],text=True).strip()
        if Path(found).is_file():return found
    raise ValueError('No usable font found. Set STUDIO_FONT to a licensed TTF/OTF/TTC with all required glyphs.')

def validate_scope(p,episode,root):
    root=Path(root).resolve();episode=Path(episode).resolve()
    if p['id'] != episode.name: raise ValueError('Episode ID must match its allocated folder')
    if not episode.is_relative_to(root): raise ValueError('Episode must be inside --project')
    for value in [p['brand']]+[a[k] for a in p['assets'] for k in ['file','prompt_file','reference','generation_record','record_file'] if a.get(k)]:
        if not (root/value).resolve().is_relative_to(root):raise ValueError('Asset/configuration path escapes project')
    lock=json.loads((episode/'source/locked-inputs.json').read_text())
    for name,digest in lock['files'].items():
        path=(episode/name).resolve()
        if not path.is_relative_to(episode) or sha(path)!=digest:raise ValueError('Locked input changed: '+name)
    snapshot=json.loads((episode/'generation/brand-snapshot.json').read_text())
    for item in snapshot['references']:
        path=(root/item['file']).resolve()
        if not path.is_relative_to(root) or sha(path)!=item['sha256']:raise ValueError('Brand reference missing/changed: '+item['file'])
    if sha(root/p['brand'])!=snapshot['profile_sha256']:raise ValueError('Episode brand profile changed after freeze; create a deliberate revision')
