"""Reusable multi-axis design methods and evidence retrieval; no sales-performance claims."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
METHODS=[
 {'id':'clean_information','name':'클린 정보형','visual':'明亮白色背景、清晰产品静物、整齐留白、简洁模块化构图','structure':['value','features','usage','specs'],'anxieties':['상품 식별','사용 방법'],'price_band':'value_to_mid','traffic':['search','marketplace'],'color':'#202820'},
 {'id':'premium_gallery','name':'프리미엄 갤러리형','visual':'深炭黑背景、柔和聚光、精致产品特写、博物馆陈列般克制的高级质感','structure':['desire','design','detail','ownership'],'anxieties':['디자인 품질','가격 납득'],'price_band':'mid_to_premium','traffic':['social','brand'],'color':'#ffffff'},
 {'id':'warm_lifestyle','name':'따뜻한 생활 장면형','visual':'暖米色自然光、真实家居生活环境、产品融入日常、温和材质层次','structure':['situation','usage','benefit','fit'],'anxieties':['생활 공간 적합성','활용 모습'],'price_band':'mid','traffic':['social','discovery'],'color':'#302b25'},
 {'id':'material_macro','name':'소재·디테일 확대형','visual':'中性浅灰背景、产品完整形态与材质微距细节并置、真实表面纹理、精准柔光','structure':['detail','feature','benefit','care'],'anxieties':['소재 감각','마감 상태'],'price_band':'mid_to_premium','traffic':['search','comparison'],'color':'#202820'},
 {'id':'problem_solution','name':'문제·사용 맥락형','visual':'明亮日常环境、通过真实使用情境表达产品用途、明确视觉焦点、不可虚构功效对比或认证','structure':['problem','use_case','benefit','choice'],'anxieties':['필요성','사용 상황'],'price_band':'value_to_mid','traffic':['shortform','discovery'],'color':'#202820'},
 {'id':'gift_narrative','name':'선물·의미 스토리형','visual':'暖象牙白背景、柔和侧光、产品作为心意礼物的静物叙事、简约优雅、不添加未提供的包装或配件','structure':['occasion','meaning','product','recipient'],'anxieties':['선물의 적합성','분위기'],'price_band':'mid_to_premium','traffic':['social','gift_search'],'color':'#342b26'},
 {'id':'comparison_grid','name':'비교·선택 가이드형','visual':'干净浅蓝灰背景、产品不同角度的整齐网格排列、强调同一产品的外观与用途、无未验证参数和假对照产品','structure':['choice_criteria','angles','usage','fit'],'anxieties':['선택 기준','다른 각도 확인'],'price_band':'value_to_mid','traffic':['comparison','search'],'color':'#182e40'},
 {'id':'bold_color','name':'선명한 컬러 캠페인형','visual':'鲜明但克制的单色背景、强烈产品轮廓与对比、现代编辑式留白、无促销爆炸贴','structure':['attention','product','single_value','action'],'anxieties':['첫눈에 상품 파악'],'price_band':'value_to_mid','traffic':['social','shortform'],'color':'#202820'},
]
AXES=['category','persuasion_structure','visual_design','buyer_anxieties','price_band','traffic_source']

def knowledge(limit=18):
 chunks=json.loads((ROOT/'skills/ecommerce-detail-page/references/banye/chunks.json').read_text())
 preferred=['consumer-psychology.md','fbe-sellpoint-model.md','visual-design-rules.md','review-standards.md','detail-page-structure.md','daily-use.md','competitor-research.md','ai-design-rules.md']
 selected=[]
 for name in preferred:
  selected.extend([c for c in chunks if c['path'].endswith(name)][:max(1,limit//len(preferred))])
 # Routing keeps the full corpus locally; not every request needs every category.
 return selected[:limit]

def match_methods(category=None,traffic=None,anxiety=None):
 scored=[]
 for m in METHODS:
  score=(2 if traffic and traffic in m['traffic'] else 0)+(2 if anxiety and anxiety in m['anxieties'] else 0)
  scored.append({'method':m,'fit_score':score,'category':category,'conversion_effect':'not_established'})
 return sorted(scored,key=lambda r:(-r['fit_score'],r['method']['id']))
