"""데이터 지도(jeju-agent 지식 그래프 이식). data/data_map.json만 읽고, vis-network를 인라인으로 넣어 오프라인에서 그린다.

- home_html(): 첫 화면 지도. 대표 자료 20개 → 분야·개념 원을 누르면 관련 자료 6개씩 펼침(브라우저 안에서 처리, 서버 왕복 없음)
- answer_html(hub_ids, places): 이 답변에 쓴 자료와 그 사이 결합 관계
- show_home() / show_answer(): Streamlit에 바로 그리기
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data" / "data_map.json"
VIS = Path(__file__).resolve().parent / "vendor" / "vis-network.min.js"
HUB = "https://jejudatahub.net/data/view/data/{}"


@lru_cache(maxsize=1)
def bundle() -> dict:
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _vis() -> str:
    return VIS.read_text(encoding="utf-8")


def _node(did: str, group: str = "dataset") -> dict:
    d = bundle()["ds"][did]
    return dict(id=did, label=d["l"], group=group, url=HUB.format(d["h"]),
                info=dict(title=d["t"], hub_id=d["h"], category=bundle()["names"].get(d["c"], ""), access=d["a"],
                          period=d["p"], desc=d["d"], topics=d["tp"]))


def answer_graph(hub_ids: list[int], places: list[str] | None = None,
                 candidates: dict[int, str] | None = None, joins: list | None = None) -> dict:
    """이 답변에 쓴 허브 자료 → 노드·관계. 그래프에 없는 번호(외부 데이터 등)는 건너뛴다.
    candidates: 후보로 검토했지만 쓰지 않은 자료 {허브ID: 제외 사유} (범용 경로에서 사용)."""
    b = bundle()
    used = [f"ds:{h}" for h in dict.fromkeys(hub_ids) if f"ds:{h}" in b["ds"]]
    nodes, edges = {}, []
    for h, why in (candidates or {}).items():
        did = f"ds:{h}"
        if did in b["ds"] and did not in used:
            n = _node(did, "candidate")
            n["info"]["desc"] = f"[사용하지 않음] {why}\n\n" + n["info"]["desc"]
            nodes[did] = n
            for k in b["ds"][did]["k"][:1]:
                nodes.setdefault(k, dict(id=k, label=b["names"].get(k, k), group="concept"))
                edges.append(dict(**{"from": did, "to": k}, label="후보"))
    for did in used:
        nodes[did] = _node(did, "used")
        for k in b["ds"][did]["k"][:2]:
            nodes.setdefault(k, dict(id=k, label=b["names"].get(k, k), group="concept"))
            edges.append(dict(**{"from": did, "to": k}, label="알 수 있음"))
        for p in places or []:
            if b["ds"][did]["g"] in ("grain:space:읍면동", "grain:space:법정동"):
                nodes.setdefault(f"place:{p}", dict(id=f"place:{p}", label=p, group="place"))
                edges.append(dict(**{"from": did, "to": f"place:{p}"}, label="지역"))
    for i, a in enumerate(used):
        for c in used[i + 1:]:
            lab = b["joins"].get(f"{min(a, c)}|{max(a, c)}") or next(
                (j[2] for j in joins or [] if {f"ds:{j[0]}", f"ds:{j[1]}"} == {a, c}), None)
            if lab:
                edges.append(dict(**{"from": a, "to": c}, label=lab, kind="join"))
    return dict(nodes=list(nodes.values()), edges=edges)


_JS = r"""
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const FONT = '"Pretendard GOV","Noto Sans KR","Malgun Gothic",sans-serif';
const NODE = {
  category:{bg:'#164756', bd:'#0f3442', fc:'#fff', size:40},
  dataset:{bg:'#0081A7', bd:'#00607d', fc:'#fff', size:42},
  used:{bg:'#DD6418', bd:'#a9470d', fc:'#fff', size:42, bw:4},
  candidate:{bg:'#e6eef0', bd:'#b9ccd2', fc:'#456570', size:34},
  concept:{bg:'#d6f1ec', bd:'#7fbfb6', fc:'#164756', size:34},
  grain:{bg:'#fbe3c4', bd:'#e0a458', fc:'#7a4a12', size:32},
  place:{bg:'#fbe3c4', bd:'#e0a458', fc:'#7a4a12', size:32},
};
const short = (t, n) => { t = String(t || ''); return t.length > n ? t.slice(0, n) + '…' : t; };
function wrap(t) { const w = t.split(/\s+/), out = []; let line = ''; w.forEach(x => { if ((line + ' ' + x).trim().length > 7 && line) { out.push(line); line = x; } else line = (line + ' ' + x).trim(); }); out.push(line); return out.slice(0, 3).join('\n'); }
function visNode(n) {
  const s = NODE[n.group] || NODE.dataset, isDs = n.group === 'dataset' || n.group === 'used' || n.group === 'candidate';
  const full = n.group === 'category' || n.group === 'hub';
  return {id:n.id, label: isDs ? wrap(short(n.label, 16)) : full ? n.label : short(n.label, 7), title: n.info ? n.info.title : n.label,
    url:n.url, info:n.info, group0:n.group, shape:'circle', widthConstraint:{minimum:s.size*2, maximum:s.size*2},
    color:{background:s.bg, border:s.bd, highlight:{background:s.bg, border:'#1B2421'}, hover:{background:s.bg, border:'#1B2421'}},
    borderWidth:s.bw || 2, font:{color:s.fc, size:14, face:FONT}};
}
function visEdge(e) {
  const strong = e.kind === 'join';
  return {id:e.from + '>' + e.to, from:e.from, to:e.to, label:e.label || '', arrows:{to:{enabled:!strong, scaleFactor:.5}},
    color:{color: strong ? '#DD6418' : '#9fb7bf', highlight:'#164756'}, width: strong ? 2.5 : 1, dashes: false,
    font:{size:12, color: strong ? '#a9470d' : '#456570', strokeWidth:3, strokeColor:'#fff', align:'middle', face:FONT}, smooth:false};
}
const OPTS = {physics:{solver:'forceAtlas2Based', forceAtlas2Based:{gravitationalConstant:-55, centralGravity:.012, springLength:95, springConstant:.08, avoidOverlap:.9},
  stabilization:{iterations:500}}, interaction:{hover:true, tooltipDelay:80, zoomView:true, dragView:true, keyboard:{enabled:true, bindToWindow:false}}, layout:{randomSeed:7}};
