from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
AGENT_ORDER = ("AI-A", "AI-B", "AI-C", "AI-D", "AI-E")

STATUS_LABELS = {
    "ACTIVE": "정상 작동 중",
    "IN_PROGRESS": "진행 중",
    "PENDING": "검토 대기",
    "PASS": "검증 통과",
    "PASS_WITH_NOTES": "검증 통과 · 참고사항 있음",
    "FIX_REQUIRED": "수정 필요",
    "REJECT": "검증에서 제외",
    "REJECTED": "검증에서 제외",
    "UNKNOWN": "현재 확인할 수 없음",
    "NOT COLLECTED": "아직 데이터가 수집되지 않음",
    "NOT_COLLECTED": "아직 데이터가 수집되지 않음",
    "STALE": "최신 데이터 갱신 지연",
    "RECOVERY_REQUIRED": "자동 복구 필요",
    "RECOVERING": "자동 복구 중",
    "RESOLVED": "복구 완료",
    "RECOVERED": "복구 완료",
    "SHADOW": "실전 반영 전 검증 중",
    "DEGRADED": "최근 실행 확인 필요",
    "STATE MISMATCH": "표시 상태와 실제 실행 증거가 다름",
    "MISSING": "최근 실행 증거 없음",
    "FRESH": "최근 정상 확인",
    "OK": "정상",
    "SUCCESS": "성공",
    "FAILURE": "실패",
    "FAILED": "실패",
    "BLOCKED": "진행 차단",
    "REVIEWING": "공동 검증 중",
    "OPEN": "검토 필요",
    "COMPLETED": "완료",
    "CLOSED": "완료",
    "LIVE": "최신 페이지",
    "UNMAPPED": "실행 정보 연결 전",
    "NONE": "해당 없음",
    "OFFLINE": "실행 정보 확인 불가",
    "OBSERVED": "예약 실행 확인됨",
    "OBSERVED_NO_FRESH_OUTPUT": "실행 확인됨 · 새 결과 없음",
    "CONFIRMED": "공식 자료로 확인",
    "ESTIMATED": "데이터 기반 추정",
    "HYPOTHESIS": "검증 중인 가설",
    "VERIFIED_WITH_SUBSTITUTIONS": "대체 검토로 우선 검증 완료",
}

AGENT_INFO = {
    "AI-A": ("시장 탐색", "시장 이상 움직임·뉴스·테마·상대강도에서 새로운 분석 후보를 찾습니다."),
    "AI-B": ("근거 검증", "발견된 주장에 공식 근거가 있는지, 시간순서와 인과관계에 과장이 없는지 확인합니다."),
    "AI-C": ("수치 검증", "가상 보유물량·평균단가 범위·분배 가능성·과거 사례를 수치로 검증합니다."),
    "AI-D": ("시스템 검증", "데이터 수집·자동 배포·최신성·장애 복구가 정상인지 확인합니다."),
    "AI-E": ("개선·진화", "더 좋은 분석 방법과 화면 구조를 찾고 다음 연구 우선순위를 정합니다."),
}

TERM_REPLACEMENTS = (
    ("canonical", "공식 반영 데이터"),
    ("candidate", "검증 전 분석 후보"),
    ("material fingerprint", "화면 데이터 일치값"),
    ("provenance", "데이터 출처"),
    ("evidence", "근거"),
    ("source_commit", "마지막 반영 버전"),
    ("generated_at", "페이지 생성 시각"),
    ("review-board", "AI 공동 검증"),
    ("recovery queue", "장애 및 복구 현황"),
    ("recovery", "복구"),
    ("telemetry", "실시간 작동 상태"),
    ("writer lease", "공식 데이터 수정 권한"),
    ("stale sha", "오래된 버전 충돌"),
    ("dependency", "연결된 작업"),
    ("production eligible", "실전 분석 사용 가능 여부"),
    ("shadow mode", "실전 반영 전 시험 운영"),
    ("heartbeat", "최근 정상 작동 확인"),
    ("fallback", "대체 담당"),
    ("Pages", "공개 페이지"),
    ("workflow", "자동 실행"),
    ("Actions", "자동 실행"),
)

