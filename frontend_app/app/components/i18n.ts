// Sprint 7 (Pillar 6 보강) — 미니멀 i18n.
// 추가 라이브러리 없이 ko/en 토글만 제공한다. 각 컴포넌트는 ``t(key)`` 만 사용.

export type Lang = 'ko' | 'en';

const STRINGS: Record<Lang, Record<string, string>> = {
  ko: {
    'app.title': 'FinGraph Insight',
    'nav.evidence': '근거',
    'nav.intent': '의도',
    'nav.critic': '비판자',
    'nav.status': '상태',
    'query.placeholder': '분석할 기업 및 리스크 요인을 입력하세요...',
    'query.subtitle': '실시간 LangGraph 실행 · v2 이벤트',
    'btn.run': '분석 실행',
    'btn.halt': '엔진 정지',
    'btn.interrupt': '개입',
    'panel.event_stream': '이벤트 스트림',
    'panel.synthesized': '종합 인텔리전스',
    'panel.consensus.ok': '합의 완료',
    'panel.consensus.fail': '합의 실패',
    'panel.exec_summary': '경영진 요약',
    'panel.kg.title': '지식 그래프 라이브 뷰',
    'panel.kg.linked': '연결된 노드',
    'panel.retrieval.mode': '검색 모드',
    'panel.compliance': '컴플라이언스 리스크',
    'panel.metrics': '정량 지표',
    'live.streaming': '스트리밍 중',
    'live.idle': '실행 대기',
    'aria.event_stream': '에이전트 이벤트 스트림 (실시간)',
    'aria.summary': '오케스트레이터 요약 (실시간 업데이트)',
  },
  en: {
    'app.title': 'FinGraph Insight',
    'nav.evidence': 'Evidence',
    'nav.intent': 'intent',
    'nav.critic': 'critic',
    'nav.status': 'Status',
    'query.placeholder': 'Enter a company and risk factor to analyze...',
    'query.subtitle': 'Real-time LangGraph Execution · v2 events',
    'btn.run': 'RUN ANALYSIS',
    'btn.halt': 'HALT ENGINE',
    'btn.interrupt': 'INTERRUPT',
    'panel.event_stream': 'Event Stream',
    'panel.synthesized': 'Synthesized Intelligence',
    'panel.consensus.ok': 'Consensus Reached',
    'panel.consensus.fail': 'Consensus Failed',
    'panel.exec_summary': 'Executive Summary',
    'panel.kg.title': 'Knowledge Graph Live View',
    'panel.kg.linked': 'Linked Nodes',
    'panel.retrieval.mode': 'Retrieval mode',
    'panel.compliance': 'Compliance Risk',
    'panel.metrics': 'Quantitative Metrics',
    'live.streaming': 'streaming',
    'live.idle': 'awaiting',
    'aria.event_stream': 'Agent event stream (live)',
    'aria.summary': 'Orchestrator summary (live updates)',
  },
};

export function t(lang: Lang, key: string): string {
  return STRINGS[lang]?.[key] ?? STRINGS.ko[key] ?? key;
}

export const LANG_LABELS: Record<Lang, string> = { ko: '한국어', en: 'English' };