const nodes = new vis.DataSet(), edges = new vis.DataSet();
function add(g) {
  g.nodes.forEach(n => { const v = visNode(n); nodes.get(n.id) ? nodes.update(v) : nodes.add(v); });
  g.edges.forEach(e => { const v = visEdge(e); if (!edges.get(v.id)) edges.add(v); });
}
function widen(net) {
  const box = $('g'), pos = net.getPositions(), ids = Object.keys(pos);
  if (!ids.length) return;
  const xs = ids.map(i => pos[i].x), ys = ids.map(i => pos[i].y);
  const w = Math.max(...xs) - Math.min(...xs) || 1, h = Math.max(...ys) - Math.min(...ys) || 1;
  const k = Math.min(2.2, Math.max(1, (box.clientWidth / box.clientHeight) * h / w));
  net.setOptions({physics:{enabled:false}});
  ids.forEach(i => net.moveNode(i, pos[i].x * k, pos[i].y));
  net.fit({animation:false});
}
function addZoom(net) {
  const z = document.createElement('div'); z.className = 'zoom';
  z.innerHTML = '<button type="button" title="확대">＋</button><button type="button" title="축소">－</button><button type="button" title="전체 보기">⤢</button>';
  const [bin, bout, bfit] = z.querySelectorAll('button');
  const step = f => net.moveTo({scale: Math.min(4, Math.max(0.15, net.getScale() * f)), animation: {duration: 250}});
  bin.onclick = () => step(1.3); bout.onclick = () => step(1 / 1.3); bfit.onclick = () => net.fit({animation: {duration: 400}});
  document.getElementById('wrap').appendChild(z);
}
function showInfo(n) {
  const d = n.info || {};
  $('info').innerHTML = `<button class="x" type="button">×</button><h3>${esc(d.title)}</h3>
    <div class="meta">허브 ID ${esc(d.hub_id)} · ${esc(d.category)} · ${esc(d.access)}<br>기간 ${esc(d.period)}</div>
    <div>${esc(d.desc)}</div>
    ${(d.topics || []).length ? '<div class="tags">' + d.topics.map(t => `<span>${esc(t)}</span>`).join('') + '</div>' : ''}
    <a class="btn" href="${esc(n.url)}" target="_blank" rel="noopener">허브에서 원자료 보기 ↗</a>`;
  $('info').hidden = false;
  $('info').querySelector('.x').onclick = () => { $('info').hidden = true; };
}
"""

_SEARCH_JS = r"""
// 검색: 띄어쓰기로 나눈 낱말이 모두 들어 있어야 함(밑줄·띄어쓰기 차이 무시).
// 제목 4 · 주제 2 · 알 수 있는 것 2 · 분야 1 · 설명 1점. 제목·주제·개념에서 맞는 자료가 있으면 설명에만 나오는 자료는 뺀다.
// 업종 이름(카페·편의점 등)이면 업종 구분이 있는 자료(상가·카드·음식점 목록 등)를 맨 앞에 둔다.
function rankSearch(q) {
  const norm = s => String(s || '').toLowerCase().replace(/[_\s]+/g, '');
  const toks = String(q).trim().split(/\s+/).map(norm).filter(Boolean);
  const isInd = (B.ind || []).some(a => norm(a) === norm(q));
  const scored = [];
  Object.keys(B.ds).forEach(id => {
    const d = B.ds[id];
    if (isInd && (B.ind_ds || []).includes(id)) { scored.push([id, 20, true]); return; }
    const T = norm(d.t), P = norm((d.tp || []).join(' ')), K = norm(d.k.map(k => B.names[k] || '').join(' ')), D = norm(d.d), C = norm(B.names[d.c]);
    let s = 0, strong = true;
    for (const w of toks) {
      const hard = (T.includes(w) ? 4 : 0) + (P.includes(w) ? 2 : 0) + (K.includes(w) ? 2 : 0);
      const v = hard + (D.includes(w) ? 1 : 0) + (C.includes(w) ? 1 : 0);
      if (!v) return;
      if (!hard) strong = false;
      s += v;
    }
    scored.push([id, s + B.ds[id].s / 10, strong]);
  });
  const anyStrong = scored.some(x => x[2]);
  const kept = anyStrong ? scored.filter(x => x[2]) : scored;
  kept.sort((a, b) => b[1] - a[1]);
  return {hits: kept.map(x => x[0]), dropped: scored.length - kept.length};
}
"""

_HOME_JS = r"""
const B = DATA, HUBURL = 'https://jejudatahub.net/data/view/data/';
const CATS = {};
Object.entries(B.ds).forEach(([id, d]) => { if (d.c) (CATS[d.c] = CATS[d.c] || []).push(id); });
const CAT_IDS = Object.keys(CATS).sort((a, b) => CATS[b].length - CATS[a].length);
const order = Object.keys(B.ds).sort((a, b) => B.ds[b].s - B.ds[a].s);
NODE.hub = {bg:'#0B3B4F', bd:'#06283a', fc:'#fff', size:56, bw:3};
function dsNode(id, group) { const d = B.ds[id]; return {id, label:d.l, group:group || 'dataset', url:HUBURL + d.h,
  info:{title:d.t, hub_id:d.h, category:B.names[d.c] || '', access:d.a, period:d.p, desc:d.d, topics:d.tp}}; }
