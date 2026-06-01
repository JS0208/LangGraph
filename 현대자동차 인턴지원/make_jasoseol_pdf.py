from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── 폰트 등록 ──
pdfmetrics.registerFont(UnicodeCIDFont('HYGothic-Medium'))
pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))

# ── 색상 ──
NAVY      = colors.HexColor('#1F3864')
DARK_GRAY = colors.HexColor('#2D2D2D')
MID_GRAY  = colors.HexColor('#666666')
WHITE     = colors.white

KO = 'HYGothic-Medium'

# ── 스타일 ──
s_name = ParagraphStyle('name',
    fontName=KO, fontSize=22, textColor=NAVY,
    leading=28, spaceAfter=3, alignment=TA_LEFT)

s_sub = ParagraphStyle('sub',
    fontName=KO, fontSize=10, textColor=DARK_GRAY,
    leading=15, spaceAfter=2, alignment=TA_LEFT)

s_link = ParagraphStyle('link',
    fontName=KO, fontSize=9.5, textColor=NAVY,
    leading=14, spaceAfter=0, alignment=TA_LEFT)

s_tech = ParagraphStyle('tech',
    fontName=KO, fontSize=9, textColor=NAVY,
    leading=14, spaceAfter=0, alignment=TA_LEFT)

s_open = ParagraphStyle('open',
    fontName=KO, fontSize=10.5, textColor=DARK_GRAY,
    leading=17, spaceAfter=0, alignment=TA_JUSTIFY,
    wordWrap='CJK')

s_body = ParagraphStyle('body',
    fontName=KO, fontSize=10, textColor=DARK_GRAY,
    leading=16.5, spaceAfter=0, alignment=TA_JUSTIFY,
    wordWrap='CJK')

def hr_thick():
    return HRFlowable(width='100%', thickness=2, color=NAVY,
                      spaceAfter=7, spaceBefore=0)

def hr_thin():
    return HRFlowable(width='100%', thickness=0.5,
                      color=colors.HexColor('#AAAAAA'),
                      spaceAfter=10, spaceBefore=0)

def sp(n=6):
    return Spacer(1, n)

def build():
    out = '/sessions/friendly-stoic-thompson/mnt/LangGraph-main/2026_인턴지원/자소서_권지성_현대자동차.pdf'
    doc = SimpleDocTemplate(out, pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2.5*cm, bottomMargin=2.5*cm)

    story = []

    # ── 헤더 블록 ──
    story.append(Paragraph('권지성', s_name))
    story.append(Paragraph('숭실대학교 컴퓨터공학부  ·  금융학부 부전공', s_sub))
    story.append(Paragraph('github.com/JS0208  ·  rnjswltjd0208@gmail.com', s_link))
    story.append(sp(10))
    story.append(hr_thick())

    # ── 기술 스택 한 줄 ──
    story.append(sp(2))
    story.append(Paragraph(
        'Python  ·  FastAPI  ·  LangGraph  ·  Neo4j  ·  Qdrant  '
        '·  Prometheus  ·  OpenTelemetry  ·  JWT',
        s_tech))
    story.append(sp(8))
    story.append(hr_thin())

    # ── 오프닝 ──
    story.append(KeepTogether([
        Paragraph(
            'LLM 기반 멀티에이전트 시스템을 처음부터 혼자 설계하고 구현했습니다.',
            s_open),
        sp(12),
    ]))

    # ── 본론 1 — 기술 경험 ──
    story.append(Paragraph(
        '숭실대학교 컴퓨터공학부 재학 중, GraphRAG 기반 금융 분석 멀티에이전트 시스템을 개발했습니다. '
        'LangGraph로 의도 분류·컨텍스트 검색·재무 분석·리스크 감사·반성·비평·오케스트레이터 등 '
        '8개 전문화 에이전트를 오케스트레이션하고, FastAPI RESTful API와 마이크로서비스 패턴으로 '
        '서비스 레이어를 구성했습니다. Neo4j와 Qdrant를 결합한 하이브리드 검색으로 '
        '멀티홉 컨텍스트 정확도를 높였습니다.',
        s_body))
    story.append(sp(12))

    # ── 본론 2 — 문제 해결 (실시간성·SSE) ──
    story.append(Paragraph(
        '핵심 과제는 \'실시간성\'이었습니다. SSE(Server-Sent Events)와 asyncio Queue 기반 '
        'ping 에미터를 직접 설계해 멀티에이전트 처리 결과를 클라이언트에 실시간 스트리밍했습니다. '
        '노드 처리 중 네트워크가 유휴 상태가 되면 프록시가 연결을 조용히 끊는 문제를, '
        '15초 간격 keepalive ping으로 해결했습니다. '
        '노드 응답이 30초를 초과하면 TimeoutError를 catch해 fallback 이벤트를 송출하고 '
        'graceful하게 종료했으며, 사용자 중단 요청은 interrupt 엔드포인트와 cancel 폴링으로 '
        '처리해 finally 블록에서 태스크를 빠짐없이 정리했습니다.',
        s_body))
    story.append(sp(12))

    # ── 본론 3 — 모니터링·보안 ──
    story.append(Paragraph(
        'Prometheus 메트릭과 OpenTelemetry 분산 추적으로 노드별 지연·오류·트래픽을 가시화하고, '
        'JWT 인증·가드레일·감사 로그로 보안 계층도 직접 구성했습니다.',
        s_body))
    story.append(sp(12))

    # ── 구분선 ──
    story.append(hr_thin())

    # ── 마무리 ──
    story.append(Paragraph(
        '커넥티드 카 백엔드가 요구하는 실시간 알림 시스템 고도화와 지능형 모니터링은 '
        '이 경험에서 직접 파생됩니다. '
        '컴퓨터공학 전공과 금융학부 부전공의 교차점에서 기술과 도메인을 함께 보는 시각을 갖고 있습니다. '
        '절대적인 정답보다 현재 최선의 선택을 실행하고 검증하며 수정하는 방식으로, '
        '팀과 함께 더 나은 시스템을 만들어가겠습니다.',
        s_body))

    doc.build(story)
    print(f'PDF 생성 완료: {out}')

build()
