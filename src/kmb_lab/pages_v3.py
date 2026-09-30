from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Any

from .instrument_filter import is_stock_analysis_eligible
from .pages_korean import human_time, status_label
from .pages_market import _flows, _futures_global, _relative_strength, _smart, _strength

VERSION_LABEL = "시장 인텔리전스 V3"

NAV_ITEMS = (
    ("index.html", "시장 홈"),
    ("issues.html", "시장 이슈"),
    ("ai-research.html", "AI 시장 추론"),
    ("stocks.html", "종목 분석"),
    ("smart-money.html", "큰손 행동"),
    ("news.html", "뉴스 인텔리전스"),
    ("global.html", "글로벌 리스크"),
    ("lab.html", "연구실"),
    ("system.html", "시스템"),
)

COMMON_TERM_MAP = {
    "credit spread": "신용 스프레드",
    "Credit Spread": "신용 스프레드",
    "lead-lag": "선행·후행 관계",
    "Lead-Lag": "선행·후행 관계",
    "hurdle rate": "투자 최소 요구수익률",
    "Hurdle Rate": "투자 최소 요구수익률",
    "buyback": "자사주 매입",
    "Buyback": "자사주 매입",
    "breadth": "시장 확산도",
    "Breadth": "시장 확산도",
    "private credit": "사모 신용",
    "Private Credit": "사모 신용",
    "refinancing": "차환",
    "CAPEX": "설비투자",
    "FCF": "잉여현금흐름",
}

RESULT_LABELS = {
    "MAJOR_RESEARCH_COMPLETED_CANDIDATE_WRITE_BLOCKED": "연구 완료 · 후보 저장 차단",
    "NEW_IMPORTANT_NEWS_FOUND": "중요 신규 뉴스 발견",
    "NEW_IMPORTANT_NEWS_DISCOVERED": "중요 신규 뉴스 발견",
    "EXISTING_ISSUE_UPDATED": "기존 이슈 업데이트",
    "NO_IMPORTANT_NEW_NEWS": "중요 신규 뉴스 없음",
    "NO_NEW_EVIDENCE": "새 근거 없음",
    "FIX_REQUIRED": "수정 필요",
    "PASS_WITH_NOTES": "조건부 통과",
    "CANDIDATE": "검증 전 분석",
    "VERIFIED": "검증 완료",
    "ESTIMATED": "데이터 기반 추정",
    "HYPOTHESIS": "검증 중인 가설",
    "CONFIRMED": "확인됨",
    "UNKNOWN": "확인 필요",
}

STYLE = """
:root{--bg:#f4f7fb;--card:#fff;--text:#172033;--muted:#667085;--line:#e4e9f0;--accent:#3157d5;--good:#137a4b;--warn:#9a6700;--bad:#b42318}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.65}
.wrap{max-width:1180px;margin:auto;padding:0 20px 56px}.top{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}
.nav{max-width:1180px;margin:auto;display:flex;gap:6px;align-items:center;padding:10px 20px;overflow:auto}.nav a{white-space:nowrap;text-decoration:none;color:#44506a;padding:8px 11px;border-radius:9px;font-size:14px}.nav a.active{background:#edf2ff;color:#2444b8;font-weight:700}
.mobile-nav{display:none;padding:8px 20px}.hero{padding:34px 0 18px}.hero h1{margin:0 0 8px;font-size:30px}.hero p{margin:0;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.card,.metric{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 1px 2px rgba(16,24,40,.03)}.metric span{display:block;color:var(--muted);font-size:13px}.metric strong{font-size:20px}
.card h3{margin:0 0 8px}.card p{margin:7px 0}.section-title{margin:30px 0 12px;font-size:22px}.note,.meta{color:var(--muted);font-size:13px}.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef1f5;color:#4b5565;font-size:12px;font-weight:700}.badge.good{background:#e8f7ef;color:var(--good)}.badge.warn{background:#fff5d6;color:var(--warn)}.badge.bad{background:#feeceb;color:var(--bad)}
.flow{display:flex;flex-wrap:wrap;gap:7px;align-items:center;margin:10px 0}.flow span{background:#f0f4ff;border:1px solid #dce4ff;padding:6px 9px;border-radius:9px}.flow b{color:#78839a}
details>summary{cursor:pointer}.reasoning-card{border-left:4px solid #657bd9}.reasoning-card .hyp{background:#f7f8ff;border-radius:10px;padding:10px 12px}.reasoning-card ul{margin-top:5px;padding-left:20px}
.issue-card{border-left:4px solid #6f7e91}.confidence-high{color:var(--good)}.confidence-mid{color:var(--warn)}.confidence-low{color:var(--bad)}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 18px}.filters button,.filters input{border:1px solid var(--line);background:#fff;border-radius:9px;padding:8px 11px}.filters button.on{background:#edf2ff;color:#2444b8}
.timeline{display:grid;gap:12px}.compact-list{margin:0;padding-left:19px}.compact-list li{margin:4px 0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid var(--line);padding:8px;font-size:13px}
.footer{margin-top:36px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
@media(max-width:760px){.nav{display:none}.mobile-nav{display:block}.grid,.grid3,.metric-grid{grid-template-columns:1fr}.hero{padding-top:24px}.hero h1{font-size:25px}.wrap{padding-left:14px;padding-right:14px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
"""

