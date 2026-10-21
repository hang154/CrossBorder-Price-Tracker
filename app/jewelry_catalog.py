"""Qwen-planned, checkpointed overseas catalog research and evidence collection."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

import httpx

from app.sourcing_agent import BASE, MODEL, connection, tool, validate_arguments
from app.sourcing_pipeline import atomic_json, digest


TOPICS = ['호안석 비휴 팔찌', '시트린/황수정 팔찌 천연색·가열처리 판매 주장',
    '연옥/화전옥 팔찌', '비취 팔찌 감정서 주장', '흑요석 비휴 팔찌', '홍마노 띠별 팔찌',
    '백수정/자수정 팔찌', '형석 팔찌', '청금석 팔찌', '녹색 어벤츄린 팔찌', '황철석 팔찌',
    '가넷/문스톤 탄생석 팔찌', '유리/레진/인조석 저가 팔찌', '925 실버 비휴 반지',
    '스테인리스/티타늄 육자진언 회전 반지', '황동/동전 재물 상징 반지', '옥/마노 반지',
    '도금·골드필드 반지', '백단/샌달우드 108 염주', '침향 108 염주', '자단 18/108 염주',
    '성월 보리자 108 염주', '금강/연화 보리자 염주', '복숭아나무 액막이 팔찌',
    '천주교 천연석 묵주 59알', '천주교 스테인리스 묵주', '유리/수정 묵주',
    '정교회 양모 기도 매듭 팔찌', '문수보살/문창 학업 기원 장식',
    '12지신 황동/실버 참 부자재', '비휴/엽전 참 부자재', '페후 룬/별자리 참 부자재',
    '12지신 붉은 실 매듭 팔찌', '각인/소원 기념 패키지용 장신구',
    '호안석/시트린 DIY 비즈 등급별', '무늬/색상 다른 전통 원석 염주 선물 세트']


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def plan(out, brief):
    props = {k: {'type': 'string', 'minLength': 1} for k in
             ['id', 'label_ko', 'form', 'material', 'query_zh', 'query_en', 'quality_target']}
    schema = tool('run_catalog_searches', 'Plan the broad requested real marketplace searches. Each topic executes on BOTH 1688 and Alibaba.com, reading public listing cards and preserving prices, MOQ and supplier evidence. No supplier messages or orders.', {
        'topics': {'type': 'array', 'minItems': 30, 'items': {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}}}, ['topics'])
    prompt = ('Create 36 diverse sourcing topics for bracelets, rings, Catholic rosaries and Buddhist malas, '
        'plus relevant charms/components. Use each supplied family once, combine only if redundant. '
        'Make genuine Chinese wholesale queries and English Alibaba queries. Include budget, middle and '
        'claimed premium/certificate/925/wood-species options rather than only cheapest products. '
        'Material purity, certificates, blessing by monks, supernatural outcomes and investment success '
        'are unverified claims, never facts. User wants wealth/investment symbolism first, then study/career, '
        'New Year wishes, zodiac personalization. Keep religious traditions distinct. '
        'Avoid repeating identical query. IDs safe lowercase ASCII hyphens. Invoke the tool.\n'
        +json.dumps(TOPICS, ensure_ascii=False)+'\nUser context:\n'+brief)
    with httpx.Client(timeout=240) as client:
        r = client.post(BASE+'/chat/completions', headers=connection(), json={
            'model': MODEL, 'messages': [{'role': 'system', 'content': 'You are a local sourcing agent. Plan observable marketplace research. Do not fabricate products, seller quality or ritual services.'}, {'role': 'user', 'content': prompt}],
            'tools': [schema], 'tool_choice': 'auto', 'parallel_tool_calls': False,
            'max_tokens': 12000, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}})
        r.raise_for_status()
        payload = r.json()
    atomic_json(out/'qwen-plan-response.json', payload)
    if payload['choices'][0]['finish_reason'] == 'length':
        raise ValueError('Qwen plan truncated; saved response, no searches launched')
    calls = payload['choices'][0]['message'].get('tool_calls') or []
    if len(calls) != 1 or calls[0]['function']['name'] != 'run_catalog_searches':
        raise ValueError('Expected Qwen native run_catalog_searches call')
    args = json.loads(calls[0]['function']['arguments'])
    validate_arguments(args, schema['function']['parameters'])
    ids = [t['id'] for t in args['topics']]
    if len(set(ids)) != len(ids) or len(ids) > 40 or any(not x or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in x) for x in ids):
        raise ValueError('Expected unique safe topic IDs, maximum 40')
    atomic_json(out/'qwen-plan.json', args)
    return args


def collect(out, prefix, brief, limit):
    planning = json.loads((out/'qwen-plan.json').read_text()) if (out/'qwen-plan.json').exists() else plan(out, brief)
    path = out/'catalog.json'
    identity = digest({'plan': planning, 'limit': limit, 'prefix': prefix})
    state = json.loads(path.read_text()) if path.exists() else {'model': MODEL, 'base_url': BASE, 'started_at_utc': timestamp(), 'fingerprint': identity, 'topics': planning['topics'], 'jobs': []}
    if state['fingerprint'] != identity:
        raise ValueError('Changed collection inputs; choose a fresh directory')
    blocked = set()
    for topic in planning['topics']:
        for site, language in [('1688', 'zh'), ('alibaba', 'en')]:
            key = topic['id']+'-'+site
            old = next((j for j in state['jobs'] if j['key'] == key), None)
            if old and old['state'] == 'collected':
                raw = Path(old['file'])
                if hashlib.sha256(raw.read_bytes()).hexdigest() != old['sha256']:
                    raise ValueError('Changed saved source response')
                continue
            job = {'key': key, 'topic_id': topic['id'], 'site': site, 'query': topic['query_'+language], 'state': 'running', 'started_at_utc': timestamp()}
            if site in blocked:
                job.update(state='blocked', error='Earlier verification/temporary restriction on this site; no repeated requests')
            else:
                try:
                    r = subprocess.run([*prefix, site, 'search', job['query'], '--limit', str(limit), '-f', 'json'], capture_output=True, text=True, timeout=100)
                    raw = out/(key+'.json')
                    raw.write_text(r.stdout)
                    job.update(file=str(raw.resolve()), sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), exit_code=r.returncode)
                    data = json.loads(r.stdout)
                    if r.returncode or not data.get('ok') or not isinstance(data.get('data'), list) or not data['data']:
                        raise ValueError(str(data.get('error', 'No observed product rows')))
                    job.update(state='collected', rows=data['data'])
                except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                    job.update(state='failed', error=str(exc))
                    if any(x in str(exc).lower() for x in ['verification', 'captcha', 'slide to verify', '验证码', 'temporarily restricted']):
                        blocked.add(site)
            job['finished_at_utc'] = timestamp()
            if old:
                job['previous_attempt'] = {k: v for k, v in old.items() if k not in ['rows', 'previous_attempt']}
                state['jobs'][state['jobs'].index(old)] = job
            else:
                state['jobs'].append(job)
            state['updated_at_utc'] = timestamp()
            atomic_json(path, state)
            print(json.dumps({'topic': topic['label_ko'], 'site': site, 'state': job['state'], 'rows': len(job.get('rows', []))}, ensure_ascii=False), flush=True)
    return state


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--opencli-main', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--brief-file', type=Path, required=True)
    p.add_argument('--limit', type=int, default=12)
    a = p.parse_args()
    if not 1 <= a.limit <= 50:
        p.error('limit must be 1–50')
    a.output_dir.mkdir(parents=True, exist_ok=True)
    collect(a.output_dir.resolve(), ['node', str(a.opencli_main.resolve())], a.brief_file.read_text(), a.limit)


if __name__ == '__main__':
    main()
