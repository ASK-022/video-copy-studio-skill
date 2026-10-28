"""Local image OCR for product material imports; raw images never go to the AI."""
from pathlib import Path
import threading
import warnings

MAX_IMAGES=5
MAX_IMAGE_BYTES=12*1024*1024
MAX_TOTAL_BYTES=30*1024*1024
MAX_PIXELS=30_000_000
_LOCK=threading.Lock()
_ENGINE=None


def image_text(paths,notify=lambda _:None):
    from PIL import Image,ImageOps
    import numpy as np
    global _ENGINE
    texts=[];seen=set()
    with _LOCK:
        if _ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR
            _ENGINE=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
        for i,path in enumerate(paths,1):
            notify(f'本机正在识别第 {i} / {len(paths)} 张商品图片…')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error',Image.DecompressionBombWarning)
                    with Image.open(path) as original:
                        if original.format not in ('PNG','JPEG','WEBP'):raise ValueError('请选择 PNG、JPG 或 WebP 图片。')
                        if original.width*original.height>MAX_PIXELS:raise ValueError('单张图片像素过大，请分成几张截图后导入。')
                        oriented=ImageOps.exif_transpose(original)
                        if 'A' in oriented.getbands() or 'transparency' in oriented.info:
                            rgba=oriented.convert('RGBA');image=Image.new('RGB',rgba.size,'white');image.paste(rgba,mask=rgba.getchannel('A'))
                        else:image=oriented.convert('RGB')
            except (OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:
                raise ValueError('图片无法读取，请重新保存为 PNG、JPG 或 WebP 后导入。') from exc
            if image.width>1600:image=image.resize((1600,max(1,round(image.height*1600/image.width))))
            image_lines=[]
            for top in range(0,image.height,1600):
                crop=image.crop((0,top,image.width,min(image.height,top+1800)))
                if crop.height<30:continue
                result,_=_ENGINE(np.ascontiguousarray(np.asarray(crop)[:,:,::-1]))
                for line in result or []:
                    value=str(line[1]).strip();key=''.join(value.split())
                    if float(line[2])>=.60 and key and key not in seen:
                        seen.add(key);image_lines.append(value)
            if image_lines:texts.append(f'图片 {i}：\n'+'\n'.join(image_lines))
            if sum(map(len,texts))>20000:raise ValueError('识别文字超过 2 万字，请减少图片后分次提取。')
    text='\n\n'.join(texts)
    if not text.strip():raise ValueError('没有识别到清晰文字。请上传含商品名称、包装说明或卖点的清晰图片，或改用商品文案提取。')
    return text