REVIEW_TITLE_MAP = {
    "Five-AI automatic verification and recovery mesh": "5개 AI 자동 검증·복구 체계",
    "GitHub Pages canonical-data closed loop and stale-page recovery": "공개 페이지 자동 업데이트·지연 복구 검증",
}

TASK_TITLE_MAP = {
    "Initialize five-agent shared memory": "5개 AI 공용 기억 체계 구축",
    "Replace UNKNOWN service telemetry with evidence-backed freshness": "실제 실행 증거 기반 시스템 상태 표시",
    "Make GitHub Pages follow material canonical state": "공식 데이터 변경을 공개 페이지에 자동 반영",
}

def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)

def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST)

def status_label(value: Any) -> str:
    raw = str(value if value not in (None, "") else "UNKNOWN").strip()
    return STATUS_LABELS.get(raw.upper(), raw if re.search(r"[가-힣]", raw) else "현재 확인할 수 없음")

def status_class(value: Any) -> str:
    upper = str(value).upper()
    if upper in {"ACTIVE","FRESH","OK","SUCCESS","LIVE","RECOVERED","RESOLVED","PASS","COMPLETED","CONFIRMED"}:
        return "ok"
    if upper in {"IN_PROGRESS","PENDING","DEGRADED","RECOVERING","STALE","STATE MISMATCH","PASS_WITH_NOTES","REVIEWING","OPEN","SHADOW","ESTIMATED","HYPOTHESIS","OBSERVED","OBSERVED_NO_FRESH_OUTPUT","VERIFIED_WITH_SUBSTITUTIONS"}:
        return "warn"
    if upper in {"BLOCKED","FAILED","FAILURE","FIX_REQUIRED","REJECT","REJECTED"}:
        return "bad"
    return "muted"

def _has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))

def _replace_terms(text: str) -> str:
    result = text
    for source, target in TERM_REPLACEMENTS:
        result = re.sub(re.escape(source), target, result, flags=re.IGNORECASE)
    for source, target in STATUS_LABELS.items():
        result = re.sub(rf"\b{re.escape(source)}\b", target, result, flags=re.IGNORECASE)
    return result

def user_text(value: Any, *, fallback: str = "현재 확인할 수 없음") -> str:
    if value in (None, "", [], {}):
        return fallback
    if isinstance(value, bool):
        return "예" if value else "아니요"
    if isinstance(value, (int, float)):
        return f"{value:,}"
    if isinstance(value, list):
        simple = [user_text(item, fallback="") for item in value[:5]]
        simple = [item for item in simple if item]
        return " · ".join(simple) if simple else fallback
    if isinstance(value, dict):
        vals = [user_text(v, fallback="") for v in list(value.values())[:5]]
        vals = [v for v in vals if v]
        return " · ".join(vals) if vals else f"세부 정보 {len(value)}개"
    text = _replace_terms(str(value).strip())
    if text.upper() in STATUS_LABELS:
        return status_label(text)
    return text

def human_time(value: Any, now_value: Any = None) -> str:
    target = _parse_time(value)
    if target is None:
        return "최근 실행 시각 확인 필요"
    now = _parse_time(now_value) or datetime.now(KST)
    delta = now - target
    if delta.total_seconds() < -60:
        return target.strftime("%m월 %d일 %H:%M")
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "방금 전"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}분 전"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}시간 전"
    if target.date() == (now - timedelta(days=1)).date():
        return f"어제 {target:%H:%M}"
    if target.year == now.year:
        return target.strftime("%m월 %d일 %H:%M")
    return target.strftime("%Y년 %m월 %d일 %H:%M")

def _technical_time(value: Any) -> str:
    parsed = _parse_time(value)
    return parsed.isoformat(timespec="seconds") if parsed else "확인 불가"

def _agent_last_time(row: dict[str, Any]) -> Any:
    return row.get("last_execution") or row.get("output_at") or row.get("heartbeat_at")

def _agent_current(row: dict[str, Any]) -> str:
    task = row.get("current_task")
    if isinstance(task, str) and task in TASK_TITLE_MAP:
        return TASK_TITLE_MAP[task]
    if isinstance(task, str) and task and task.upper() != "UNKNOWN":
        if _has_korean(task):
            return _replace_terms(task)
        lower = task.lower()
        if "page" in lower:
            return "공개 페이지 자동 업데이트 상태 확인"
        if "telemetry" in lower or "freshness" in lower:
            return "실제 실행 증거 기반 시스템 상태 확인"
        if "market" in lower:
            return "시장 데이터 상태 확인"
    status = str(row.get("status","UNKNOWN")).upper()
    if status == "DEGRADED":
        return "최근 실제 실행 증거를 확인하고 있습니다."
    return AGENT_INFO.get(row.get("agent"), ("AI 작업","현재 작업을 확인하고 있습니다."))[1]

