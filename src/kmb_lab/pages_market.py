from __future__ import annotations

from datetime import datetime, timezone
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
    cls = "ok" if raw in {"CONNECTED", "CONNECTED_EOD_PRIMARY", "CONNECTED_SECONDARY", "HEALTHY", "ESTIMATED", "RESOLVED"} else "warn" if raw in {"PARTIAL", "SHADOW", "USER_ACTION_REQUIRED", "HYPOTHESIS", "NEW", "PERSISTING", "STRENGTHENING", "WEAKENING"} else "bad" if raw in {"FAILED"} else "muted"
    labels = {
        "CONNECTED_EOD_PRIMARY": "공식 일별 연결",
        "CONNECTED_SECONDARY": "보조 데이터 연결",
        "USER_ACTION_REQUIRED": "사용자 설정 필요",
        "NOT_CONNECTED": "미연결",
        "ESTIMATED": "데이터 기반 추정",
        "SHADOW": "검증 중",
        "UNKNOWN": "확인 불가",
        "NEW": "등장",
        "PERSISTING": "지속",
        "STRENGTHENING": "강화",
        "WEAKENING": "완화",
        "RESOLVED": "해소",
        "UNDETERMINED": "판단 유보",
        "POSITIVE_BIAS": "상승 요인 가능",
        "NEGATIVE_BIAS": "하락 요인 가능",
        "MIXED": "혼합",
        "NEUTRAL": "중립",
        "FAILED": "수집 실패",
    }
    return f'<span class="badge {cls}">{esc(labels.get(raw, raw))}</span>'


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _relative(value: Any, now_value: Any) -> str:
    target = _parse_time(value)
    now = _parse_time(now_value) or datetime.now(timezone.utc)
    if target is None:
        return "시각 확인 필요"
    seconds = max(0, int((now - target).total_seconds()))
    if seconds < 60:
        return "방금 전"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    return target.astimezone().strftime("%m월 %d일 %H:%M")


def _join(values: Any, fallback: str = "추가 확인 중") -> str:
    if not isinstance(values, list):
        return fallback
    cleaned = [str(x) for x in values if x not in (None, "")]
    return " · ".join(cleaned[:8]) if cleaned else fallback


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
    turnover = ((data.get("turnover_detail") or {}).get("combined") or {})
    tv = turnover.get("total_trading_value_krw")
    adv_tv = turnover.get("advance_trading_value_krw")
    dec_tv = turnover.get("decline_trading_value_krw")
    adv_share = turnover.get("advance_directional_share")
    turnover_html = (
        '<article class="card" style="margin-top:12px"><h3>거래대금 내부 힘</h3>'
        f'<p><b>분석 종목:</b> {esc(turnover.get("stock_count") or 0)}개 · '
        f'<b>전체:</b> {num(tv/1e12 if isinstance(tv,(int,float)) else None,suffix="조원",digits=2)}</p>'
        f'<p><b>상승 종목:</b> {num(adv_tv/1e12 if isinstance(adv_tv,(int,float)) else None,suffix="조원",digits=2)} · '
        f'<b>하락 종목:</b> {num(dec_tv/1e12 if isinstance(dec_tv,(int,float)) else None,suffix="조원",digits=2)}</p>'
        f'<p><b>방향성 거래대금 중 상승 비중:</b> {num(adv_share*100 if isinstance(adv_share,(int,float)) else None,suffix="%",digits=1)}</p>'
        '<p class="section-note">단순 거래량이 아니라 상승·하락 종목에 실제 누적된 거래대금의 비중을 비교합니다. 공개 보조 데이터 기준입니다.</p></article>'
        if turnover.get("evidence_state") == "ESTIMATED"
        else '<article class="card" style="margin-top:12px"><h3>거래대금 내부 힘</h3><p>아직 전 종목 거래대금 집계가 충분하지 않습니다.</p></article>'
    )
    return (
        '<h2 data-kmb-section="market-strength">시장 힘</h2>'
        f'<p class="section-note">시장 체력 종합값 {esc(composite)} · 사용 축 {esc(coverage.get("available",0))}/{esc(coverage.get("total",0))}. 누락 축은 임의 점수로 채우지 않습니다.</p>'
        f'<div class="metric-grid">{cards}</div>{turnover_html}<article class="card" style="margin-top:12px"><h3>지수 착시 확인</h3><ul>{illusions}</ul></article>'
    )


