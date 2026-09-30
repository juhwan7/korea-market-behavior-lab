from __future__ import annotations

import html
from typing import Any


def esc(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "확인 불가"), quote=True)


def num(value: Any, *, suffix: str = "", digits: int = 1) -> str:
    if not isinstance(value, (int, float)):
        return "확인 불가"
    return f"{value:,.{digits}f}{suffix}"


def badge(value: Any) -> str:
    raw = str(value or "UNKNOWN")
    cls = "ok" if raw in {"CONNECTED", "CONNECTED_EOD_PRIMARY", "HEALTHY", "ESTIMATED"} else "warn" if raw in {"PARTIAL", "SHADOW", "USER_ACTION_REQUIRED", "HYPOTHESIS"} else "muted"
    labels = {
        "CONNECTED_EOD_PRIMARY": "공식 일별 연결",
        "USER_ACTION_REQUIRED": "사용자 설정 필요",
        "NOT_CONNECTED": "미연결",
        "ESTIMATED": "데이터 기반 추정",
        "SHADOW": "검증 중",
        "UNKNOWN": "확인 불가",
    }
    return f'<span class="badge {cls}">{esc(labels.get(raw, raw))}</span>'


def _strength(data: dict[str, Any]) -> str:
    components = data.get("components") or {}
    labels = {"price":"가격","breadth":"시장폭","turnover":"거래대금","foreign_flow":"외국인 수급","program":"프로그램"}
    cards = "".join(
        f'<article class="metric"><span>{esc(labels.get(k,k))}</span><strong>{esc(num(v))}</strong></article>'
        for k,v in components.items()
    ) or '<p class="empty">아직 계산 가능한 시장 체력 데이터가 없습니다.</p>'
    illusions = "".join(f'<li>{esc(x.get("explanation"))}</li>' for x in (data.get("index_illusion") or [])) or '<li>현재 감지된 지수 착시 신호가 없습니다.</li>'
    composite = num(data.get("composite"))
    coverage = data.get("coverage") or {}
    return (
        '<h2 data-kmb-section="market-strength">시장 힘</h2>'
        f'<p class="section-note">시장 체력 종합값 {esc(composite)} · 사용 축 {esc(coverage.get("available",0))}/{esc(coverage.get("total",0))}. 누락 축은 임의 점수로 채우지 않습니다.</p>'
        f'<div class="metric-grid">{cards}</div><article class="card" style="margin-top:12px"><h3>지수 착시 확인</h3><ul>{illusions}</ul></article>'
    )


def _flows(data: dict[str, Any]) -> str:
    markets = data.get("markets") or {}
    blocks=[]
    for market in ("KOSPI","KOSDAQ"):
        row=markets.get(market) or {}
        items=[]
        for key,label in (("foreign","외국인"),("institution","기관"),("individual","개인")):
            v=row.get(key) or {}
            net=v.get("net_100m_krw")
            velocity=v.get("velocity_100m_krw_per_min")
            arrow="전환" if v.get("reversal") else "유지"
            items.append(f'<li><b>{label}</b> {num(net, suffix="억원", digits=0)} · 속도 {num(velocity, suffix="억원/분", digits=1)} · {arrow}</li>')
        blocks.append(f'<article class="card"><h3>{market}</h3><ul>{"".join(items)}</ul></article>')
    return '<h2 data-kmb-section="flows">시장 수급</h2><p class="section-note">순매수 누적값뿐 아니라 최근 스냅샷 간 속도·가속·방향전환을 분리합니다. 공개 보조 데이터는 공식 KRX 수급과 동일하게 취급하지 않습니다.</p><div class="grid">'+("".join(blocks) or '<p class="empty">수급 데이터 수집 전입니다.</p>')+'</div>'


def _futures_global(futures: dict[str, Any], global_data: dict[str, Any]) -> str:
    k200=futures.get("KOSPI200_FUTURES") or {}
    kbody=(
        f'{badge(k200.get("status"))}<p><b>종목:</b> {esc(k200.get("instrument"))}</p><p><b>종가:</b> {esc(num(k200.get("close"),digits=2))} · <b>베이시스:</b> {esc(num(k200.get("basis"),digits=2))}</p><p><b>미결제약정:</b> {esc(num(k200.get("open_interest"),digits=0))}</p>'
        if k200.get("status") == "CONNECTED_EOD_PRIMARY" else f'{badge(k200.get("status"))}<p>{esc(k200.get("reason") or "공식 선물 데이터를 현재 확인할 수 없습니다.")}</p>'
    )
    q=global_data.get("quotes") or {}
    gl=[]
    for key,label in (("NASDAQ100_FUTURES","Nasdaq 100 선물"),("SP500_FUTURES","S&P 500 선물"),("SOX","SOX"),("VIX","VIX"),("USD_KRW","USD/KRW"),("WTI","WTI"),("GOLD","금")):
        row=q.get(key) or {}
        gl.append(f'<li><b>{label}</b> {num(row.get("price"),digits=2)} · {num(row.get("change_pct"),suffix="%",digits=2)}</li>')
    interp=(global_data.get("interpretation") or {})
    return (
        '<h2 data-kmb-section="futures-global">선물·글로벌 선행시장</h2><p class="section-note">선물과 글로벌 지표는 방향 예측이 아니라 국내 수급·시장폭과 함께 환경을 해석하는 입력입니다.</p>'
        f'<div class="grid"><article class="card"><h3>KOSPI200 선물</h3>{kbody}</article><article class="card"><h3>글로벌</h3><ul>{"".join(gl)}</ul></article><article class="card"><h3>조합 해석</h3>{badge(interp.get("evidence_state"))}<p>{esc(interp.get("label"))}</p><p class="section-note">{esc(interp.get("note"))}</p></article></div>'
    )