def _agent_result(row: dict[str, Any]) -> str:
    result = str(row.get("last_result") or "")
    if not result or result.lower().startswith("no runtime"):
        return "최근 실행 결과를 확인할 충분한 증거가 없습니다."
    if _has_korean(result):
        return _replace_terms(result)
    lower = result.lower()
    if "review" in lower:
        return "최근 AI 공동 검증 기록이 있습니다."
    if "candidate" in lower or "research" in lower:
        return "최근 새로운 분석 후보 또는 연구 기록이 생성됐습니다."
    if "audit" in lower:
        return "최근 근거 검증 기록이 생성됐습니다."
    return "최근 활동 기록이 확인됐습니다."

def _activity_title(item: dict[str, Any]) -> str:
    raw = str(item.get("title") or "")
    if _has_korean(raw):
        return _replace_terms(raw)
    lower = raw.lower()
    if "recovery" in lower or "recover" in lower:
        return "장애 원인을 확인하고 복구 상태를 갱신했습니다."
    if "page" in lower or "deploy" in lower:
        return "공개 페이지 자동 업데이트 상태를 확인했습니다."
    if "review" in lower:
        return "다른 AI의 결과를 검증했습니다."
    if "discover" in lower or "candidate" in lower:
        return "새로운 시장 분석 후보를 발견했습니다."
    if "audit" in lower or "evidence" in lower:
        return "분석 근거와 출처를 검증했습니다."
    if "quant" in lower or "position" in lower:
        return "수치 분석 모델을 검토했습니다."
    if "writer" in lower or "canonical" in lower:
        return "검증된 결과의 공식 반영 과정을 확인했습니다."
    return f"{item.get('agent','AI')}의 최근 작업 기록이 갱신됐습니다."

def _market_label(label: str) -> str:
    return {
        "Behavior Event": "주요 시장 행동",
        "CONFIRMED": "공식 자료로 확인된 내용",
        "HYPOTHESIS": "검증 중인 가설",
        "UNKNOWN": "아직 확인되지 않은 항목",
    }.get(label, label)

def _market_value(value: Any) -> str:
    raw = str(value).upper() if not isinstance(value, (dict,list)) else ""
    if raw in {"UNKNOWN","NOT COLLECTED","NOT_COLLECTED"}:
        return status_label(raw)
    return user_text(value)

def _review_title(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "")
    if title in REVIEW_TITLE_MAP:
        return REVIEW_TITLE_MAP[title]
    if _has_korean(title):
        return _replace_terms(title)
    return "AI 공동 검증 항목"

def _review_progress(item: dict[str, Any]) -> tuple[int,int]:
    reviews = item.get("reviews") or {}
    done = 0
    for agent in AGENT_ORDER:
        result = str((reviews.get(agent) or {}).get("result","PENDING")).upper()
        if result not in {"PENDING","UNKNOWN","FIX_REQUIRED","REJECT"}:
            done += 1
    return done, len(AGENT_ORDER)

def _incident_title(item: dict[str, Any]) -> str:
    incident = str(item.get("incident_id",""))
    if "SOURCE-CONTRACT" in incident:
        return "공식 데이터 출처 검증 오류 복구"
    if "WRITER-SMOKE" in incident:
        return "공식 데이터 반영 과정 검증 복구"
    if "PAGES-STALE" in incident:
        return "공개 페이지 업데이트 지연 복구"
    return "시스템 장애 및 복구 기록"

def _workflow_name(name: str) -> str:
    return {
        "pages": "공개 페이지 자동 업데이트",
        "system-check": "시스템 자동 점검",
        "canonical-writer": "검증 결과 공식 반영",
    }.get(name, "자동 실행 작업")

def _research_title(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "")
    if "primary-source" in title.lower() or "provenance" in title.lower():
        return "가설 확정 전 공식 원자료 연결"
    if _has_korean(title):
        return _replace_terms(title)
    return "추가 검증이 필요한 연구 과제"

