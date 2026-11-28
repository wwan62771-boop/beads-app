"""Resolve exact colors for old and new editable project snapshots."""
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CURRENT=json.loads((ROOT/'palettes.json').read_text())
LEGACY=json.loads((ROOT/'palettes-legacy.json').read_text())
CURRENT_VERSION='mard-pixel-beads-2026-11-28'

def resolve_project_palette(project):
    identity=str(project.get('paletteId','291'))
    known=CURRENT.get(identity)
    if known is None:raise ValueError('未知色卡。')
    snapshot=project.get('paletteSnapshot')
    if 'paletteSnapshot' in project:
        if not isinstance(snapshot,list) or len(snapshot)!=len(known):raise ValueError('项目色卡快照不完整。')
        codes={color['code'] for color in known};seen=set()
        for color in snapshot:
            if not isinstance(color,dict) or color.get('code') not in codes or color['code'] in seen:
                raise ValueError('项目色卡快照色号无效。')
            value=color.get('hex');rgb=color.get('rgb')
            if not isinstance(value,str) or not re.fullmatch('#[0-9a-fA-F]{6}',value) or not isinstance(rgb,list) or len(rgb)!=3:
                raise ValueError('项目色卡颜色无效。')
            if any(type(v) is not int or v!=int(value[1+i*2:3+i*2],16) for i,v in enumerate(rgb)):
                raise ValueError('项目色卡 RGB 与 HEX 不一致。')
            seen.add(color['code'])
        return snapshot
    version=project.get('paletteVersion')
    if not version or version=='mard-legacy-v1':return LEGACY[identity]
    if version not in (CURRENT_VERSION,'reference-v1'):raise ValueError('项目色卡版本未知，请提供完整色卡快照。')
    return known