let net = null, mode = 'overview';
function draw(g, iters, small) {
  nodes.clear(); edges.clear(); add(g);
  nodes.update(nodes.get().map(n => ({id:n.id, fixed:false})));
  if (small) nodes.update(nodes.get().filter(n => n.group0 === 'dataset').map(n => ({id:n.id, widthConstraint:{minimum:46, maximum:46}, font:{size:10, color:'#fff'}})));
  if (!net) {
    net = new vis.Network($('g'), {nodes, edges}, OPTS);
    addZoom(net);
    net.on('click', onClick);
    net.on('hoverNode', () => { $('g').style.cursor = 'pointer'; });
    net.on('blurNode', () => { $('g').style.cursor = 'default'; });
  }
  net.setOptions({physics:{enabled:true, stabilization:{iterations:iters}}});
  net.stabilize(iters);
  net.once('stabilizationIterationsDone', () => { net.setOptions({physics:{enabled:false}}); net.fit({animation:false}); });
}
function setActive(key) {
  document.querySelectorAll('#bar .cat').forEach(b => b.classList.toggle('on', b.dataset.k === key));
}
function overview() {
  mode = 'overview'; setActive('all'); $('info').hidden = true;
  const g = {nodes:[{id:'hub', label:'제주데이터허브\n' + B.total.toLocaleString() + '종', group:'hub'}], edges:[]};
  CAT_IDS.forEach(c => {
    const n = CATS[c].length, sz = Math.round(34 + Math.sqrt(n) * 2.6);
    g.nodes.push({id:c, label:B.names[c] + '\n' + n + '종', group:'category', size:sz});
    g.edges.push({from:'hub', to:c, label:''});
  });
  // 겹치지 않게 원형으로 고정 배치(큰 분야는 바깥으로 조금 더 멀리)
  nodes.clear(); edges.clear(); add(g);
  const R = 210;
  nodes.update([{id:'hub', x:0, y:0, fixed:true, font:{size:17, color:'#fff'}}].concat(g.nodes.filter(n => n.size).map((n, i) => {
    const a = -Math.PI / 2 + i * 2 * Math.PI / CAT_IDS.length, r = R + (n.size - 50) * 0.8;
    return {id:n.id, x:Math.round(r * Math.cos(a)), y:Math.round(r * Math.sin(a)), fixed:true,
            widthConstraint:{minimum:n.size * 2, maximum:n.size * 2}, font:{size:17, color:'#fff'}};
  })));
  if (!net) {
    net = new vis.Network($('g'), {nodes, edges}, OPTS);
    addZoom(net); net.on('click', onClick);
    net.on('hoverNode', () => { $('g').style.cursor = 'pointer'; });
    net.on('blurNode', () => { $('g').style.cursor = 'default'; });
  }
  net.setOptions({physics:{enabled:false}});
  setTimeout(() => net.fit({animation:false}), 50);
  $('cnt').textContent = `전체 ${B.total.toLocaleString()}개 자료 · 분야 ${CAT_IDS.length}개 — 분야 원이나 위 버튼을 누르면 그 분야 자료가 모두 펼쳐집니다`;
}
function category(c) {
  mode = c; setActive(c); $('info').hidden = true;
  const ids = CATS[c], g = {nodes:[{id:c, label:B.names[c] + '\n' + ids.length + '종', group:'category'}], edges:[]};
  ids.forEach(id => { g.nodes.push(dsNode(id)); g.edges.push({from:id, to:c, label:''}); });
  draw(g, Math.min(300, 80 + ids.length), ids.length > 60);
  $('cnt').textContent = `${B.names[c]} 자료 ${ids.length}개 — 자료를 누르면 설명과 '알 수 있는 것'이 붙습니다 · 휠·＋로 확대하면 이름이 크게 보입니다`;
}
function search(q) {
  q = (q || '').trim().toLowerCase();
  if (!q) return overview();
  mode = 'search'; setActive(''); $('info').hidden = true;
  const R = rankSearch(q), hit = R.hits;
  const show = hit.slice(0, 80), g = {nodes:[], edges:[]}, seen = new Set();
  show.forEach(id => {
    const c = B.ds[id].c;
    if (c && !seen.has(c)) { seen.add(c); g.nodes.push({id:c, label:B.names[c], group:'category'}); }
    g.nodes.push(dsNode(id, 'used'));
    if (c) g.edges.push({from:id, to:c, label:''});
  });
  if (!show.length) { nodes.clear(); edges.clear(); $('cnt').textContent = `'${q}' 검색 결과가 없습니다`; return; }
  draw(g, 200, show.length > 40);
  $('cnt').textContent = `'${q}' 검색 결과 ${hit.length}개` + (hit.length > 80 ? ' (관련도 높은 80개 표시)' : '') + ' — 주황 원이 검색된 자료입니다'
    + (R.dropped ? ` · 설명에만 '${q}'이(가) 나오는 자료 ${R.dropped}개는 뺐습니다` : '');
}
function expand(n) {
  const d = B.ds[n.id], pos = net.getPositions([n.id])[n.id];
  const extra = {nodes:[], edges:[]};
  d.k.slice(0, 3).forEach((k, i) => {
    if (!nodes.get(k)) extra.nodes.push(Object.assign({id:k, label:B.names[k] || k, group:'concept'}, {x:pos.x + 90 * Math.cos(i * 2.1), y:pos.y + 90 * Math.sin(i * 2.1)}));
    extra.edges.push({from:n.id, to:k, label:'알 수 있음'});
  });
  if (d.g && !nodes.get(d.g)) { extra.nodes.push({id:d.g, label:B.names[d.g], group:'grain', x:pos.x - 90, y:pos.y + 60}); }
  if (d.g) extra.edges.push({from:n.id, to:d.g, label:'지역 단위'});
  extra.nodes.forEach(x => { const v = visNode(x); v.x = x.x; v.y = x.y; nodes.add(v); });
  extra.edges.forEach(e => { const v = visEdge(e); if (!edges.get(v.id)) edges.add(v); });
}
function conceptDatasets(k) {
  const pos = net.getPositions([k])[k];
  const ids = order.filter(id => B.ds[id].k.includes(k) && !nodes.get(id)).slice(0, 8);
  ids.forEach((id, i) => {
    const v = visNode(dsNode(id)); v.x = pos.x + 120 * Math.cos(i * 0.8); v.y = pos.y + 120 * Math.sin(i * 0.8); nodes.add(v);
    const e = visEdge({from:id, to:k, label:'알 수 있음'}); if (!edges.get(e.id)) edges.add(e);
  });
  $('cnt').textContent = `'${B.names[k] || k}'을(를) 알 수 있는 자료 ${ids.length}개를 더 펼쳤습니다`;
}
function onClick(p) {
  if (!p.nodes.length) { $('info').hidden = true; return; }
  const n = nodes.get(p.nodes[0]);
  if (n.id === 'hub') return overview();
  if (n.group0 === 'category') return category(n.id);
  if (n.group0 === 'dataset' || n.group0 === 'used') { showInfo(n); expand(n); return; }
  if (n.group0 === 'concept') return conceptDatasets(n.id);
}
const bar = $('bar');
bar.innerHTML = '<input id="q" type="search" placeholder="자료 검색 (예: 카페, 버스, 관광객, 기온)"><button id="go" type="button">검색</button>'
  + '<span class="cats"><button class="cat on" data-k="all" type="button">전체 분야</button>'
  + CAT_IDS.map(c => `<button class="cat" data-k="${c}" type="button">${esc(B.names[c])} <b>${CATS[c].length}</b></button>`).join('') + '</span>';