def _research_reason(item: dict[str, Any]) -> str:
    reason = str(item.get("reason") or "")
    if _has_korean(reason):
        return _replace_terms(reason)
    if "secondary" in reason.lower() or "primary" in reason.lower():
        return "현재 분석 후보의 공식 원자료 확인이 충분하지 않아 먼저 데이터 출처를 연결해야 합니다."
    return "실전 분석에 반영하기 전에 추가 근거와 검증이 필요합니다."

def _experiment_title(item: dict[str, Any]) -> str:
    name = str(item.get("name") or item.get("id") or "")
    if "virtual position" in name.lower():
        return "가상 보유물량 범위 추정 모델"
    if _has_korean(name):
        return _replace_terms(name)
    return "실험 중인 분석 모델"

def _experiment_reason(item: dict[str, Any]) -> str:
    samples = item.get("sample_count")
    if samples == 0:
        return "아직 검증된 과거 표본이 없어 실제 분석 결과에는 사용하지 않습니다."
    return "실전 반영 전에 과거 사례와 시장 구간별 성능을 추가 검증하고 있습니다."

def _recent_activity_count(activity: list[dict[str, Any]], now_value: Any, minutes: int = 10) -> int:
    now = _parse_time(now_value) or datetime.now(KST)
    count = 0
    for item in activity:
        at = _parse_time(item.get("at"))
        if at and timedelta(0) <= now - at <= timedelta(minutes=minutes):
            count += 1
    return count

def _visible_technical_text(value: Any) -> str:
    if value in (None,"",[],{}):
        return "확인 불가"
    if isinstance(value,(list,dict)):
        return f"기술 세부 항목 {len(value)}개"
    return _replace_terms(str(value))