def _flows(data: dict[str, Any], program: dict[str, Any] | None = None) -> str:
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
    program = program or {}
    if isinstance(program.get("net_100m_krw"), (int, float)):
        blocks.append(
            '<article class="card"><h3>KOSPI 프로그램</h3>'
            f'<p><b>총 순매수:</b> {num(program.get("net_100m_krw"), suffix="억원", digits=0)}</p>'
            f'<p><b>차익:</b> {num(program.get("arbitrage_net_100m_krw"), suffix="억원", digits=0)} · '
            f'<b>비차익:</b> {num(program.get("non_arbitrage_net_100m_krw"), suffix="억원", digits=0)}</p>'
            '<p class="section-note">네이버 공개 보조 데이터 기준이며 공식 KRX 원자료와 동일하게 취급하지 않습니다.</p></article>'
        )
    return '<h2 data-kmb-section="flows">시장 수급</h2><p class="section-note">순매수 누적값뿐 아니라 최근 스냅샷 간 속도·가속·방향전환을 분리합니다. 공개 보조 데이터는 공식 KRX 수급과 동일하게 취급하지 않습니다.</p><div class="grid">'+("".join(blocks) or '<p class="empty">수급 데이터 수집 전입니다.</p>')+'</div>'


def _futures_global(futures: dict[str, Any], global_data: dict[str, Any]) -> str:
    k200=futures.get("KOSPI200_FUTURES") or {}
    status = k200.get("status")
    if status in {"CONNECTED_EOD_PRIMARY", "CONNECTED_SECONDARY"}:
        flows = k200.get("investor_flow_100m_krw") or {}
        source_note = (
            "KRX 공식 일별 데이터"
            if status == "CONNECTED_EOD_PRIMARY"
            else "네이버 공개 보조 데이터 · KRX 공식 인증 미연결"
        )
        kbody=(
            f'{badge(status)}'
            f'<p><b>종목:</b> {esc(k200.get("instrument"))}</p>'
            f'<p><b>선물:</b> {esc(num(k200.get("close"),digits=2))} · '
            f'<b>전일대비:</b> {esc(num(k200.get("change"),digits=2))} '
            f'({esc(num(k200.get("change_pct"),suffix="%",digits=2))})</p>'
            f'<p><b>KOSPI200 현물:</b> {esc(num(k200.get("spot_kpi200"),digits=2))} · '
            f'<b>베이시스:</b> {esc(num(k200.get("basis"),digits=2))} '
            f'({esc(num(k200.get("basis_pct"),suffix="%",digits=2))})</p>'
            f'<p><b>선물 수급:</b> 외국인 {esc(num(flows.get("foreign"),suffix="억원",digits=0))} · '
            f'기관 {esc(num(flows.get("institution"),suffix="억원",digits=0))} · '
            f'개인 {esc(num(flows.get("individual"),suffix="억원",digits=0))}</p>'
            f'<p><b>미결제약정:</b> {esc(num(k200.get("open_interest"),digits=0))}</p>'
            f'<p class="section-note">{esc(source_note)}. 보조값은 공식 확정값으로 승격하지 않습니다.</p>'
        )
    else:
        kbody=f'{badge(status)}<p>{esc(k200.get("reason") or "선물 데이터를 현재 확인할 수 없습니다.")}</p>'

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


def _issue_card(issue: dict[str, Any], now_value: Any) -> str:
    channels = _join(issue.get("impact_channels"), "영향 경로 추가 확인 중")
    related = _join((issue.get("related_markets") or []) + (issue.get("related_sectors") or []) + (issue.get("related_stocks") or []))
    publishers = _join(issue.get("publishers"), "출처 확인 중")
    articles = issue.get("articles") or []
    links = "".join(
        f'<li><a href="{esc(a.get("url"))}" rel="noopener noreferrer">{esc(a.get("source") or a.get("publisher") or "출처")}</a> · {esc(a.get("headline") or a.get("title"))}</li>'
        for a in articles[:5] if a.get("url")
    )
    analysis = issue.get("ai_analysis") or {}
    ai_lines = "".join(
        f'<li><b>{esc(agent)}</b> · {esc((detail or {}).get("status") if isinstance(detail, dict) else detail)}'
        + (f' · {esc((detail or {}).get("summary"))}' if isinstance(detail, dict) and (detail or {}).get("summary") else "")
        + '</li>'
        for agent,detail in analysis.items()
    ) or '<li>아직 이 이슈와 연결된 AI 분석 기록이 없습니다.</li>'
    return (
        f'<details class="card"><summary><span>{badge(issue.get("state"))}</span><strong>{esc(issue.get("headline"))}</strong>'
        f'<span class="summary-meta">{esc(_relative(issue.get("latest_at") or issue.get("last_updated_at"), now_value))} · 기사 {esc(issue.get("article_count",0))} · 독립 출처 {esc(issue.get("independent_publishers",0))}</span></summary>'
        f'<p><b>시장 영향:</b> {badge(issue.get("market_bias"))}</p>'
        f'<p><b>왜 중요한가:</b> {esc(issue.get("why_important") or issue.get("reason"))}</p>'
        f'<p><b>관련:</b> {esc(related)}</p><p><b>영향 경로:</b> {esc(channels)}</p>'
        f'<p><b>반론/주의:</b> {esc(issue.get("counterpoint") or "뉴스와 가격의 동시 발생만으로 인과를 확정하지 않습니다.")}</p>'
        f'<p><b>다음 확인 변수:</b> {esc(_join(issue.get("next_variables")))}</p>'
        f'<p><b>출처:</b> {esc(publishers)} · 공식자료 {"있음" if issue.get("official_source_available") else "추가 확인 필요"}</p>'
        f'<details><summary>관련 기사</summary><ul>{links or "<li>표시 가능한 기사 링크가 없습니다.</li>"}</ul></details>'
        f'<details><summary>AI 분석 연결</summary><ul>{ai_lines}</ul></details></details>'
    )


