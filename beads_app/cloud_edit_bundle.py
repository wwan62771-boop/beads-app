"""Validate portable editable drawings before storing or importing them."""
import base64,hashlib,io,json,re
from PIL import Image

LIMIT=60*1024*1024
def validate_bundle(bundle):
    if not isinstance(bundle,dict) or bundle.get('format')!='wanwan-editable-work-v1':
        raise ValueError('不是可编辑作品存档。')
    if not isinstance(bundle.get('name'),str) or not 1<=len(bundle['name'])<=200:
        raise ValueError('作品名称无效。')
    entries=bundle.get('entries')
    if not isinstance(entries,list) or not 1<=len(entries)<=30:
        raise ValueError('每款请选择1至30个可编辑规格。')
    signatures=set()
    for entry in entries:
        if not isinstance(entry,dict):raise ValueError('规格无效。')
        project=entry.get('project')
        if not isinstance(project,dict) or project.get('format')!='yiwanwanyi-beads' or type(project.get('version')) is not int or project.get('version')!=1:
            raise ValueError('缺少工坊可编辑项目。')
        w,h=project.get('W'),project.get('H')
        if any(type(v) is not int or not 1<=v<=416 for v in (w,h)):
            raise ValueError('图纸尺寸须为1至416格。')
        palette=project.get('paletteId','291');bead=project.get('beadSize',2.6)
        if palette not in ('221','291','perler','hama','artkal') or bead not in (2.5,2.6,5):
            raise ValueError('色卡或豆子规格无效。')
        signature=(w,h,palette,bead)
        if signature in signatures:raise ValueError('规格重复。')
        signatures.add(signature)
        if not isinstance(project.get('grid'),list) or len(project['grid'])!=w*h:
            raise ValueError('项目格数不符。')
        if not isinstance(project.get('mapping'),list) or not isinstance(project.get('overrides'),list):
            raise ValueError('项目配色数据无效。')
        try:
            mapping=dict(project['mapping'])
            if len(project['mapping'])>173056 or len(project['overrides'])>173056:raise ValueError()
            if any(not isinstance(key,str) or not re.fullmatch('#[0-9a-fA-F]{6}',key) or not isinstance(value,dict) or not isinstance(value.get('code'),str) for key,value in mapping.items()):raise ValueError()
            if any(value is not None and (not isinstance(value,str) or value not in mapping) for value in project['grid']):raise ValueError()
            if any(type(index) is not int or not 0<=index<w*h or (code is not None and not isinstance(code,str)) for index,code in project['overrides']):raise ValueError()
        except (TypeError,ValueError):raise ValueError('项目配色或改色数据无效。')
        reference=project.get('reference')
        if not isinstance(reference,str) or not reference.startswith('data:image/png;base64,') or len(reference)>30_000_000:raise ValueError('项目参考图无效。')
        if not isinstance(entry.get('png'),str):raise ValueError('图纸 PNG 无效。')
        for value in (reference.split(',',1)[1],entry['png']):
            raw=base64.b64decode(value,validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format!='PNG' or image.width*image.height>40_000_000:
                    raise ValueError('项目图片无效或过大。')
                image.verify()
    raw=json.dumps(bundle,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>LIMIT:raise ValueError('单款可编辑存档超过60MB，请减少规格后上传。')
    return raw,hashlib.sha256(raw).hexdigest()