def _news(data: dict[str, Any]) -> str:
    issues=data.get("issues") or []
    cards=[]
    for issue in issues[:12]:
        channels=" · ".join(issue.get("impact_channels") or []) or "영향 경로 추가 확인 중"
        cards.append(
            f'<details class="card"><summary><strong>{esc(issue.get("headline"))}</strong><span class="summary-meta">기사 {esc(issue.get("article_count",0))} · 독립 매체 {esc(issue.get("independent_publishers",0))}</span></summary>'
            f'<p><b>상태:</b> {esc(issue.get("state"))} · <b>방향:</b> {esc(issue.get("market_bias"))}</p><p><b>영향 경로:</b> {esc(channels)}</p><p class="section-note">{esc(issue.get("reason"))}</p></details>'
        )
    return '<h2 data-kmb-section="news-issues">뉴스·이슈</h2><p class="section-note">중복 기사를 묶고 독립 출처 수를 세며, 제목 키워드만으로 호재·악재를 확정하지 않습니다.</p><div class="grid">'+("".join(cards) or '<p class="empty">현재 수집된 뉴스 이슈가 없습니다.</p>')+'</div>'


def _smart(data: dict[str, Any]) -> str:
    cards=[]
    for item in (data.get("items") or [])[:20]:
        cost=item.get("virtual_cost_range") or {}; remain=item.get("remaining_inventory_proxy") or {}
        cards.append(
            f'<article class="card"><div class="card-head"><strong>{esc(item.get("name"))} ({esc(item.get("code"))})</strong>{badge(item.get("evidence_state"))}</div>'
            f'<p><b>상태:</b> {esc(item.get("state"))} · <b>신뢰도:</b> {esc(item.get("confidence"))}</p>'
            f'<p><b>가상 평균단가 참고범위:</b> {num(cost.get("low"),digits=0)} ~ {num(cost.get("high"),digits=0)}</p>'
            f'<p><b>잔존 재고 프록시:</b> {num((remain.get("low")*100) if isinstance(remain.get("low"),(int,float)) else None,suffix="%",digits=0)} ~ {num((remain.get("high")*100) if isinstance(remain.get("high"),(int,float)) else None,suffix="%",digits=0)}</p>'
            f'<p><b>매집/흡수:</b> {num(item.get("accumulation_absorption_score"))} · <b>분배위험:</b> {num(item.get("distribution_risk_score"))}</p>'
            f'<p><b>외부수요:</b> {num(item.get("external_demand_score"))} · <b>추가상승 유인 프록시:</b> {num(item.get("additional_upside_incentive_proxy"))}</p>'
            f'<p class="section-note">실제 특정 계좌의 물량·평단·의도가 아니라 공개 데이터 기반 범위 추정입니다.</p></article>'
        )
    return '<h2 data-kmb-section="smart-money">큰손·종목 행동</h2><p class="section-note">거래량=매집량으로 두지 않습니다. 실제 특정 계좌의 보유량·평단·의도를 안다고 가정하지 않고 가격 복원력·상대 거래량·돌파·거래량 프로파일을 분리해 가상 범위와 반대가설을 보존합니다.</p><div class="grid">'+("".join(cards) or '<p class="empty">관심종목 데이터가 아직 수집되지 않았습니다.</p>')+'</div>'


def _system(data: dict[str, Any]) -> str:
    unresolved=data.get("unresolved") or []
    active=[x for x in unresolved if x.get("status") not in {"RESOLVED","CLOSED"}]
    mix=data.get("development_mix") or {}
    mix_text=(f'최근 24시간 제품개발 {num(mix.get("product_pct"),suffix="%",digits=1)} / 유지보수 {num(mix.get("maintenance_pct"),suffix="%",digits=1)}' if mix.get("product_pct") is not None else '70/30 분류 데이터가 아직 충분하지 않습니다.')
    items="".join(f'<li><b>{esc(x.get("status"))}</b> {esc(x.get("problem"))}<br><span class="section-note">재시도 조건: {esc(x.get("retry_condition"))}</span></li>' for x in active[:10]) or '<li>현재 표시할 미해결 항목이 없습니다.</li>'
    return f'<details class="card" style="margin-top:30px"><summary><strong>개발 비율·미해결 문제</strong></summary><p>{esc(mix_text)}</p><ul>{items}</ul></details>'


def render_market_intelligence(data: dict[str, Any]) -> str:
    if not data:
        return '<p class="empty">시장 인텔리전스 데이터가 아직 생성되지 않았습니다.</p>'
    nav='<nav class="card" aria-label="시장 기능 바로가기"><b>바로가기</b> · <a href="#market-strength">시장 힘</a> · <a href="#flows">수급</a> · <a href="#futures-global">선물·글로벌</a> · <a href="#news-issues">뉴스</a> · <a href="#smart-money">큰손 분석</a></nav>'
    # IDs are mirrored with section markers for usable in-page navigation.
    body=(
        nav
        + '<div id="market-strength">'+_strength(data.get("strength") or {})+'</div>'
        + '<div id="flows">'+_flows(data.get("flows") or {})+'</div>'
        + '<div id="futures-global">'+_futures_global(data.get("futures") or {},data.get("global") or {})+'</div>'
        + '<div id="news-issues">'+_news(data.get("issues") or {})+'</div>'
        + '<div id="smart-money">'+_smart(data.get("smart_money") or {})+'</div>'
        + _system(data)
    )
    return body
