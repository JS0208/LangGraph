const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, LevelFormat
} = require('/sessions/dazzling-funny-ride/docx_work/node_modules/docx');
const fs = require('fs');

// A4, 좌우 여백 1080 DXA → 본문 너비 = 11906 - 2160 = 9746 DXA
const CONTENT_W = 9746;
const KO = { name: "맑은 고딕", eastAsia: "맑은 고딕" };

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

function makeLabel(text) {
  return new Paragraph({
    spacing: { before: 180, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "1F4E79", space: 4 } },
    children: [new TextRun({ text, bold: true, size: 22, font: KO, color: "1F4E79" })]
  });
}

function makeSubhead(text) {
  return new Paragraph({
    spacing: { before: 140, after: 40 },
    children: [new TextRun({ text, bold: true, size: 21, font: KO, color: "1F4E79" })]
  });
}

function makeBullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 0, after: 50, line: 300 },
    children: [new TextRun({ text, size: 20, font: KO, color: "222222" })]
  });
}

function makeCell(text, isHeader, w) {
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: isHeader ? { fill: "D6E4F0", type: ShadingType.CLEAR } : undefined,
    margins: { top: 70, bottom: 70, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text, bold: isHeader, size: 19, font: KO })]
    })]
  });
}

// 열 너비: 레이블 1400 + 값 3473 + 레이블 1400 + 값 3473 = 9746
const C1 = 1400, C2 = 3473;
const infoTable = new Table({
  width: { size: CONTENT_W, type: WidthType.DXA },
  columnWidths: [C1, C2, C1, C2],
  rows: [
    new TableRow({ children: [
      makeCell("프로젝트명", true, C1),
      makeCell("GraphRAG 기반 다중 에이전트 금융 의사결정 지원 시스템", false, C2),
      makeCell("이름", true, C1),
      makeCell("권지성", false, C2),
    ]}),
    new TableRow({ children: [
      makeCell("학번", true, C1),
      makeCell("20211723", false, C2),
      makeCell("소속", true, C1),
      makeCell("AI소프트웨어학부 (부전공: 금융학부)", false, C2),
    ]}),
  ]
});

const doc = new Document({
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "-",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 200 } } }
      }]
    }]
  },
  styles: {
    default: { document: { run: { font: KO, size: 20 } } }
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1200, right: 1080, bottom: 1200, left: 1080 }
      }
    },
    children: [
      // 제목
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 60 },
        children: [new TextRun({ text: "Progress Report 1", bold: true, size: 40, font: KO, color: "1F4E79" })]
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 0, after: 260 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "1F4E79", space: 8 } },
        children: [new TextRun({ text: "2026년 5월 8일   |   고급캡스톤디자인", size: 19, font: KO, color: "777777" })]
      }),

      // 기본 정보
      makeLabel("■ 기본 정보"),
      infoTable,

      // 주요 내용
      makeLabel("■ 주요 내용"),
      new Paragraph({
        spacing: { before: 0, after: 60 },
        children: [new TextRun({
          text: "중간보고서(2026.04.13) 제출 당시: 터미널/콘솔 기반 프로토타입, 5노드 LangGraph 구조, 실 DB·LLM 연동 검증 완료. 이후 아래 항목들을 추가 구현하였다.",
          size: 20, font: KO, color: "444444"
        })]
      }),

      makeSubhead("1. Web UI 통합 및 Generative UI 완성 (4.14~5.03)"),
      makeBullet("터미널 기반 에이전트 로직을 Next.js 대시보드(FinGraph Insight)에 완전 연동"),
      makeBullet("SSE 기반 실시간 분석 스트리밍 브라우저 동작 확인"),
      makeBullet("분석 결과 3-패널 구성: Quantitative Metrics / Compliance Risk / Orchestrator Consensus"),
      makeBullet("HALT ENGINE / RUN ANALYSIS 버튼을 통한 실시간 제어 UI 구현"),

      makeSubhead("2. 에이전트 아키텍처 고도화 — 5노드 → 8노드"),
      makeBullet("intent_classifier 노드 추가: 그래프 진입 전 질의 의도 분류 및 경로 선택"),
      makeBullet("critic 노드 추가: 분석 결과의 인용 완결성·논리 모순 점수화"),
      makeBullet("reflector 노드 추가: critic 점수 미달 시 파이프라인 자동 재시도"),
      makeBullet("MAX_REFLEXIONS 가드 도입 → 무한루프 방지 로직 완성"),
      makeBullet("pytest 70건 전체 통과 / LocalFallbackGraph로 외부 의존 없는 전체 동작 검증"),

      makeSubhead("3. Retrieval 2.0 — 검색 계층 재설계"),
      makeBullet("임베딩 캐시(InMemory LRU+TTL / SQLite) 신설 → 반복 질의 비용 절감"),
      makeBullet("쿼리 플래너 도입: 복합 질의를 LLM 또는 휴리스틱으로 서브쿼리 분해"),
      makeBullet("Cypher 안전성 가드 적용: 읽기 전용 화이트리스트로 DB 무결성 보장"),
      makeBullet("프롬프트 인젝션 및 범위 외 질의 사전 차단 로직 추가"),

      makeSubhead("4. 메모리·보안·관측성 구축"),
      makeBullet("세션 체크포인터: PostgresSaver/SqliteSaver 기반 스레드별 상태 영속"),
      makeBullet("에피소드 아카이브: 분석 완료 세션 이력 저장"),
      makeBullet("보안: PII 가드레일, append-only 감사 로그, HS256 자체 JWT 인증"),
      makeBullet("관측성: Prometheus 호환 인메모리 메트릭, 구조화 로깅, trace_id 분산 추적"),

      makeSubhead("5. 인프라 및 평가 체계 (5.04~5.17 선행 착수)"),
      makeBullet("Dockerfile + docker-compose 구성 (fallback-first / --profile real 선택 기동)"),
      makeBullet("GitHub Actions CI: pytest 및 골든셋 pass rate 게이팅 적용"),
      makeBullet("골든셋 12문항(삼성전자·SK하이닉스·NAVER·카카오·LG CNS) 및 eval 하네스 구축"),

      // 향후 계획
      makeLabel("■ 향후 계획"),
      makeBullet("RAGAS 지표(faithfulness, answer_correctness) CI 게이팅 통합"),
      makeBullet("LLM 토큰 스트리밍 + SSE v2 결합으로 실시간 응답성 개선"),
      makeBullet("Multi-entity 쿼리(복수 기업 비교) 분해 정확도 보완"),
      makeBullet("5.25 최종 결과보고서 및 시연 동영상 제출"),
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync('/sessions/dazzling-funny-ride/mnt/LangGraph-main/Progress_Report_1_권지성.docx', buffer);
  console.log('Done!');
}).catch(e => { console.error(e); process.exit(1); });