def esc(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "확인 필요"), quote=True)


def ko_text(value: Any) -> str:
    if value in (None, ""):
        return "확인 필요"
    if isinstance(value, dict):
        return "세부 데이터는 검증 기록에서 확인"
    if isinstance(value, list):
        return " · ".join(ko_text(x) for x in value if x not in (None, "")) or "확인 필요"
    text = str(value)
    text = RESULT_LABELS.get(text.upper(), text)
    for source, target in COMMON_TERM_MAP.items():
        text = re.sub(re.escape(source), target, text, flags=re.IGNORECASE)
    return text


def badge(value: Any) -> str:
    raw = str(value or "UNKNOWN")
    label = RESULT_LABELS.get(raw.upper(), status_label(raw))
    cls = "good" if raw.upper() in {"ACTIVE","HEALTHY","CONFIRMED","VERIFIED","SUCCESS","RESOLVED","LIVE"} else "bad" if raw.upper() in {"FAILED","FIX_REQUIRED","BLOCKED","REJECTED"} else "warn"
    return f'<span class="badge {cls}">{esc(label)}</span>'


def page_shell(title: str, subtitle: str, active: str, body: str, model: dict[str, Any]) -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">{label}</a>'
        for href, label in NAV_ITEMS
    )
    mobile = "".join(f'<li><a href="{href}">{label}</a></li>' for href, label in NAV_ITEMS)
    source = str(model.get("source_commit") or "")
    generated = model.get("generated_at") or "확인 필요"
    fp = str(model.get("material_fingerprint") or "")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · KMB</title><style>{STYLE}</style></head>