def render_korean_html(model: dict[str, Any]) -> str:
    now_value = model.get("generated_at")
    briefing = model.get("briefing") or {}
    agents_by_name = {row.get("agent"): row for row in (model.get("agents") or [])}
    agents = [agents_by_name.get(agent, {"agent":agent,"status":"UNKNOWN"}) for agent in AGENT_ORDER]

    valid_times = [(idx,_parse_time(_agent_last_time(row))) for idx,row in enumerate(agents)]
    valid_times = [(idx,t) for idx,t in valid_times if t is not None]
    active_idx = max(valid_times,key=lambda x:x[1])[0] if valid_times else None

    market_cards = "".join(
        f'<article class="metric"><span>{_esc(_market_label(str(label)))}</span><strong>{_esc(_market_value(value))}</strong></article>'
        for label,value in (model.get("market") or {}).items()
    ) or '<p class="empty">아직 시장 요약 데이터가 수집되지 않았습니다.</p>'

    cycle_cards=[]
    for idx,row in enumerate(agents):
        agent=str(row.get("agent") or AGENT_ORDER[idx])
        short,desc=AGENT_INFO[agent]
        status=str(row.get("status","UNKNOWN"))
        current=_agent_current(row)
        result=_agent_result(row)
        last=human_time(_agent_last_time(row),now_value)
        active=" current" if idx==active_idx else ""
        cycle_cards.append(
            f'<article class="cycle-card{active}" aria-label="{_esc(agent)} {short}">'
            f'<div class="cycle-step">{idx+1}</div><div class="cycle-head"><strong>{agent} · {_esc(short)}</strong>'
            f'<span class="badge {status_class(status)}">{_esc(status_label(status))}</span></div>'
            f'<p class="role">{_esc(desc)}</p><p><b>현재:</b> {_esc(current)}</p>'
            f'<p><b>최근 활동:</b> {_esc(last)}</p><p><b>최근 결과:</b> {_esc(result)}</p>'
            f'<details><summary>기술 정보 보기</summary>'
            f'<p>내부 상태: {_esc(status)}</p><p>마지막 실행 기록: {_esc(_technical_time(_agent_last_time(row)))}</p>'
            f'<p>최근 정상 작동 확인: {_esc(_technical_time(row.get("heartbeat_at")))}</p></details></article>'
        )
        if idx<len(agents)-1:
            cycle_cards.append('<div class="cycle-arrow" aria-hidden="true"><span></span></div>')
    cycle_cards.append('<div class="cycle-arrow return" aria-hidden="true"><span></span></div>')

    activity=model.get("activity") or []
    activity_count=_recent_activity_count(activity,now_value)
    activity_intro=(f"최근 10분 동안 확인된 활동은 {activity_count}건입니다." if activity_count else "최근 10분 동안 새로 확인된 활동이 없습니다.")
    activity_html="".join(
        f'<article class="timeline-item"><div class="timeline-dot"></div><div class="timeline-time">{_esc(human_time(item.get("at"),now_value))}</div>'
        f'<div><strong>{_esc(str(item.get("agent") or "SYSTEM"))}</strong><p>{_esc(_activity_title(item))}</p>'
        f'<details><summary>기술 기록 보기</summary><p>원래 기록 시각: {_esc(_technical_time(item.get("at")))}</p>'
        f'<p>{_esc(_visible_technical_text(item.get("title")))}</p></details></div></article>'
        for item in activity[:20]
    ) or '<p class="empty">아직 표시할 최근 활동 기록이 없습니다.</p>'

    review_html=""
    if isinstance(model.get("review"),dict):
        for item in model["review"].get("items",[]):
            done,total=_review_progress(item)
            reviews=item.get("reviews") or {}
            badges="".join(
                f'<span class="badge {status_class((reviews.get(agent) or {}).get("result","PENDING"))}">{agent} · {_esc(status_label((reviews.get(agent) or {}).get("result","PENDING")))}</span>'
                for agent in AGENT_ORDER
            )
            next_action=str(item.get("next_action") or "")
            next_text=_replace_terms(next_action) if _has_korean(next_action) else "남은 AI의 독립 검증과 필요한 수정 반영을 기다리고 있습니다."
            review_html+=(
                f'<details class="card"><summary><strong>{_esc(_review_title(item))}</strong>'
                f'<span class="summary-meta">{done}/{total}개 역할 검증 완료</span></summary>'
                f'<div class="badge-row">{badges}</div><p><b>현재:</b> {_esc(status_label(item.get("status","UNKNOWN")))}</p>'
                f'<p><b>다음:</b> {_esc(next_text)}</p><details><summary>기술 정보 보기</summary>'
                f'<p>내부 검증 ID: {_esc(item.get("review_id","확인 불가"))}</p>'
                f'<p>마지막 반영 버전: {_esc(str((item.get("evidence") or {}).get("commit_sha","확인 불가"))[:12])}</p></details></details>'
            )
    if not review_html:
        review_html='<p class="empty">현재 진행 중인 AI 공동 검증 항목이 없습니다.</p>'

    incidents=(model.get("recovery") or {}).get("incidents",[]) if isinstance(model.get("recovery"),dict) else []
    recovery_html="".join(
        f'<details class="card"><summary><span class="badge {status_class(i.get("status","UNKNOWN"))}">{_esc(status_label(i.get("status","UNKNOWN")))}</span>'
        f'<strong>{_esc(_incident_title(i))}</strong></summary>'
        f'<p>문제가 발견되면 관련 기능만 격리해 복구하고 다른 독립 작업은 계속 진행합니다.</p>'
        f'<details><summary>기술 정보 보기</summary><p>장애 ID: {_esc(i.get("incident_id","확인 불가"))}</p>'
        f'<p>복구 담당: {_esc(i.get("recovery_owner","확인 불가"))}</p>'
        f'<p>원인 기록: {_esc(_visible_technical_text(i.get("root_cause")))}</p></details></details>'
        for i in incidents[-10:]
    ) or '<p class="empty">현재 표시할 복구 기록이 없습니다.</p>'

    workflows=(model.get("workflows") or {}).get("latest",{}) if isinstance(model.get("workflows"),dict) else {}
    workflow_html="".join(
        f'<article class="card compact"><h3>{_esc(_workflow_name(name))}</h3>'
        f'<p><span class="badge {status_class(run.get("conclusion") or run.get("status") or "UNKNOWN")}">{_esc(status_label(run.get("conclusion") or run.get("status") or "UNKNOWN"))}</span></p>'
        f'<p>최근 실행: {_esc(human_time(run.get("created_at"),now_value))}</p>'
        f'<details><summary>기술 정보 보기</summary><p>실행 번호: {_esc(run.get("id","확인 불가"))}</p>'
        f'<p>반영 버전: {_esc(str(run.get("head_sha") or "확인 불가")[:12])}</p></details></article>'
        for name,run in workflows.items()
    ) or '<p class="empty">자동 실행 상태를 현재 확인할 수 없습니다.</p>'

    research_items=(model.get("research") or {}).get("items",[]) if isinstance(model.get("research"),dict) else []
    research_html="".join(
        f'<details class="card"><summary><strong>{_esc(_research_title(item))}</strong>'
        f'<span class="badge {status_class(item.get("status","UNKNOWN"))}">{_esc(status_label(item.get("status","UNKNOWN")))}</span></summary>'
        f'<p>{_esc(_research_reason(item))}</p><p><b>근거 상태:</b> {_esc(status_label(item.get("evidence_state","UNKNOWN")))}</p>'
        f'<details><summary>기술 정보 보기</summary><p>연구 ID: {_esc(item.get("id","확인 불가"))}</p></details></details>'
        for item in research_items[:20]
    ) or '<p class="empty">현재 추가 검증 대기 중인 연구 과제가 없습니다.</p>'

    exp_items=(model.get("experiments") or {}).get("experiments",[]) if isinstance(model.get("experiments"),dict) else []
    exp_html="".join(
        f'<article class="card"><div class="card-head"><strong>{_esc(_experiment_title(item))}</strong>'
        f'<span class="badge {status_class(item.get("status","UNKNOWN"))}">{_esc(status_label(item.get("status","UNKNOWN")))}</span></div>'
        f'<p>{_esc(_experiment_reason(item))}</p><p><b>현재 검증 표본:</b> {_esc(item.get("sample_count","확인 불가"))}건</p>'
        f'<p><b>실전 분석 사용:</b> {"가능" if item.get("production_eligible") is True else "아직 사용하지 않음"}</p>'
        f'<details><summary>기술 정보 보기</summary><p>실험 ID: {_esc(item.get("id","확인 불가"))}</p></details></article>'
        for item in exp_items[:20]
    ) or '<p class="empty">현재 등록된 분석 실험이 없습니다.</p>'

    big_money_html=exp_html if exp_items else (
        '<article class="card"><strong>가상 보유물량·분배 분석</strong>'
        '<p>아직 실전 반영 가능한 검증 모델이 없습니다. 공식 시장 데이터와 과거 표본이 쌓일 때까지 임의의 세력 평단·보유량·재상승 확률을 만들지 않습니다.</p></article>'
    )

    briefing_items=[]
    for title,key in (
        ("지금 시장에서 중요한 것","지금 가장 중요한 시장 변화"),
        ("현재 확인 중인 문제","현재 문제"),
        ("다음 조사 순서","다음 우선순위"),
    ):
        items=briefing.get(key) or []
        body="".join(f"<li>{_esc(user_text(x))}</li>" for x in items[:5]) or "<li>현재 표시할 확인된 내용이 없습니다.</li>"
        briefing_items.append(f'<article class="card"><h3>{_esc(title)}</h3><ul>{body}</ul></article>')
    briefing_html="".join(briefing_items)

    source_short=str(model.get("source_commit","확인 불가"))[:12]
    fingerprint=str(model.get("material_fingerprint",""))
    generated=human_time(model.get("generated_at"),model.get("generated_at"))

    agent_health_html="".join(
        f'<article class="card"><div class="card-head"><strong>{_esc(row.get("agent"))} · {_esc(AGENT_INFO[row.get("agent")][0])}</strong>'
        f'<span class="badge {status_class(row.get("status"))}">{_esc(status_label(row.get("status")))}</span></div>'
        f'<p>{_esc(_agent_current(row))}</p><p class="section-note">최근 활동: {_esc(human_time(_agent_last_time(row),now_value))}</p></article>'
        for row in agents
    )

    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="kmb-source-commit" content="{_esc(model.get('source_commit',''))}"><meta name="kmb-generated-at" content="{_esc(model.get('generated_at',''))}"><meta name="kmb-material-fingerprint" content="{_esc(fingerprint)}">
