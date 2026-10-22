"""Blank image layout contract. Approved copy stays in editable layers, outside prompts."""
import copy,math

MODE='blank-background-v1'

def validate_layout(layout,job,width,height):
    if set(layout)!={'mode','width','height','job_id','slots'} or layout['mode']!=MODE:raise ValueError('Invalid layout contract')
    if (layout['width'],layout['height'],layout['job_id'])!=(width,height,job['job_id']):raise ValueError('Layout dimensions or job mismatch')
    phrases=[p.strip() for p in job['cut']['이미지 내 삽입 문구'].split('/') if p.strip()]
    if [s['text'] for s in layout['slots']]!=phrases:raise ValueError('Layout must preserve approved copy in order')
    ids=set()
    for slot in layout['slots']:
        if set(slot)!={'id','text','x','y','width','height'} or slot['id'] in ids:raise ValueError('Invalid slot')
        ids.add(slot['id'])
        for key,limit in [('x',width),('y',height),('width',width),('height',height)]:
            v=slot[key]
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not (0 if key in ['x','y'] else 1)<=v<=limit:raise ValueError('Invalid slot geometry')
        if slot['x']+slot['width']>width or slot['y']+slot['height']>height:raise ValueError('Slot outside artboard')
    for i,s in enumerate(layout['slots']):
        for t in layout['slots'][i+1:]:
            if s['x']<t['x']+t['width'] and t['x']<s['x']+s['width'] and s['y']<t['y']+t['height'] and t['y']<s['y']+s['height']:raise ValueError('Overlapping copy slots')
    return layout

def plan_layout(job,width=1536,height=2304,override=None):
    if override is not None:return validate_layout(copy.deepcopy(override),job,width,height)
    phrases=[p.strip() for p in job['cut']['이미지 내 삽입 문구'].split('/') if p.strip()]
    slots=[]
    for i,text in enumerate(phrases):
        # Headline above, remaining copy below; middle half stays available for product.
        if i==0:y,h=round(height*.06),round(height*.18)
        else:
            n=len(phrases)-1;cell=height*.24/n;y=round(height*.72+(i-1)*cell);h=max(1,math.floor(cell*.88))
        slots.append({'id':f'copy_{i+1}','text':text,'x':round(width*.065),'y':y,'width':round(width*.87),'height':h})
    return validate_layout({'mode':MODE,'width':width,'height':height,'job_id':job['job_id'],'slots':slots},job,width,height)

def background_prompt(job,directions,layout):
    zones=[{k:round(s[k]/(layout['width'] if k in ['x','width'] else layout['height'])*100,2) for k in ['x','y','width','height']} for s in layout['slots']]
    import json
    direction=directions[job['job_id']]
    if any(s['text'] in direction for s in layout['slots']):raise ValueError('Approved copy leaked into visual direction')
    return ('高端韩国电商竖版产品背景图。'+direction+'。保持参考图片中产品的形状、颜色和材质。'
            '不要添加标题、文案、文字、字母、数字、徽章、水印、占位符或可见框线，不复制参考图中的广告文字。产品本身的原有印刷和图案保持原样。'
            '以下矩形区域采用画面百分比坐标，必须留作干净的低细节空白背景，不能放产品、人物或装饰；图中不要画出这些矩形。产品主体放在不与空白区域重叠的中间区域。'
            +json.dumps(zones,ensure_ascii=False)+'。')

def text_layers(layout):
    return [{**s,'color':'#202820','font_size':min(68,max(12,round(s['height']*.42))),
             'min_font_size':8,'weight':700 if i==0 else 400,'align':'center','line_height':1.35,'auto_fit':True}
            for i,s in enumerate(layout['slots'])]