$('go').onclick = () => search($('q').value);
$('q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) search($('q').value); });
bar.querySelectorAll('.cat').forEach(b => b.onclick = () => b.dataset.k === 'all' ? overview() : category(b.dataset.k));
overview();
"""

_HOME_JS_CLASSIC = r"""
const B = DATA, pages = {};
function dsNode(id, group) { const d = B.ds[id]; return {id, label:d.l, group:group || 'dataset', url:'https://jejudatahub.net/data/view/data/' + d.h,
  info:{title:d.t, hub_id:d.h, category:B.names[d.c] || '', access:d.a, period:d.p, desc:d.d, topics:d.tp}}; }
function links(id, g) {
  const d = B.ds[id];
  if (d.c) { g.nodes.push({id:d.c, label:B.names[d.c], group:'category'}); g.edges.push({from:id, to:d.c, label:'분야'}); }
  d.k.slice(0, 2).forEach(k => { g.nodes.push({id:k, label:B.names[k] || k, group:'concept'}); g.edges.push({from:id, to:k, label:'알 수 있음'}); });
  if (d.g) { g.nodes.push({id:d.g, label:B.names[d.g], group:'grain'}); g.edges.push({from:id, to:d.g, label:'지역 단위'}); }
}
function pick(ids) { const g = {nodes:[], edges:[]}; ids.forEach(id => { g.nodes.push(dsNode(id)); links(id, g); }); return g; }
const first = new Set(B.initial);
const order = Object.keys(B.ds).sort((a, b) => B.ds[b].s - B.ds[a].s);
function pool(focus) {
  return order.filter(id => !first.has(id) && (focus.startsWith('category:') ? B.ds[id].c === focus : B.ds[id].k.includes(focus)));
}
add(pick(B.initial));
const count = () => nodes.get().filter(x => x.group0 === 'dataset').length;
$('cnt').textContent = `전체 ${B.total.toLocaleString()}개 자료 중 대표 ${count()}개 표시 · 분야·개념 원을 누르면 관련 자료가 6개씩 펼쳐집니다 · 마우스 휠·＋/－ 버튼으로 확대, 끌어서 이동`;
const net = new vis.Network($('g'), {nodes, edges}, OPTS);
net.once('stabilizationIterationsDone', () => widen(net));
addZoom(net);
net.on('click', p => {
  if (!p.nodes.length) { $('info').hidden = true; return; }
  const n = nodes.get(p.nodes[0]);
  if (n.group0 === 'dataset') return showInfo(n);
  if (n.group0 !== 'category' && n.group0 !== 'concept') return;
  $('info').hidden = true;
  const pg = pages[n.id] || 0, all = pool(n.id), ids = all.slice(pg * 6, pg * 6 + 6);
  pages[n.id] = pg + 1;
  net.setOptions({physics:{enabled:true}});
  add(pick(ids));
  net.once('stabilized', () => { net.setOptions({physics:{enabled:false}}); net.fit({animation:{duration:500}}); });
  $('cnt').textContent = `전체 ${B.total.toLocaleString()}개 자료 중 ${count()}개 표시` + (all.length > pg * 6 + 6 ? '' : ` · '${n.label.replace(/\n/g, ' ')}' 관련 자료를 모두 펼쳤습니다`);
});
"""

_HOME_JS_HYBRID = r"""
const B = DATA, HUBURL = 'https://jejudatahub.net/data/view/data/', STEP = 20, pages = {};
const CATS = {};
Object.entries(B.ds).forEach(([id, d]) => { if (d.c) (CATS[d.c] = CATS[d.c] || []).push(id); });
const CAT_IDS = Object.keys(CATS).sort((a, b) => CATS[b].length - CATS[a].length);
const order = Object.keys(B.ds).sort((a, b) => B.ds[b].s - B.ds[a].s);
function dsNode(id, group) { const d = B.ds[id]; return {id, label:d.l, group:group || 'dataset', url:HUBURL + d.h,
  info:{title:d.t, hub_id:d.h, category:B.names[d.c] || '', access:d.a, period:d.p, desc:d.d, topics:d.tp}}; }
function links(id, g) {
  const d = B.ds[id];
  if (d.c) { g.nodes.push({id:d.c, label:B.names[d.c], group:'category'}); g.edges.push({from:id, to:d.c, label:'분야'}); }
  d.k.slice(0, 2).forEach(k => { g.nodes.push({id:k, label:B.names[k] || k, group:'concept'}); g.edges.push({from:id, to:k, label:'알 수 있음'}); });
  if (d.g) { g.nodes.push({id:d.g, label:B.names[d.g], group:'grain'}); g.edges.push({from:id, to:d.g, label:'지역 단위'}); }
}
function pick(ids, group) { const g = {nodes:[], edges:[]}; ids.forEach(id => { g.nodes.push(dsNode(id, group)); links(id, g); }); return g; }
const net = new vis.Network($('g'), {nodes, edges}, OPTS);
addZoom(net);
let list = [], shown = 0, label = '', group = 'dataset';
const count = () => nodes.get().filter(x => x.group0 === 'dataset' || x.group0 === 'used').length;
function layout(reset) {
  net.setOptions({physics:{enabled:true}});
  net.stabilize(reset ? 400 : 200);
  net.once('stabilizationIterationsDone', () => { if (reset) widen(net); else { net.setOptions({physics:{enabled:false}}); net.fit({animation:{duration:400}}); } });
}
function status() {
  const more = shown < list.length;
  $('cnt').innerHTML = esc(`${label} — ${list.length.toLocaleString()}개 중 ${Math.min(shown, list.length)}개 표시`)
    + (more ? ` <button id="more" type="button">${Math.min(STEP, list.length - shown)}개 더 보기</button>` : '')
    + '<span class="hint"> · 분야·개념 원을 누르면 관련 자료 6개씩 · 휠·＋/－로 확대</span>';
  if (more) $('more').onclick = () => { add(pick(list.slice(shown, shown + STEP), group)); shown += STEP; status(); layout(false); };
}
function show(ids, lab, grp) {
  nodes.clear(); edges.clear(); $('info').hidden = true;
  list = ids; shown = STEP; label = lab; group = grp || 'dataset';
  add(pick(list.slice(0, STEP), group)); status(); layout(true);
}
function setActive(key) { document.querySelectorAll('#bar .cat').forEach(b => b.classList.toggle('on', b.dataset.k === key)); }
function home() { setActive('all'); show(B.initial.concat(order.filter(id => !B.initial.includes(id))), `전체 ${B.total.toLocaleString()}개 자료(대표 자료부터)`); }
function category(c) { setActive(c); show(order.filter(id => B.ds[id].c === c), `${B.names[c]} 자료`); }
function search(q) {
  q = (q || '').trim();
  if (!q) return home();
  setActive('');
  const R = rankSearch(q);
  if (!R.hits.length) { nodes.clear(); edges.clear(); $('cnt').textContent = `'${q}' 검색 결과가 없습니다`; return; }
  show(R.hits, `'${q}' 검색 결과` + (R.dropped ? `(설명에만 나오는 ${R.dropped}개 제외)` : ''), 'used');
}
net.on('click', p => {
  if (!p.nodes.length) { $('info').hidden = true; return; }
  const n = nodes.get(p.nodes[0]);
  if (n.group0 === 'dataset' || n.group0 === 'used') return showInfo(n);
  if (n.group0 !== 'category' && n.group0 !== 'concept') return;
  $('info').hidden = true;
  const pool = order.filter(id => !nodes.get(id) && (n.group0 === 'category' ? B.ds[id].c === n.id : B.ds[id].k.includes(n.id)));
  const ids = pool.slice(0, 6);
  if (!ids.length) { $('cnt').textContent = `'${n.label.replace(/\n/g, ' ')}' 관련 자료를 모두 펼쳤습니다`; return; }
  add(pick(ids)); layout(false);
  $('cnt').textContent = `'${n.label.replace(/\n/g, ' ')}' 관련 자료 ${ids.length}개를 펼쳤습니다(지금 ${count()}개 표시)`;
});
const bar = $('bar');
bar.innerHTML = '<input id="q" type="search" placeholder="자료 검색 (예: 카페, 버스, 관광객, 기온)"><button id="go" type="button">검색</button>'
  + '<span class="cats"><button class="cat on" data-k="all" type="button">대표 자료</button>'
  + CAT_IDS.map(c => `<button class="cat" data-k="${c}" type="button">${esc(B.names[c])} <b>${CATS[c].length}</b></button>`).join('') + '</span>';
$('go').onclick = () => search($('q').value);
$('q').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) search($('q').value); });
bar.querySelectorAll('.cat').forEach(b => b.onclick = () => b.dataset.k === 'all' ? home() : category(b.dataset.k));
home();
"""

_ANSWER_JS = r"""
add(DATA);
const net = new vis.Network($('g'), {nodes, edges}, OPTS);
net.once('stabilizationIterationsDone', () => widen(net));
addZoom(net);
net.on('click', p => { if (!p.nodes.length) { $('info').hidden = true; return; } const n = nodes.get(p.nodes[0]); if (n.info) showInfo(n); });
"""

_CSS = """
body{margin:0;font-family:"Pretendard GOV","Noto Sans KR","Malgun Gothic",sans-serif;color:#1B2421}
#wrap{position:relative;border:1px solid #DCE3E8;border-radius:12px;background:#fbfdfd}
#g{height:%dpx}
#cnt{font-size:13px;color:#5f7680;padding:6px 10px}
#info{position:absolute;top:10px;right:10px;width:300px;max-height:85%%;overflow:auto;background:#fff;border:1px solid #DCE3E8;
  border-radius:10px;box-shadow:0 6px 20px rgba(0,0,0,.12);padding:12px 14px;font-size:13.5px;line-height:1.55}