<title>KMB · 한국 시장 행동 연구소</title>
<style>
:root{{--bg:#f5f7fa;--card:#fff;--line:#e4e8ee;--text:#111827;--muted:#64748b;--ok:#087f5b;--okbg:#eafaf3;--warn:#9a6700;--warnbg:#fff7db;--bad:#c92a2a;--badbg:#fff0f0;--accent:#3157d5;--accentbg:#eef2ff}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font-family:"Pretendard","Noto Sans KR",system-ui,-apple-system,"Segoe UI",sans-serif;word-break:keep-all}}main{{max-width:1240px;margin:auto;padding:20px}}header{{background:linear-gradient(135deg,#fff,#f7f9ff);border:1px solid var(--line);border-radius:20px;padding:24px;margin-bottom:20px}}h1{{font-size:clamp(26px,4vw,42px);margin:8px 0 10px;letter-spacing:-.04em}}h2{{margin:34px 0 8px;font-size:clamp(20px,3vw,26px);letter-spacing:-.025em}}h3{{margin:0 0 10px;font-size:16px}}p,li{{line-height:1.65}}ul{{padding-left:20px;margin:8px 0}}.lead{{font-size:16px;max-width:850px;color:#334155;margin:0}}.meta{{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:13px}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}.metric-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}}.card,.metric,.timeline-item{{background:var(--card);border:1px solid var(--line);border-radius:15px;padding:16px}}.card-head,.cycle-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}}.metric span{{display:block;color:var(--muted);font-size:13px;margin-bottom:8px}}.metric strong{{font-size:15px;overflow-wrap:anywhere}}.badge{{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:750;background:#f1f5f9;color:#475569;margin:2px;white-space:nowrap}}.badge.ok{{background:var(--okbg);color:var(--ok)}}.badge.warn{{background:var(--warnbg);color:var(--warn)}}.badge.bad{{background:var(--badbg);color:var(--bad)}}.badge.muted{{background:#f1f5f9;color:#64748b}}.section-note,.empty{{color:var(--muted);font-size:14px}}.cycle-wrap{{display:flex;align-items:stretch;gap:8px;overflow-x:auto;padding:8px 2px 14px}}.cycle-card{{position:relative;flex:1 0 190px;max-width:230px;background:#fff;border:1px solid var(--line);border-radius:18px;padding:15px;transition:transform .2s,border-color .2s,box-shadow .2s}}.cycle-card.current{{border-color:#91a7ff;box-shadow:0 0 0 4px #eef2ff;animation:pulse 2.4s ease-in-out infinite}}.cycle-step{{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--accentbg);color:var(--accent);font-weight:800;margin-bottom:10px}}.cycle-card .role{{color:var(--muted);font-size:13px;min-height:66px}}.cycle-card p{{font-size:13px;margin:8px 0}}.cycle-arrow{{display:grid;place-items:center;min-width:28px;position:relative}}.cycle-arrow:before{{content:"";width:100%;height:2px;background:#cbd5e1}}.cycle-arrow span{{position:absolute;width:7px;height:7px;border-radius:50%;background:var(--accent);animation:flow 1.8s linear infinite}}.cycle-arrow.return{{display:none}}.timeline{{display:grid;gap:9px}}.timeline-item{{display:grid;grid-template-columns:12px 90px 1fr;gap:12px;align-items:start}}.timeline-item p{{margin:2px 0}}.timeline-dot{{width:10px;height:10px;border-radius:50%;background:var(--accent);margin-top:7px}}.timeline-time{{color:var(--muted);font-size:13px;padding-top:3px}}details{{margin-top:10px}}details>summary{{cursor:pointer;line-height:1.55;color:#334155}}details details{{margin-left:8px;padding-left:10px;border-left:2px solid #eef2f7}}.summary-meta{{color:var(--muted);font-size:12px;margin-left:8px}}.badge-row{{margin:10px 0}}.tech-footer{{margin:32px 0 12px;padding:14px 0;border-top:1px solid var(--line);color:var(--muted);font-size:12px}}
@keyframes flow{{0%{{transform:translateX(-10px);opacity:0}}20%{{opacity:1}}80%{{opacity:1}}100%{{transform:translateX(10px);opacity:0}}}}@keyframes pulse{{0%,100%{{box-shadow:0 0 0 2px #eef2ff}}50%{{box-shadow:0 0 0 6px #eef2ff}}}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}.metric-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:680px){{main{{padding:12px}}header{{padding:18px}}.grid,.metric-grid{{grid-template-columns:1fr}}.cycle-wrap{{display:grid;grid-template-columns:1fr;overflow:visible}}.cycle-card{{max-width:none;min-width:0}}.cycle-arrow{{height:24px;min-width:0}}.cycle-arrow:before{{width:2px;height:100%}}.cycle-arrow span{{animation:flowY 1.8s linear infinite}}.timeline-item{{grid-template-columns:10px 1fr}}.timeline-time{{grid-column:2}}}}
@keyframes flowY{{0%{{transform:translateY(-8px);opacity:0}}20%{{opacity:1}}80%{{opacity:1}}100%{{transform:translateY(8px);opacity:0}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important}}.cycle-card.current,.cycle-arrow span{{animation:none!important}}}}
</style></head>
<body data-source-commit="{_esc(model.get('source_commit',''))}" data-material-fingerprint="{_esc(fingerprint)}"><main>
<header><div class="meta"><span class="badge ok">공개 페이지 최신 반영</span><span>마지막 화면 생성: {_esc(generated)}</span></div>
<h1>한국 시장 행동 연구소</h1><p class="lead">한국 주식시장의 큰 자금 움직임과 시장 행동을 5개의 AI가 서로 발견하고 반박하고 검증하면서 계속 연구합니다. 확인되지 않은 내용은 사실처럼 표시하지 않습니다.</p></header>

<h2 data-kmb-section="overview">지금 한눈에 보기</h2><p class="section-note">시장·연구·시스템에서 지금 알아야 할 내용만 먼저 보여줍니다.</p><div class="grid">{briefing_html}</div>

<h2 data-kmb-section="market">현재 시장 요약</h2><p class="section-note">공식 시장 데이터가 아직 연결되지 않은 항목은 임의 숫자를 만들지 않고 수집 전 또는 확인 불가로 표시합니다.</p><div class="metric-grid">{market_cards}</div>

<h2 data-kmb-section="cycle">5개 AI 연구 순환</h2><p class="section-note">{_esc(activity_intro)} 가장 최근 실행 증거가 있는 AI를 부드럽게 강조합니다.</p><div class="cycle-wrap">{''.join(cycle_cards)}</div>

<h2 data-kmb-section="activity">최근 AI 협업 흐름</h2><p class="section-note">기술 로그 대신 각 AI가 어떤 일을 했는지 시간순으로 보여줍니다.</p><div class="timeline">{activity_html}</div>

<h2 data-kmb-section="experiments">큰손·가상 포지션 분석</h2><p class="section-note">특정 계좌의 실제 보유량·평단을 안다고 가정하지 않습니다. 공개 시장 데이터로 가능한 범위만 추정하며 검증 전 모델은 실전에 사용하지 않습니다.</p><div class="grid">{big_money_html}</div>

<h2 data-kmb-section="research">현재 검증 중인 연구</h2>{research_html}

<h2 data-kmb-section="review">AI 공동 검증 결과</h2><p class="section-note">한 AI의 판단으로 끝내지 않고 5개 역할이 서로 다른 관점에서 검증합니다.</p>{review_html}

<h2 data-kmb-section="agent-health">AI 작동 상태</h2><p class="section-note">저장소에 적힌 정상이라는 글자보다 실제 최근 실행·결과 증거를 우선합니다.</p><div class="grid">{agent_health_html}</div>

<h2 data-kmb-section="recovery">장애 및 복구 현황</h2>{recovery_html}

<h2 data-kmb-section="actions">자동 실행 상태</h2><div class="grid">{workflow_html}</div>

<details class="card" style="margin-top:30px"><summary><strong>개발자용 기술 정보</strong></summary>
<p>마지막 반영 버전: {_esc(source_short)}</p><p>정확한 페이지 생성 시각: {_esc(model.get('generated_at','확인 불가'))}</p><p>화면 데이터 일치값: {_esc(fingerprint[:16])}</p>
<p>이 영역은 공개 페이지가 저장소의 최신 상태와 일치하는지 점검하기 위한 정보입니다.</p></details>
<footer class="tech-footer">이 화면은 저장소의 검증 데이터에서 자동 생성됩니다. 데이터가 없으면 임의로 채우지 않습니다.</footer>
</main></body></html>"""