def render_news_intelligence(data: dict[str, Any]) -> str:
    current = data.get("news") or {}
    issue_doc = data.get("issues") or {}
    digest = data.get("issue_digest") or {}
    issues = issue_doc.get("issues") or []
    now_value = issue_doc.get("generated_at") or current.get("generated_at")

    core = [x for x in issues if x.get("state") not in {"RESOLVED"}][:10]
    core_html = "".join(_issue_card(x, now_value) for x in core) or '<p class="empty">현재 확인된 핵심 시장 이슈가 없습니다.</p>'

    news_cards = []
    for item in (current.get("items") or [])[:24]:
        related = _join((item.get("related_markets") or []) + (item.get("related_sectors") or []) + (item.get("related_stocks") or []))
        source = item.get("source") or item.get("publisher") or "출처 확인 필요"
        href = item.get("url")
        title = item.get("headline") or item.get("title")
        source_html = f'<a href="{esc(href)}" rel="noopener noreferrer">{esc(source)}</a>' if href else esc(source)
        news_cards.append(
            f'<details class="card"><summary><strong>{esc(title)}</strong><span class="summary-meta">{esc(_relative(item.get("published_at") or item.get("observed_at"), now_value))} · {source_html}</span></summary>'
            f'<p><b>주제:</b> {esc(item.get("topic") or "시장일반")}</p><p><b>관련:</b> {esc(related)}</p>'
            f'<p><b>왜 확인하나:</b> {esc(item.get("reason") or "시장 반응과 공식자료를 추가 확인합니다.")}</p>'
            f'<p><b>출처 구분:</b> {esc(item.get("source_type") or "UNKNOWN")} · 공식자료 {"있음" if item.get("official_source_available") else "추가 확인 필요"}</p></details>'
        )
    news_html = "".join(news_cards) or '<p class="empty">최근 수집 창에서 표시할 뉴스가 없습니다. 데이터가 없다고 임의의 뉴스를 만들지 않습니다.</p>'

    linked = data.get("news_work_products") or []
    analysis_html = "".join(
        f'<article class="card"><div class="card-head"><strong>{esc(item.get("agent") or "AI")} · {esc(item.get("title"))}</strong>{badge(item.get("status"))}</div>'
        f'<p>{esc(item.get("summary"))}</p><p><b>연결 이슈:</b> {esc(_join(item.get("related_issue_ids")))}</p>'
        f'<p><b>다음:</b> {esc(item.get("next_work") or "추가 검증 계획 미기록")}</p></article>'
        for item in linked[:20]
    ) or '<p class="empty">현재 뉴스 이슈와 명시적으로 연결된 AI 작업물이 없습니다. 단순 실행 상태를 “분석 중”으로 표시하지 않습니다.</p>'

    timeline = []
    for issue in issues:
        for event in issue.get("history") or []:
            timeline.append({
                "at": event.get("at"),
                "state": event.get("state"),
                "headline": issue.get("headline"),
                "reason": event.get("reason"),
            })
    timeline.sort(key=lambda x: x.get("at") or "", reverse=True)
    timeline_html = "".join(
        f'<article class="timeline-item"><div class="timeline-dot"></div><div class="timeline-time">{esc(_relative(row.get("at"), now_value))}</div>'
        f'<div><strong>{badge(row.get("state"))} {esc(row.get("headline"))}</strong><p>{esc(row.get("reason"))}</p></div></article>'
        for row in timeline[:30]
    ) or '<p class="empty">아직 이슈 상태 변화 기록이 없습니다.</p>'

    collection = current.get("collection_status") or digest.get("collection_status") or "UNKNOWN"
    freshness = (
        f'뉴스 수집 {badge(collection)} · 마지막 수집 {esc(_relative(current.get("collection_attempted_at") or current.get("generated_at"), now_value))}'
        f' · 최신 기사 {esc(_relative(current.get("latest_news_at"), now_value))}'
        f' · 확인 쿼리 {esc(current.get("sources_checked") or digest.get("sources_checked") or 0)}개'
    )

    return (
        '<section data-kmb-section="news-issues">'
        '<h2 id="market-issues" data-kmb-section="market-issues">현재 시장 핵심 이슈</h2>'
        f'<p class="section-note">{freshness}. 뉴스 자체와 시장 인과는 분리해 표시합니다.</p><div class="grid">{core_html}</div>'
        '<h2 id="today-news" data-kmb-section="today-news">오늘 주요 뉴스</h2>'
        '<p class="section-note">중복 기사를 제거한 최근 뉴스입니다. 보조 뉴스 소스는 공식자료와 동일하게 취급하지 않습니다.</p>'
        f'<div class="grid">{news_html}</div>'
        '<h2 data-kmb-section="ai-news-analysis">AI 뉴스 분석</h2>'
        '<p class="section-note">실제 저장된 작업물에 관련 이슈 ID가 있을 때만 연결합니다. 실행 중이라는 추정은 하지 않습니다.</p>'
        f'<div class="grid">{analysis_html}</div>'
        '<h2 data-kmb-section="issue-timeline">이슈 변화</h2>'
        '<p class="section-note">등장 → 지속 → 강화 → 완화 → 해소 상태 변화를 최신순으로 보여줍니다.</p>'
        f'<div class="timeline">{timeline_html}</div></section>'
    )


