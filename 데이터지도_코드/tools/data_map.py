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
                 candidates: dict[int, str] | None = None) -> dict:
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
            lab = b["joins"].get(f"{min(a, c)}|{max(a, c)}")
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
  return {id:n.id, label: isDs ? wrap(short(n.label, 16)) : short(n.label, 7), title: n.info ? n.info.title : n.label,
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
  stabilization:{iterations:500}}, interaction:{hover:true, tooltipDelay:80}, layout:{randomSeed:7}};
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

_HOME_JS = r"""
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
$('cnt').textContent = `전체 ${B.total.toLocaleString()}개 자료 중 대표 ${count()}개 표시 · 분야·개념 원을 누르면 관련 자료가 6개씩 펼쳐집니다`;
const net = new vis.Network($('g'), {nodes, edges}, OPTS);
net.once('stabilizationIterationsDone', () => widen(net));
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

_ANSWER_JS = r"""
add(DATA);
const net = new vis.Network($('g'), {nodes, edges}, OPTS);
net.once('stabilizationIterationsDone', () => widen(net));
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
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12.5px;color:#456570;padding:4px 10px 8px}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%%;margin-right:4px;vertical-align:-1px}
"""

_LEGEND_HOME = ('<div class="legend"><span><i style="background:#164756"></i>분야</span><span><i style="background:#0081A7"></i>자료</span>'
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
            f"{'<div id=cnt></div>' if count else ''}<div id='g'></div><div id='info' hidden></div>{legend}</div>"
            f"<script>const DATA = {data_js};{_JS}{body_js}</script>"
            f"</body></html>")


def home_html(height: int = 520) -> str:
    return _page(bundle(), _HOME_JS, _LEGEND_HOME, height, True)


def answer_html(hub_ids: list[int], places: list[str] | None = None, height: int = 380,
                candidates: dict[int, str] | None = None) -> str | None:
    g = answer_graph(hub_ids, places, candidates)
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
    _embed(home_html(height), height + 90)


def show_answer(hub_ids: list[int], places: list[str] | None = None, height: int = 380,
                candidates: dict[int, str] | None = None) -> None:
    import streamlit as st
    html = answer_html(hub_ids, places, height, candidates)
    if html is None:
        st.caption("이 답변에 쓴 자료가 데이터 지도에 없습니다(외부 데이터 등).")
        return
    _embed(html, height + 50)
