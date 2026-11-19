"""
지식 그래프 탐색: 질문 슬롯 -> 후보 자료 목록 + 결합 키 + 보류 사유
에이전트가 import 해서 쓰는 모듈. 단독 실행 시 애월 카페 사례를 재현한다.
  python -X utf8 지식그래프/kg_query.py
"""
import os, json, sqlite3, datetime, collections

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(BASE), "data", "graph", "kg.sqlite")
LEVEL = ['좌표', '주소', '법정동', '읍면동', '시군구', '시도']


class KG:
    def __init__(self, db=DB):
        con = sqlite3.connect(db)
        self.n = {i: dict(type=t, **json.loads(p)) for i, t, p in con.execute('select id,type,props from nodes')}
        self.out = collections.defaultdict(list); self.inn = collections.defaultdict(list)
        for a, b, t, p in con.execute('select src,dst,type,props from edges'):
            e = dict(src=a, dst=b, type=t, **json.loads(p))
            self.out[a].append(e); self.inn[b].append(e)
        self.con = con
        self.concepts = {v['name']: k for k, v in self.n.items() if v['type'] == 'Concept'}
        self.syn = {}
        for k, v in self.n.items():
            if v['type'] == 'Concept':
                for s in [v['name']] + (v.get('synonyms') or []):
                    self.syn.setdefault(s.replace(' ', ''), k)
            if v['type'] == 'Place':
                for s in [v['name']] + (v.get('aliases') or []):
                    self.syn.setdefault('place:' + s, k)

    # --- 이름 맞추기 ---
    def concept(self, word):
        return self.concepts.get(word) or self.syn.get(str(word).replace(' ', ''))

    def place(self, word):
        k = self.syn.get('place:' + word)
        if k:
            return k, None
        try:
            from rapidfuzz import process
            names = [v['name'] for v in self.n.values() if v['type'] == 'Place' and v.get('level') == '읍면동']
            best = process.extractOne(word, names)
            return None, best and best[0]
        except ImportError:
            import difflib
            names = [v['name'] for v in self.n.values() if v['type'] == 'Place' and v.get('level') == '읍면동']
            m = difflib.get_close_matches(word, names, n=1)
            return None, m[0] if m else None

    def keys(self, did):
        sp, tm, cols = set(), set(), []
        for e in self.out[did]:
            if e['type'] != 'HAS_COLUMN':
                continue
            c = self.n[e['dst']]; cols.append((e['dst'], c))
            if c['role'] == '공간키' and c.get('grain'):
                sp.add(c['grain'])
            if c['role'] == '시간키' and c.get('grain'):
                tm.add(c['grain'])
        return sp, tm, cols

    def joinable(self, a, b):
        for e in self.out[a] + self.inn[a]:
            if e['type'] == 'JOINABLE' and {e['src'], e['dst']} == {a, b}:
                return e
        return None

    # --- 핵심: 후보 자료 찾기 ---
    def find_datasets(self, concepts, place_level='읍면동', period=None, top=5):
        """concepts: 개념 이름 목록, period: ('YYYY-MM-DD','YYYY-MM-DD') 또는 None(최신 우선)"""
        need = LEVEL.index(place_level) if place_level else None
        result = {}
        for cname in concepts:
            cid = self.concept(cname)
            if not cid:
                result[cname] = dict(error='개념 어휘에 없음'); continue
            cands = {}
            for e in self.inn[cid]:
                if e['type'] == 'MEASURES':
                    did = f"ds:{self.n[e['src']]['dataset']}"; cands.setdefault(did, set()).add(e['src'])
                elif e['type'] == 'ABOUT':
                    cands.setdefault(e['src'], set())
            rows = []
            for did, mcols in cands.items():
                d = self.n[did]; sp, tm, _ = self.keys(did)
                lv = [LEVEL.index(g) for g in sp if g in LEVEL]
                finest = min(lv) if lv else None
                reason = []
                if need is None:
                    pass
                elif finest is None:
                    reason.append('지역 키 없음')
                elif finest > need:
                    reason.append(f'지역 단위가 {LEVEL[finest]}까지만 있음')
                conv = '법정동→행정동 변환' if need is not None and finest == LEVEL.index('법정동') and need == LEVEL.index('읍면동') else None
                end = d.get('auto_update_verified_end') or d.get('period_end') or ''
                end = '' if str(end).startswith('9999') else end
                scope = [self.n[c].get('denominator_scope') for c in mcols if self.n[c].get('denominator_scope')]
                if scope:
                    reason_soft = f"측정 범위 제한: {scope[0]}"
                else:
                    reason_soft = None
                if period and (str(d.get('period_start')) > period[1] or (end and end < period[0])):
                    reason.append(f"기간 밖({d.get('period_start')}~{end})")
                rows.append(dict(id=did, title=d['title'], access=d['access'], verified=bool(d.get('verified')),
                                 period=f"{d.get('period_start')} ~ {end or '자동갱신(미확인)'}", space=sorted(sp), time=sorted(tm),
                                 measure_cols=[self.n[c]['name'] for c in mcols], via='컬럼' if mcols else '자료 주제',
                                 conversion=conv, caution=reason_soft, excluded=reason))
            ok = [r for r in rows if not r['excluded']]
            ok.sort(key=lambda r: r['period'].split(' ~ ')[-1] if r['period'][-1].isdigit() else '0000', reverse=True)
            ok.sort(key=lambda r: (r['caution'] is not None, not r['verified']))
            exc = [r for r in rows if r['excluded']]
            exc.sort(key=lambda r: (not all(x.startswith('기간 밖') for x in r['excluded']), not r['verified'], r['via'] != '컬럼'))
            result[cname] = dict(candidates=ok[:top], excluded=exc[:top], n_total=len(rows))
        return result

    def plan_pairs(self, found):
        names = list(found)
        out = []
        if len(names) < 2:
            return out
        A = [c['id'] for c in found[names[0]].get('candidates', [])]
        B = [c['id'] for c in found[names[1]].get('candidates', [])]
        for a in A:
            for b in B:
                if a == b:
                    out.append(dict(a=a, b=b, same_dataset=True)); continue
                e = self.joinable(a, b)
                out.append(dict(a=a, b=b, joinable=bool(e), **({k: e.get(k) for k in ('space_key', 'conversion', 'time_key', 'overlap', 'common_dims', 'cautions', 'status')} if e else {})))
        return out