<body data-source-commit="{esc(source)}" data-material-fingerprint="{esc(fp)}">
<div class="top"><nav class="nav">{nav}</nav><details class="mobile-nav"><summary>메뉴</summary><ul>{mobile}</ul></details></div>
<main class="wrap"><section class="hero"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></section>{body}
<footer class="footer">{esc(VERSION_LABEL)} · 페이지 생성 {esc(generated)} · 데이터가 없으면 임의로 채우지 않습니다. · 반영 버전 {esc(source[:8] or "확인 필요")}</footer>
</main></body></html>"""


def _confidence(issue: dict[str, Any]) -> tuple[str, str]:
    independent = int(issue.get("independent_source_count") or issue.get("independent_publishers") or 0)
    official = bool(issue.get("official_source_available"))
    if official and independent >= 2:
        return "높음", "confidence-high"
    if official or independent >= 2:
        return "보통", "confidence-mid"
    return "낮음", "confidence-low"


def _research_anchor(row: dict[str, Any]) -> str:
    raw = str(row.get("fingerprint") or row.get("title") or row.get("at") or "research")
    return "research-" + re.sub(r"[^A-Za-z0-9_-]+", "-", raw)[:90].strip("-")


def _research_by_issue(model: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    linked: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in model.get("research_timeline") or []:
        for issue_id in row.get("related_issue_ids") or []:
            linked[str(issue_id)].append(row)
    return linked


def issue_card(issue: dict[str, Any], now_value: Any, related_research: list[dict[str, Any]] | None = None) -> str:
    trust, cls = _confidence(issue)
    independent = issue.get("independent_source_count") or issue.get("independent_publishers") or 0
    article_count = issue.get("article_count") or 0
    reprints = issue.get("reprint_count") or max(0, int(article_count) - int(independent or 0))
    articles = []
    for row in (issue.get("articles") or [])[:12]:
        source = row.get("source") or row.get("publisher") or "출처 확인 필요"
        quality = row.get("content_quality")
        qlabel = {
            "OFFICIAL_FACTUAL_OR_NOTICE": "공식자료",
            "EDITORIAL_OR_FACTUAL": "독립/일반 보도",
            "POSSIBLE_PROMOTION": "홍보 가능성",
        }.get(str(quality), "출처 확인")
        href = row.get("url")
        label = f"{source} · {qlabel}"
        articles.append(f'<li><a href="{esc(href)}" rel="noopener noreferrer">{esc(label)}</a></li>' if href else f'<li>{esc(label)}</li>')
    related = (issue.get("related_markets") or []) + (issue.get("related_sectors") or []) + (issue.get("related_stocks") or [])
    research_links = "".join(
        f'<li><a href="ai-research.html#{esc(_research_anchor(row))}">{esc(row.get("agent") or "AI")} · {esc(ko_text(row.get("title") or "관련 연구"))}</a></li>'
        for row in (related_research or [])[:8]
    )
    research_html = (
        f'<details><summary>연결된 AI 연구 {len(related_research or [])}개</summary><ul class="compact-list">{research_links}</ul></details>'
        if related_research else ""
    )
    return (
        '<details class="card issue-card">'
        f'<summary><strong>{esc(issue.get("headline"))}</strong><div class="meta">{badge(issue.get("state"))} · 신뢰도 <b class="{cls}">{trust}</b> · {esc(human_time(issue.get("latest_at"), now_value))}</div></summary>'
        f'<p>{esc(issue.get("why_important") or "시장 반응과 공식자료를 추가 확인합니다.")}</p>'
        f'<p><b>근거 구성:</b> 기사 {esc(article_count)}건 · 독립 근거 {esc(independent)}개 · 재인용 추정 {esc(reprints)}건 · 공식자료 {"있음" if issue.get("official_source_available") else "추가 확인"}</p>'
        f'<p><b>관련 시장·업종·종목:</b> {esc(" · ".join(map(str, related[:10])) if related else "추가 확인 중")}</p>'
        f'<p><b>반대 해석:</b> {esc(issue.get("counterpoint") or "뉴스와 가격이 동시에 움직였다는 사실만으로 인과를 확정하지 않습니다.")}</p>'
        f'<p><b>다음 확인:</b> {esc(" · ".join(map(str, issue.get("next_variables") or [])) or "추가 확인 중")}</p>'
        f'{research_html}'
        f'<details><summary>관련 원문 보기</summary><ul class="compact-list">{"".join(articles) or "<li>표시 가능한 원문 링크 없음</li>"}</ul></details>'
        '</details>'
    )


def _list_block(title: str, values: Any, empty: str = "기록된 내용 없음") -> str:
    rows = values if isinstance(values, list) else ([values] if values not in (None, "") else [])
    clean = [ko_text(x) for x in rows if x not in (None, "", {})]
    return f'<div><b>{esc(title)}</b><ul class="compact-list">{"".join(f"<li>{esc(x)}</li>" for x in clean) or f"<li>{esc(empty)}</li>"}</ul></div>'


def research_card(row: dict[str, Any], now_value: Any) -> str:
    hypothesis = row.get("hypothesis")
    if isinstance(hypothesis, list):
        hypothesis_text = " · ".join(ko_text(x) for x in hypothesis)
    else:
        hypothesis_text = ko_text(hypothesis) if hypothesis else "아직 명시된 가설 없음"
    path = row.get("impact_path") or []
    flow = ""
    if path:
        flow = '<div class="flow">' + '<b>→</b>'.join(f'<span>{esc(ko_text(x))}</span>' for x in path) + '</div>'
    related = (row.get("related_markets") or []) + (row.get("related_sectors") or []) + (row.get("related_stocks") or [])
    source_kind = "GitHub 실행 기록" if row.get("source_kind") == "AGENT_STATE_HISTORY" else "현재 실행 기록" if row.get("source_kind") == "CURRENT_AGENT_STATE" else "저장된 연구 작업물"
    return (
        f'<article id="{esc(_research_anchor(row))}" class="card reasoning-card research-item" data-agent="{esc(row.get("agent") or "AI")}" data-search="{esc((str(row.get("title") or "")+" "+hypothesis_text).lower())}">'
        f'<div class="meta">{esc(row.get("agent") or "AI")} · {esc(human_time(row.get("at"), now_value))} · {esc(source_kind)}</div>'
        f'<h3>{esc(ko_text(row.get("title") or "시장 연구"))}</h3>'
        f'<p>{badge(row.get("result") or row.get("news_outcome") or "HYPOTHESIS")} {badge(row.get("news_outcome")) if row.get("news_outcome") else ""}</p>'
        f'{_list_block("확인된 사실", row.get("confirmed"))}'
        f'<div class="hyp"><b>현재 가설</b><p>{esc(hypothesis_text)}</p></div>'
        f'{flow}'
        f'<p><b>왜 중요한가:</b> {esc(ko_text(row.get("why_important")) if row.get("why_important") else "시장 가격·수급·기업 실적에 미치는 경로를 추가 검증 중")}</p>'
        f'<p><b>반대 시나리오:</b> {esc(ko_text(row.get("counter_scenario")) if row.get("counter_scenario") else "아직 별도 기록 없음")}</p>'
        f'{_list_block("확인 필요", row.get("unknown"), "현재 기록된 미확인 항목 없음")}'
        f'{_list_block("다른 AI 검증", row.get("handoffs"), "추가 검증 연결 없음")}'
        f'<p><b>관련 시장·업종·종목:</b> {esc(" · ".join(map(str, related[:12])) if related else "연결 데이터 추가 확인 중")}</p>'
        f'<p><b>다음 연구:</b> {esc(ko_text(row.get("next_work")) if row.get("next_work") else "후속 작업 미기록")}</p>'
        '</article>'
    )


def _market_metrics(model: dict[str, Any]) -> str:
    intel = model.get("intelligence") or {}
    current = intel.get("current") or {}
    indices = current.get("indices") or {}
    global_quotes = ((intel.get("global") or {}).get("quotes") or {})
    rows = []
    for key, label in (("KOSPI","KOSPI"),("KOSDAQ","KOSDAQ")):
        row = indices.get(key) or current.get(key) or {}
        if isinstance(row, dict):
            price = row.get("close")
            change = row.get("change_pct")
            value = f'{price:,.2f}' if isinstance(price,(int,float)) else "확인 필요"
            if isinstance(change,(int,float)):
                value += f' ({change:+.2f}%)'
        else:
            value = ko_text(row)
        rows.append((label,value))
    for key,label in (("USD_KRW","원/달러"),("WTI","WTI"),("NASDAQ100_FUTURES","나스닥100 선물")):
        row = global_quotes.get(key) or {}
        price=row.get("price")
        change=row.get("change_pct")
        value=f'{price:,.2f}' if isinstance(price,(int,float)) else "확인 필요"
        if isinstance(change,(int,float)): value+=f' ({change:+.2f}%)'
        rows.append((label,value))
    return "".join(f'<article class="metric"><span>{esc(k)}</span><strong>{esc(v)}</strong></article>' for k,v in rows)


def render_home(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    issues=((intel.get("issues") or {}).get("issues") or [])[:3]
    research=(model.get("research_timeline") or [])[:4]
    agents=model.get("agents") or []
    issue_html="".join(issue_card(x,model.get("generated_at")) for x in issues) or '<p class="note">현재 표시할 핵심 이슈 없음</p>'
    research_html="".join(research_card(x,model.get("generated_at")) for x in research) or '<p class="note">최근 구조화된 AI 연구 기록 없음</p>'
    agents_html="".join(f'<article class="metric"><span>{esc(x.get("agent"))}</span><strong style="font-size:14px">{esc(status_label(x.get("status")))}</strong></article>' for x in agents)
    body=(
        '<section data-kmb-section="overview"><h2 class="section-title">오늘 시장 한눈에 보기</h2>'
        f'<div class="metric-grid">{_market_metrics(model)}</div></section>'
        '<section data-kmb-section="market"><h2 class="section-title">지금 가장 중요한 이슈</h2>'
        f'<div class="grid">{issue_html}</div><p><a href="issues.html">모든 시장 이슈 보기 →</a></p></section>'
        '<section data-kmb-section="cycle"><h2 class="section-title">지금 AI가 생각하고 있는 것</h2>'
        '<p class="note">숨겨진 내부 사고과정이 아니라 관찰·근거·가설·반대 시나리오·다음 검증을 구조화해 보여줍니다.</p>'
        f'<div class="grid">{research_html}</div><p><a href="ai-research.html">AI 시장 추론 전체 보기 →</a></p></section>'
        '<h2 class="section-title">5개 AI 작동 상태</h2><div class="metric-grid">'+agents_html+'</div>'
    )
    return page_shell("시장 홈","몇 초 안에 현재 시장의 핵심 이슈와 AI 연구 방향을 확인합니다.","index.html",body,model)


def render_issues(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    doc=intel.get("issues") or {}
    issues=doc.get("issues") or []
    research_links=_research_by_issue(model)
    body='<section data-kmb-section="market-issues"><p class="note">동일 사건을 기사 단위가 아니라 이슈 단위로 묶습니다. 재인용 기사 수를 독립 근거 수로 계산하지 않습니다.</p><div class="grid">'+("".join(issue_card(x,model.get("generated_at"),research_links.get(str(x.get("issue_id")),[])) for x in issues[:50]) or '<p>현재 이슈 없음</p>')+'</div></section>'
    return page_shell("시장 이슈","등장 → 지속 → 강화 → 완화 → 해소의 흐름으로 시장 사건을 추적합니다.","issues.html",body,model)


def render_ai_research(model: dict[str, Any]) -> str:
    rows=model.get("research_timeline") or []
    groups=defaultdict(list)
    for row in rows:
        groups[str(row.get("fingerprint") or row.get("title") or "기타")].append(row)
    evol=[]
    for _,items in groups.items():
        if len(items)<2: continue
        title=ko_text(items[0].get("title") or "가설")
        times=" → ".join(human_time(x.get("at"),model.get("generated_at")) for x in reversed(items[:8]))
        evol.append(f'<article class="card"><strong>{esc(title)}</strong><p>{esc(times)}</p><p class="note">같은 연구 지문이 시간에 따라 {len(items)}회 업데이트됨</p></article>')
    filters='''<div class="filters"><button class="on" data-agent-filter="ALL">전체</button><button data-agent-filter="AI-A">AI-A</button><button data-agent-filter="AI-B">AI-B</button><button data-agent-filter="AI-C">AI-C</button><button data-agent-filter="AI-D">AI-D</button><button data-agent-filter="AI-E">AI-E</button><input id="research-search" placeholder="가설·주제 검색"></div>'''
    cards="".join(research_card(x,model.get("generated_at")) for x in rows[:150]) or '<p>아직 구조화된 연구 기록이 없습니다.</p>'
    script='''<script>(()=>{let agent="ALL";const items=[...document.querySelectorAll(".research-item")];const input=document.querySelector("#research-search");function draw(){const q=(input?.value||"").toLowerCase();items.forEach(x=>x.hidden=!((agent==="ALL"||x.dataset.agent===agent)&&(!q||x.dataset.search.includes(q))))}document.querySelectorAll("[data-agent-filter]").forEach(b=>b.onclick=()=>{agent=b.dataset.agentFilter;document.querySelectorAll("[data-agent-filter]").forEach(x=>x.classList.toggle("on",x===b));draw()});input?.addEventListener("input",draw)})();</script>'''
    body=(
        '<section data-kmb-section="ai-market-reasoning">'
        '<p class="note">AI 실행 결과에 저장된 사실·가설·미확인 항목·반증·정량검증 계획을 모읍니다. candidate 저장이 막혀도 agent state가 Git에 남았다면 과거 기록에서 복원합니다.</p>'
        +filters+
        ('<h2 class="section-title">가설 발전 기록</h2><div class="grid">'+"".join(evol[:20])+'</div>' if evol else '')+
        '<h2 class="section-title">최신 연구 타임라인</h2><div class="timeline">'+cards+'</div></section>'+script
    )
    return page_shell("AI 시장 추론","AI가 어떤 사실을 연결해 무엇을 위험요인·기회후보로 연구하는지 확인합니다.","ai-research.html",body,model)


def _filtered_stock_data(data: dict[str, Any]) -> dict[str, Any]:
    copied=dict(data)
    items=[]
    for row in data.get("items") or []:
        if is_stock_analysis_eligible({"itemCode":row.get("code"),"stockName":row.get("name")}):
            items.append(row)
    copied["items"]=items
    return copied


def render_stocks(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    rs=_filtered_stock_data(intel.get("relative_strength") or {})
    issues=((intel.get("issues") or {}).get("issues") or [])
    connection_cards=[]
    for stock in rs.get("items") or []:
        name=str(stock.get("name") or "")
        linked=[x for x in issues if name and name in (x.get("related_stocks") or [])][:5]
        if not linked:
            continue
        connection_cards.append(
            f'<article class="card"><h3>{esc(name)}</h3><p><b>최근 연결 이슈:</b></p><ul class="compact-list">'
            + "".join(f'<li>{esc(x.get("headline"))} · {esc(status_label(x.get("state")))}</li>' for x in linked)
            + '</ul></article>'
        )
    connections=('<h2 class="section-title">종목과 연결된 최근 이슈</h2><div class="grid">'+"".join(connection_cards)+'</div>') if connection_cards else ""
    body='<section data-kmb-section="stock-analysis"><article class="card"><strong>분석 대상: 한국 거래소 일반 보통주</strong><p>ETF·ETN·스팩·우선주·리츠·인버스·레버리지 등 상장상품은 개별 종목 분석에서 제외합니다. ETF/ETN은 시장 자금흐름 참고변수로만 사용할 수 있습니다.</p></article>'+_relative_strength(rs)+connections+'</section>'
    return page_shell("종목 분석","보통주 기업만 대상으로 상대강도·수급·이슈 연결을 봅니다.","stocks.html",body,model)


def render_smart_money(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    smart=_filtered_stock_data(intel.get("smart_money") or {})
    body='<section data-kmb-section="smart-money"><article class="card"><strong>관측 사실과 큰손 행동 추정을 분리합니다.</strong><p>거래량을 곧바로 매집량·분배량으로 간주하지 않습니다. ETF·ETN·스팩·우선주는 이 분석에서 제외합니다.</p></article>'+_smart(smart)+'</section>'
    return page_shell("큰손 행동","매집·흡수·분배·잔존 물량·추가 상승 유인을 공개 데이터 범위에서 연구합니다.","smart-money.html",body,model)


def render_news(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    current=intel.get("news") or {}
    doc=intel.get("issues") or {}
    issues=doc.get("issues") or []
    disclosures=intel.get("disclosures") or {}
    drows=[]
    for x in (disclosures.get("items") or [])[:30]:
        title=f'{x.get("corp_name") or "회사"} · {x.get("report_name") or "공시"}'
        href=x.get("url")
        drows.append(f'<li><a href="{esc(href)}" rel="noopener noreferrer">{esc(title)}</a></li>' if href else f'<li>{esc(title)}</li>')
    stats=(
        f'수집 원문 {current.get("raw_count") or current.get("raw_news_count") or "확인 필요"}건'
        f' → 홍보성 제외 {current.get("promotion_filtered_count") if current.get("promotion_filtered_count") is not None else "측정 전"}건'
        f' · 저정보 제외 {current.get("low_information_filtered_count") if current.get("low_information_filtered_count") is not None else "측정 전"}건'
        f' · 중복/재인용 정리 {current.get("duplicate_or_reprint_filtered_count") if current.get("duplicate_or_reprint_filtered_count") is not None else "측정 전"}건'
        f' → 정제 후 {current.get("deduplicated_count") or current.get("count") or "확인 필요"}건'
        f' · 확인 소스 {current.get("sources_checked") or "확인 필요"}개'
    )
    body=(
        '<section data-kmb-section="news-issues"><article class="card"><strong>뉴스는 기사 수가 아니라 이슈 품질로 봅니다.</strong>'
        f'<p>{esc(stats)}</p><p>광고·홍보성 2차 콘텐츠는 기본 분석에서 제외하고, 원출처·공식자료·독립 취재와 재인용을 구분합니다.</p></article>'
        '<h2 class="section-title">정제된 핵심 이슈</h2><div class="grid">'+("".join(issue_card(x,model.get("generated_at"),_research_by_issue(model).get(str(x.get("issue_id")),[])) for x in issues[:30]) or '<p>현재 이슈 없음</p>')+'</div>'
        '<h2 class="section-title" data-kmb-section="disclosures">공식 공시</h2><article class="card"><ul class="compact-list">'+("".join(drows) or '<li>현재 표시할 공시 없음</li>')+'</ul></article></section>'
    )
    return page_shell("뉴스 인텔리전스","중복·재인용·홍보를 걷어내고 실제 시장 사건만 압축해서 봅니다.","news.html",body,model)


def render_global(model: dict[str, Any]) -> str:
    intel=model.get("intelligence") or {}
    body='<section data-kmb-section="futures-global">'+_futures_global(intel.get("futures") or {},intel.get("global") or {})+'</section>'
    return page_shell("글로벌 리스크","미국 금리·달러·유가·선물·지정학이 국내시장으로 전달되는 경로를 분리해 봅니다.","global.html",body,model)


def render_lab(model: dict[str, Any]) -> str:
    products=model.get("work_products") or []
    cards=[]
    for x in products[:80]:
        cards.append(
            '<article class="card">'
            f'<div class="meta">{esc(x.get("agent") or "AI")} · {esc(human_time(x.get("updated_at"),model.get("generated_at")))}</div>'
            f'<h3>{esc(ko_text(x.get("title")))}</h3><p>{badge(x.get("result") or x.get("status"))}</p>'
            f'<p>{esc(ko_text(x.get("summary")))}</p><p><b>다음:</b> {esc(ko_text(x.get("next_work")))}</p></article>'
        )
    body='<section data-kmb-section="research"><p class="note">AI-B의 반증, AI-C의 정량검증, 기타 연구 작업물을 모읍니다. 검증 전 후보는 확정 사실처럼 표시하지 않습니다.</p><div class="grid">'+("".join(cards) or '<p>현재 표시할 연구 작업물 없음</p>')+'</div></section>'
    return page_shell("연구실","가설이 실제 데이터와 반대 사례를 견디는지 검증하는 공간입니다.","lab.html",body,model)


def render_system(model: dict[str, Any]) -> str:
    agents=model.get("agents") or []
    agent_cards=[]
    for x in agents:
        agent_cards.append(f'<article class="card"><h3>{esc(x.get("agent"))}</h3><p>{badge(x.get("status"))}</p><p><b>현재 작업:</b> {esc(ko_text(x.get("current_task")))}</p><p><b>최근 실행:</b> {esc(human_time(x.get("last_execution"),model.get("generated_at")))}</p></article>')
    recovery=model.get("recovery") or {}
    incidents=recovery.get("incidents") or []
    rec="".join(f'<li>{badge(x.get("status"))} {esc(ko_text(x.get("title") or x.get("incident_id") or "복구 항목"))}</li>' for x in incidents[:20]) or '<li>현재 표시할 복구 항목 없음</li>'
    workflows=((model.get("workflows") or {}).get("latest") or {})
    wf="".join(f'<article class="card"><h3>{esc(name)}</h3><p>{badge(row.get("conclusion") or row.get("status"))}</p></article>' for name,row in workflows.items())
    body=(
        '<section data-kmb-section="agent-health"><h2 class="section-title">AI 작동 상태</h2><div class="grid">'+("".join(agent_cards) or '<p>상태 없음</p>')+'</div></section>'
        '<section data-kmb-section="recovery"><h2 class="section-title">복구 현황</h2><article class="card"><ul class="compact-list">'+rec+'</ul></article></section>'
        '<section data-kmb-section="actions"><h2 class="section-title">자동 실행 상태</h2><div class="grid">'+(wf or '<p>자동 실행 상태 확인 필요</p>')+'</div></section>'
    )
    return page_shell("시스템 상태","AI 실행·수집·복구·배포 같은 운영 정보는 시장 분석 화면과 분리합니다.","system.html",body,model)


def render_pages(model: dict[str, Any]) -> dict[str, str]:
    return {
        "index.html": render_home(model),
        "issues.html": render_issues(model),
        "ai-research.html": render_ai_research(model),
        "stocks.html": render_stocks(model),
        "smart-money.html": render_smart_money(model),
        "news.html": render_news(model),
        "global.html": render_global(model),
        "lab.html": render_lab(model),
        "system.html": render_system(model),
    }
