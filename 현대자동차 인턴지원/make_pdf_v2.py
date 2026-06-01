# -*- coding: utf-8 -*-
import os, sys, json

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

here = os.path.dirname(os.path.abspath(__file__))
candidates = [
    os.path.join(here, "malgun.ttf"),
    os.path.join(here, "NanumGothic.ttf"),
    os.path.join(here, "gulim.ttc"),
]
font_path = next((p for p in candidates if os.path.exists(p)), None)
if font_path is None:
    sys.exit("ERROR: 폰트 파일 없음")

pdfmetrics.registerFont(TTFont("KO", font_path))
KO = "KO"

NAVY      = colors.HexColor("#1F3864")
DARK_GRAY = colors.HexColor("#2D2D2D")
LINE_GRAY = colors.HexColor("#BBBBBB")

def S(name, **kw):
    base = dict(fontName=KO, textColor=DARK_GRAY, wordWrap="CJK")
    base.update(kw)
    return ParagraphStyle(name, **base)

s_name = S("name", fontSize=21, textColor=NAVY,  leading=27, spaceAfter=3,  alignment=TA_LEFT)
s_sub  = S("sub",  fontSize=10,                   leading=15, spaceAfter=2,  alignment=TA_LEFT)
s_link = S("link", fontSize=9.5, textColor=NAVY,  leading=14, spaceAfter=0,  alignment=TA_LEFT)
s_tech = S("tech", fontSize=9,   textColor=NAVY,  leading=14, spaceAfter=0,  alignment=TA_LEFT)
s_open = S("open", fontSize=10.5,                 leading=18, spaceAfter=0,  alignment=TA_JUSTIFY)
s_body = S("body", fontSize=10,                   leading=17, spaceAfter=0,  alignment=TA_JUSTIFY)

def hr_thick(): return HRFlowable(width="100%", thickness=2,   color=NAVY,      spaceAfter=7)
def hr_thin():  return HRFlowable(width="100%", thickness=0.5, color=LINE_GRAY, spaceAfter=10)
def sp(n=8):    return Spacer(1, n)

content_path = os.path.join(here, "content_v3.json")
with open(content_path, encoding="utf-8") as f:
    C = json.load(f)

out = os.path.join(here, "자소서_권지성_현대자동차_v3.pdf")
doc = SimpleDocTemplate(out, pagesize=A4,
    leftMargin=2.5*cm, rightMargin=2.5*cm,
    topMargin=2.3*cm,  bottomMargin=2.3*cm)

story = []
story.append(Paragraph(C["name"], s_name))
story.append(Paragraph(C["sub"], s_sub))
story.append(Paragraph(C["link"], s_link))
story.append(sp(10))
story.append(hr_thick())
story.append(sp(3))
story.append(Paragraph(C["tech"], s_tech))
story.append(sp(8))
story.append(hr_thin())
story.append(Paragraph(C["opening"], s_open))
story.append(sp(11))
story.append(Paragraph(C["body1"], s_body))
story.append(sp(11))
story.append(Paragraph(C["body2"], s_body))
story.append(sp(11))
story.append(Paragraph(C["body3"], s_body))
story.append(sp(11))
story.append(hr_thin())
story.append(Paragraph(C["closing"], s_body))

doc.build(story)
print(f"완료: {out}")