if __name__ == '__main__':
    kg = KG()
    print('질문: 애월에 카페 많아? 한림보다 경쟁 심해? 점포당 매출도 궁금해')
    for w in ('애월', '노현동'):
        print(' 지명', w, '→', kg.place(w))
    f = kg.find_datasets(['점포수', '방문인구'], '읍면동')
    for c, v in f.items():
        print(f'\n[{c}] 후보 {v["n_total"]}건 중 상위')
        for r in v['candidates']:
            print('  ', r['id'], r['title'][:30], '|', r['access'], '|', r['period'], '|', r['measure_cols'][:3] or r['via'], '|', '검증' if r['verified'] else '', r['conversion'] or '', r['caution'] or '')
    print('\n[결합 확인]')
    for p in kg.plan_pairs(f)[:4]:
        print('  ', {k: v for k, v in p.items() if k != 'cautions'})
    print('\n[점포당 매출: 카드이용금액 ÷ 점포수]')
    g = kg.find_datasets(['카드이용금액', '점포수'], '읍면동', period=('2025-09-01', '2025-09-30'))
    for c, v in g.items():
        print(f'  {c}: 기간 내 후보 {len(v["candidates"])}건, 제외 예:', [(r['id'], r['excluded']) for r in v['excluded'][:3]])
    e = kg.joinable('ds:746', 'ds:793')
    print('  746 ↔ 793 결합:', e or '불가(기간 불일치) → 점포당 매출 보류')