#info h3{margin:0 24px 6px 0;font-size:15px}
#info .x{position:absolute;top:6px;right:8px;border:0;background:none;font-size:20px;cursor:pointer;color:#5f7680}
#info .meta{color:#5f7680;font-size:12.5px;margin-bottom:8px}
#info .tags{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0}
#info .tags span{background:#ebf4f3;color:#356272;border:1px solid #c7dcd7;border-radius:20px;padding:1px 9px;font-size:12px}
#info .btn{display:inline-block;margin-top:8px;padding:6px 12px;background:#0081A7;color:#fff;border-radius:8px;text-decoration:none}
#bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:10px 10px 4px}
#bar input{flex:0 0 260px;padding:7px 10px;border:1px solid #DCE3E8;border-radius:8px;font:inherit;font-size:13.5px}
#bar #go{padding:7px 12px;border:0;border-radius:8px;background:#006F8F;color:#fff;font:inherit;font-size:13px;cursor:pointer}
#bar .cats{display:flex;flex-wrap:wrap;gap:5px}
#bar .cat{padding:5px 10px;border:1px solid #DCE3E8;border-radius:16px;background:#fff;color:#164756;font:inherit;font-size:12.5px;cursor:pointer}
#bar .cat b{color:#0081A7;font-weight:700}
#bar .cat.on{background:#164756;color:#fff;border-color:#164756}
#bar .cat.on b{color:#bfe6f0}
#cnt #more{margin-left:6px;padding:3px 10px;border:1px solid #0081A7;border-radius:14px;background:#E6F4F8;color:#006F8F;font:inherit;font-size:12.5px;cursor:pointer}
#cnt .hint{color:#8a99a5}
.zoom{position:absolute;left:10px;bottom:44px;display:flex;flex-direction:column;gap:4px;z-index:5}
.zoom button{width:32px;height:32px;border:1px solid #DCE3E8;border-radius:8px;background:#fff;color:#164756;font-size:17px;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.zoom button:hover{background:#E6F4F8}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12.5px;color:#456570;padding:4px 10px 8px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%%;margin-right:4px;vertical-align:-1px}
"""

_LEGEND_HOME = ('<div class="legend"><span><i style="background:#164756"></i>분야</span><span><i style="background:#0081A7"></i>자료</span>'
                '<span><i style="background:#DD6418"></i>검색된 자료</span>'
                '<span><i style="background:#d6f1ec;border:1px solid #7fbfb6"></i>알 수 있는 것(개념)</span>'
                '<span><i style="background:#fbe3c4;border:1px solid #e0a458"></i>지역 단위</span></div>')
_LEGEND_ANSWER = ('<div class="legend"><span><i style="background:#DD6418"></i>이 답변에 쓴 자료</span>'
                  '<span><i style="background:#e6eef0;border:1px solid #b9ccd2"></i>검토했지만 안 쓴 자료</span>'
                  '<span><i style="background:#d6f1ec;border:1px solid #7fbfb6"></i>알 수 있는 것</span>'
                  '<span><i style="background:#fbe3c4;border:1px solid #e0a458"></i>지역</span>'
                  '<span style="color:#a9470d">━ 결합 가능(지역 단위 · 겹치는 기간)</span></div>')


def _page(data: dict, body_js: str, legend: str, height: int, count: bool) -> str:
    data_js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_CSS % height}</style>"
            f"<script>{_vis()}</script></head><body><div id='wrap'>"
            f"{'<div id=bar></div><div id=cnt></div>' if count else ''}<div id='g'></div><div id='info' hidden></div>{legend}</div>"
            f"<script>const DATA = {data_js};{_JS}{body_js}</script>"
            f"</body></html>")


def _industry_aliases() -> list[str]:
    import yaml
    d = yaml.safe_load((ROOT / "data" / "industries.yaml").read_text(encoding="utf-8"))
    return sorted({a for k, v in d.items() if isinstance(v, dict) for a in [k, *v.get("aliases", [])]})


# 업종 이름(카페·편의점 등)으로 검색하면 업종 구분이 있는 자료를 먼저 보여 준다
INDUSTRY_DATASETS = [793, 746, 780, 781, 782, 1048, 495]


def home_html(height: int = 520) -> str:
    data = dict(bundle(), ind=_industry_aliases(), ind_ds=[f"ds:{h}" for h in INDUSTRY_DATASETS])
    return _page(data, _SEARCH_JS + _HOME_JS, _LEGEND_HOME, height, True)


def home_html_hybrid(height: int = 520) -> str:
    """대표 자료 20개 보기(이전 방식) + 검색창·분야 버튼. 목록은 20개씩 '더 보기'."""
    data = dict(bundle(), ind=_industry_aliases(), ind_ds=[f"ds:{h}" for h in INDUSTRY_DATASETS])
    return _page(data, _SEARCH_JS + _HOME_JS_HYBRID, _LEGEND_HOME, height, True)


def home_html_classic(height: int = 520) -> str:
    """이전 방식: 대표 자료 20개로 시작, 분야·개념을 누르면 6개씩 펼침."""
    legend = ('<div class="legend"><span><i style="background:#164756"></i>분야</span><span><i style="background:#0081A7"></i>자료</span>'
              '<span><i style="background:#d6f1ec;border:1px solid #7fbfb6"></i>알 수 있는 것(개념)</span>'
              '<span><i style="background:#fbe3c4;border:1px solid #e0a458"></i>지역 단위</span></div>')
    page = _page(bundle(), _HOME_JS_CLASSIC, legend, height, True)
    return page.replace("<div id=bar></div>", "", 1)


def answer_html(hub_ids: list[int], places: list[str] | None = None, height: int = 380,
                candidates: dict[int, str] | None = None, joins: list | None = None) -> str | None:
    g = answer_graph(hub_ids, places, candidates, joins)
    return _page(g, _ANSWER_JS, _LEGEND_ANSWER, height, False) if g["nodes"] else None


def _embed(html: str, height: int) -> None:
    """Streamlit 1.5x 이후는 st.iframe, 그 이전은 components.html (둘 다 같은 HTML을 그린다)."""
    import streamlit as st
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=height, scrolling=False)


def show_home(height: int = 520) -> None:
    _embed(home_html(height), height + 205)


def show_home_hybrid(height: int = 520) -> None:
    _embed(home_html_hybrid(height), height + 205)


def show_home_classic(height: int = 520) -> None:
    _embed(home_html_classic(height), height + 90)


def show_answer(hub_ids: list[int], places: list[str] | None = None, height: int = 380,
                candidates: dict[int, str] | None = None, joins: list | None = None) -> None:
    import streamlit as st
    html = answer_html(hub_ids, places, height, candidates, joins)
    if html is None:
        st.caption("이 답변에 쓴 자료가 데이터 지도에 없습니다(외부 데이터 등).")
        return
    _embed(html, height + 50)