def _relative_strength(data: dict[str, Any]) -> str:
    cards = []
    labels = {"STRONGER": "강함", "WEAKER": "약함", "SIMILAR": "비슷", "UNKNOWN": "확인 불가"}
    for item in (data.get("items") or [])[:20]:
        windows = item.get("windows") or {}
        rows = []
        for window in ("1", "3", "5", "20"):
            metric = windows.get(window) or {}
            rows.append(
                f'<tr><td>{window}일</td>'
                f'<td>{num(metric.get("stock_return_pct"), suffix="%", digits=2)}</td>'
                f'<td>{num(metric.get("benchmark_return_pct"), suffix="%", digits=2)}</td>'
                f'<td>{num(metric.get("excess_return_pct"), suffix="%", digits=2)}</td>'
                f'<td>{esc(labels.get(str(metric.get("state") or "UNKNOWN"), metric.get("state") or "확인 불가"))}</td></tr>'
            )
        cards.append(
            f'<article class="card"><div class="card-head"><strong>{esc(item.get("name"))} ({esc(item.get("code"))})</strong>{badge(item.get("evidence_state"))}</div>'
            f'<p><b>벤치마크:</b> {esc(item.get("benchmark") or "KOSPI")} · '
            f'<b>종합:</b> {esc(labels.get(str(item.get("overall_state") or "UNKNOWN"), item.get("overall_state") or "확인 불가"))} · '
            f'<b>가중 초과수익:</b> {num(item.get("weighted_excess_return_pct"), suffix="%", digits=2)}</p>'
            '<div class="table-wrap"><table><thead><tr><th>기간</th><th>종목</th><th>지수</th><th>초과</th><th>상태</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            '<p class="section-note">같은 거래일 종가 기준 상대성과입니다. 향후 상승 확률이나 매수 신호가 아닙니다.</p></article>'
        )
    return (
        '<h2 data-kmb-section="relative-strength">종목 상대강도</h2>'
        '<p class="section-note">관심종목이 KOSPI/KOSDAQ 벤치마크보다 실제로 강했는지 1·3·5·20거래일로 나눠 비교합니다.</p>'
        '<div class="grid">' + ("".join(cards) or '<p class="empty">상대강도 데이터가 아직 수집되지 않았습니다.</p>') + '</div>'
    )


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


def render_market_intelligence(data: dict[str, Any], *, include_news: bool = True) -> str:
    nav='<nav class="card" aria-label="시장 기능 바로가기"><b>바로가기</b> · <a href="#market-issues">핵심 이슈</a> · <a href="#today-news">뉴스</a> · <a href="#market-strength">시장 힘</a> · <a href="#flows">수급</a> · <a href="#futures-global">선물·글로벌</a> · <a href="#relative-strength">상대강도</a> · <a href="#smart-money">큰손 분석</a></nav>'
    news = render_news_intelligence(data) if include_news else ""
    body=(
        nav
        + news
        + '<div id="market-strength">'+_strength(data.get("strength") or {})+'</div>'
        + '<div id="flows">'+_flows(data.get("flows") or {}, ((data.get("current") or {}).get("program") or {}))+'</div>'
        + '<div id="futures-global">'+_futures_global(data.get("futures") or {},data.get("global") or {})+'</div>'
        + '<div id="relative-strength">'+_relative_strength(data.get("relative_strength") or {})+'</div>'
        + '<div id="smart-money">'+_smart(data.get("smart_money") or {})+'</div>'
        + _system(data)
    )
    return body
