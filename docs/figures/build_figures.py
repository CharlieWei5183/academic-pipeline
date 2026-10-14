#!/usr/bin/env python3
"""README 圖檔產生器：輸出 docs/figures/ 底下的六張 SVG（三張圖 × 亮／暗主題）。

    python3 docs/figures/build_figures.py

只用標準函式庫。改流程時改下方「資料」區塊再重跑；README 以 <picture> 依 GitHub 主題切換亮／暗版。
文字寬度用字元類別估算（CJK 1em、等寬 0.6em、其餘查表），版面若超出畫布會直接報錯，不會默默溢出。
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
W = 960

SANS = ("-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans TC','Noto Sans CJK TC',"
        "'PingFang TC','Microsoft JhengHei',Helvetica,Arial,sans-serif")
MONO = ("ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',"
        "'Noto Sans Mono CJK TC',monospace")

THEMES = {
    "light": dict(
        text="#1f2328", muted="#59636e", faint="#818b98", line="#8c959f",
        band="#f6f8fa", band_stroke="#e1e4e8", chip="#ffffff", chip_stroke="#d0d7de",
        human_fill="#fff1e5", human_stroke="#e16f24", human_text="#762c00", human_sub="#9a4a16",
        badge="#e16f24", badge_text="#ffffff",
        mech_fill="#e6f6f3", mech_stroke="#1a7f72", mech_text="#0b4b42", mech_sub="#2f6d64",
        accent="#0969da", accent_text="#ffffff", opt_stroke="#8c959f",
        agent_fill="#f3effd", agent_stroke="#8250df", agent_text="#4c2889",
    ),
    "dark": dict(
        text="#e6edf3", muted="#9198a1", faint="#768390", line="#6e7681",
        band="#151b23", band_stroke="#2a313c", chip="#0d1117", chip_stroke="#3d444d",
        human_fill="#2b1708", human_stroke="#f0883e", human_text="#ffc799", human_sub="#f0a868",
        badge="#f0883e", badge_text="#0d1117",
        mech_fill="#0b2622", mech_stroke="#3dbfa8", mech_text="#a6eadc", mech_sub="#7fcfbf",
        accent="#4493f8", accent_text="#0d1117", opt_stroke="#6e7681",
        agent_fill="#1f1733", agent_stroke="#a371f7", agent_text="#d2bdff",
    ),
}

# ---------------------------------------------------------------- 文字寬度估算

_NARROW = set("il.,:;|!'`")
_SEMI = set("fjrt()[]{}-/\\\" ")
_WIDE = set("mwMW@%")


def tw(s: str, size: float, mono: bool = False, bold: bool = False) -> float:
    w = 0.0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F") or ch in "→⇄★":
            w += 1.0
        elif mono:
            w += 0.6
        elif ch in _NARROW:
            w += 0.28
        elif ch in _SEMI:
            w += 0.36
        elif ch in _WIDE:
            w += 0.86
        elif ch.isupper() or ch.isdigit():
            w += 0.62
        elif ch in "·×–":
            w += 0.6
        else:
            w += 0.55
    return w * size * (1.06 if bold else 1.0) * 1.05


# ---------------------------------------------------------------- SVG 基本元件

class Svg:
    def __init__(self, w: int, theme: str, title: str, desc: str):
        self.w, self.h = w, 0
        self.name = theme
        self.t = THEMES[theme]
        self.title, self.desc = title, desc
        self.body: list[str] = []

    def add(self, s: str) -> None:
        self.body.append(s)

    def rect(self, x, y, w, h, fill, stroke=None, sw=1.0, r=8, dash=None):
        a = f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{sw}"'
        if dash:
            a += f' stroke-dasharray="{dash}"'
        self.add(a + "/>")

    def text(self, x, y, s, size, color, weight=400, mono=False, anchor="start"):
        cls = "m" if mono else "s"
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

    def spans(self, x, y, parts, size, anchor="start"):
        """parts: [(文字, 顏色, 字重)]，同一行接續排，間距由瀏覽器排版決定。"""
        inner = "".join(f'<tspan fill="{c}" font-weight="{w}">{escape(s)}</tspan>' for s, c, w in parts)
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="s" font-size="{size}" text-anchor="{anchor}">{inner}</text>')

    def circle(self, cx, cy, r, fill, stroke=None, sw=1.5):
        a = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}"'
        if stroke:
            a += f' stroke="{stroke}" stroke-width="{sw}"'
        self.add(a + "/>")

    def path(self, d, color, sw=1.5, arrow=None, dash=None):
        a = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"'
        if dash:
            a += f' stroke-dasharray="{dash}"'
        if arrow:
            a += f' marker-end="url(#{arrow})"'
        self.add(a + "/>")

    def render(self) -> str:
        t = self.t
        defs = []
        for mid, col in (("a-line", t["line"]), ("a-human", t["human_stroke"]), ("a-accent", t["accent"])):
            defs.append(f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" '
                        f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0.8 L9,5 L0,9.2 z" fill="{col}"/></marker>')
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
                f'height="{self.h}" role="img" aria-labelledby="title desc">\n'
                f'<title id="title">{escape(self.title)}</title>\n<desc id="desc">{escape(self.desc)}</desc>\n'
                f'<style>.s{{font-family:{SANS}}}.m{{font-family:{MONO}}}</style>\n'
                f'<defs>{"".join(defs)}</defs>\n')
        return head + "\n".join(self.body) + "\n</svg>\n"


def rounded(points, r=8) -> str:
    """正交折線（點列）轉圓角 path d。"""
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        l1 = abs(x1 - x0) + abs(y1 - y0)
        l2 = abs(x2 - x1) + abs(y2 - y1)
        rr = min(r, l1 / 2, l2 / 2)
        ax = x1 - rr * ((x1 > x0) - (x1 < x0))
        ay = y1 - rr * ((y1 > y0) - (y1 < y0))
        bx = x1 + rr * ((x2 > x1) - (x2 < x1))
        by = y1 + rr * ((y2 > y1) - (y2 < y1))
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    d += f" L{points[-1][0]:.1f},{points[-1][1]:.1f}"
    return d


# ---------------------------------------------------------------- 站點（chip）

CH = 48            # chip 高度
PAD = 10           # chip 左右內距
NAME = 12.5        # skill 名（等寬）
SUB = 11           # 副標
GLAB = 13          # 人工關卡標題
BADGE = 38         # 人工關卡左側號碼區寬


@dataclass
class Chip:
    kind: str                  # skill | opt | human | mech | end
    name: str
    sub: str = ""
    n: int = 0                 # 人工關卡編號
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = CH
    id: str = ""

    def measure(self) -> "Chip":
        if self.kind in ("skill", "opt"):
            self.w = max(tw(self.name, NAME, mono=True, bold=True), tw(self.sub, SUB)) + 2 * PAD
        elif self.kind == "human":
            self.w = BADGE + max(tw(self.name, GLAB, bold=True), tw(self.sub, SUB)) + PAD
        elif self.kind == "mech":
            self.w = 32 + max(tw(self.name, NAME, mono=True, bold=True), tw(self.sub, SUB)) + PAD
        elif self.kind == "end":
            self.w = tw(self.name, 13, bold=True) + 34
            self.h = 34
        return self

    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def r(self): return self.x + self.w
    @property
    def b(self): return self.y + self.h


def S(name, sub="", id=""): return Chip("skill", name, sub, id=id or name).measure()
def O(name, sub="", id=""): return Chip("opt", name, sub, id=id or name).measure()
def H(n, name, sub=""): return Chip("human", name, sub, n=n, id=f"H{n}").measure()
def M(name, sub="", id=""): return Chip("mech", name, sub, id=id or name).measure()
def E(name, id="end"): return Chip("end", name, id=id).measure()


def draw_chip(g: Svg, c: Chip) -> None:
    t = g.t
    if c.kind == "skill":
        g.rect(c.x, c.y, c.w, c.h, t["chip"], t["chip_stroke"], 1.2, 9)
        g.text(c.x + PAD, c.y + 20, c.name, NAME, t["text"], 600, mono=True)
        g.text(c.x + PAD, c.y + 37, c.sub, SUB, t["muted"])
    elif c.kind == "opt":
        g.rect(c.x, c.y, c.w, c.h, t["chip"], t["opt_stroke"], 1.2, 9, dash="5 4")
        g.text(c.x + PAD, c.y + 20, c.name, NAME, t["muted"], 600, mono=True)
        g.text(c.x + PAD, c.y + 37, c.sub, SUB, t["faint"])
    elif c.kind == "human":
        g.rect(c.x, c.y, c.w, c.h, t["human_fill"], t["human_stroke"], 2.0, 9)
        g.circle(c.x + 19, c.cy, 11, t["badge"])
        g.text(c.x + 19, c.cy + 4.3, str(c.n), 12 if c.n < 10 else 10.5, t["badge_text"], 700, anchor="middle")
        g.text(c.x + BADGE, c.y + 20, c.name, GLAB, t["human_text"], 700)
        g.text(c.x + BADGE, c.y + 37, c.sub, SUB, t["human_sub"])
    elif c.kind == "mech":
        g.rect(c.x, c.y, c.w, c.h, t["mech_fill"], t["mech_stroke"], 1.6, 9)
        ix, iy = c.x + 11, c.cy - 7
        g.rect(ix, iy, 14, 14, t["mech_stroke"], r=3)
        g.path(f"M{ix+3.5:.1f},{iy+7.2:.1f} L{ix+6.2:.1f},{iy+10:.1f} L{ix+10.8:.1f},{iy+4.2:.1f}", t["mech_fill"], 1.8)
        g.text(c.x + 32, c.y + 20, c.name, NAME, t["mech_text"], 600, mono=True)
        g.text(c.x + 32, c.y + 37, c.sub, SUB, t["mech_sub"])
    elif c.kind == "end":
        g.rect(c.x, c.y, c.w, c.h, t["accent"], r=17)
        g.text(c.cx, c.cy + 4.6, c.name, 13, t["accent_text"], 700, anchor="middle")


def arrow_h(g: Svg, a: Chip, b: Chip, color=None, label=None, dy=0.0, label_below=False):
    t = g.t
    y = a.cy + dy
    g.path(f"M{a.r + 2:.1f},{y:.1f} L{b.x - 3:.1f},{y:.1f}", color or t["line"], 1.5, "a-line")
    if label:
        ly = y + 14 if label_below else y - 6
        g.text((a.r + b.x) / 2, ly, label, 10.5, t["muted"], anchor="middle")


# ---------------------------------------------------------------- 圖一：總覽（hero）

PHASES = [
    ("立案與設計", ["route · protocol", "版本化分析計畫"], [(1, "route 確認"), (2, "計畫封存")]),
    ("資料與證據", ["資料稽核 · 分析重跑", "結果驗證 · 證據綜整"], [(3, "資料處置"), (4, "結果契合")]),
    ("判讀與主張", ["目標覆蓋裁決", "claims 反方審查"], [(5, "claims 確認")]),
    ("撰稿", ["出版級圖表", "繁中稿 · SI"], [(6, "圖表驗收"), (7, "中文成稿")]),
    ("審查與中文定稿", ["虛擬同儕審查", "修訂 · 中文潤稿"], [(8, "★ 中文定稿")]),
    ("英文化", ["翻譯 · 英文潤稿", "全量一致性 gate"], [(9, "★ 英文確認")]),
    ("投稿", ["投稿包 · 完整性", "docx／LaTeX 排版"], [(10, "投稿包補件"), (11, "排版收尾")]),
]


def fig_overview(theme: str) -> Svg:
    g = Svg(W, theme, "academic-pipeline 全流程總覽",
            "七個階段從研究問題走到投稿，上方橙色標記為 11 個人工確認關卡，不確認不往下走。")
    t = g.t
    line_y = 150
    x_start, x_end = 46, W - 30
    xs = [128 + i * ((W - 128 - 96) / 6) for i in range(7)]
    # 主線
    g.path(f"M{x_start:.1f},{line_y} L{x_end - 4:.1f},{line_y}", t["line"], 2.4, "a-line")
    g.circle(x_start, line_y, 6, t["chip"], t["line"], 2.2)
    g.text(x_start - 8, line_y - 14, "研究問題", 12, t["muted"], 600)
    g.text(x_end, line_y - 14, "投稿", 12, t["muted"], 600, anchor="end")
    for i, (name, subs, gates) in enumerate(PHASES):
        x = xs[i]
        # 人工關卡旗標（由下往上疊）
        for k, (n, lab) in enumerate(gates):
            pw = BADGE - 8 + tw(lab, 12.5, bold=True) + 12
            py = line_y - 62 - (len(gates) - 1 - k) * 40
            if k == len(gates) - 1:
                g.path(f"M{x:.1f},{line_y - 20:.1f} L{x:.1f},{py + 30:.1f}", t["human_stroke"], 1.6)
            g.rect(x - pw / 2, py, pw, 30, t["human_fill"], t["human_stroke"], 1.8, 15)
            g.circle(x - pw / 2 + 15, py + 15, 10, t["badge"])
            g.text(x - pw / 2 + 15, py + 19.2, str(n), 11.5 if n < 10 else 10, t["badge_text"], 700, anchor="middle")
            g.text(x - pw / 2 + 31, py + 19.6, lab, 12.5, t["human_text"], 700)
        # 階段節點
        g.circle(x, line_y, 17, t["accent"])
        g.text(x, line_y + 5.2, str(i + 1), 15, t["accent_text"], 700, anchor="middle")
        g.text(x, line_y + 42, name, 14, t["text"], 700, anchor="middle")
        for j, s in enumerate(subs):
            g.text(x, line_y + 62 + j * 17, s, 11.5, t["muted"], anchor="middle")
        if i < 6:
            limit = (xs[i + 1] - xs[i]) - 8
            assert max(tw(s, 11.5) for s in subs) < limit and tw(name, 14, bold=True) < limit, name
    # 圖例
    ly = line_y + 116
    g.circle(46, ly - 4, 8, t["badge"])
    g.text(46, ly - 0.4, "n", 10.5, t["badge_text"], 700, anchor="middle")
    g.spans(60, ly, [("人工確認關卡：共 11 個，不確認就不往下走。", t["text"], 700),
                     ("每個階段另有獨立審查 agent 與確定性腳本 gate，細節見 Pipeline 流程圖。", t["muted"], 400)], 12)
    g.h = ly + 20
    return g


# ---------------------------------------------------------------- 圖二：系統架構

AGENT_PAIRS = [
    ("research-designer", "reviewer-methods"),
    ("data-analyst", "statistical-validator"),
    ("literature-scout", "evidence-auditor"),
    ("interpreter", "claim-critic"),
    ("translator", "reviewer-language"),
]
AGENT_OTHERS = ("methodology-router · data-auditor · integrity-officer · evaluator · "
                "reviewer ×3–4 · editor · fact-checker · figure-designer")
SCRIPTS = ["check_route.py", "seal_artifact.py", "check_plan.py", "check_data_audit.py",
           "check_results_schema.py", "rerun_all.py", "check_validation.py", "check_evidence.py",
           "check_claims.py", "check_claim_audit.py", "check_integrity.py", "check_gate.py"]
ARTIFACTS = ["project.yaml", "methodology/route.yaml", "protocol/study-protocol.yaml", "analysis/plans/",
             "analysis/data-audit.yaml", "analysis/results.json", "analysis/validation.yaml",
             "literature/evidence-synthesis.yaml", "analysis/claims.yaml", "analysis/claim-audit.yaml",
             "integrity/register.yaml", "reviews/issue-ledger.yaml", "decisions.yaml"]
PROGRESS_ITEMS = [
    ("status", "隨時呼叫：掃描 artifacts、重算 fingerprint，指出第一個未過或已過期的 gate"),
    ("SessionEnd hook", "session 結束自動重算進度頁面與決策時間軸"),
    ("progress/PROGRESS.html", "里程 · 關聯 · 文獻 · 投稿檔案四個分頁，離線可開"),
    ("收件匣", "頁面上的提問與拖放只進收件匣，下次 session 由你逐筆裁決"),
    ("debug-pipeline", "執行、重跑或 checker 失敗且根因未知時才觸發"),
]


def wrap(s: str, size: float, width: float, mono=False) -> list[str]:
    lines, cur = [], ""
    for tok in _tokens(s):
        if cur and tw(cur + tok, size, mono) > width:
            lines.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur += tok
    if cur:
        lines.append(cur.rstrip())
    return lines


def _tokens(s: str):
    buf = ""
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            if buf:
                yield buf
                buf = ""
            yield ch
        elif ch == " ":
            yield buf + " "
            buf = ""
        else:
            buf += ch
    if buf:
        yield buf


def flow_chips(g: Svg | None, items, x0, y0, width, size, fill=None, stroke=None, color=None,
               mono=True, h=24, gap=6):
    """逐顆排 chip、超寬換行；g 為 None 時只量高度不畫。回傳最後一列底部 y。"""
    x, y = x0, y0
    for s in items:
        w = tw(s, size, mono) + 16
        if x + w > x0 + width:
            x, y = x0, y + h + gap
        if g is not None:
            g.rect(x, y, w, h, fill, stroke, 1, 6)
            g.text(x + 8, y + h / 2 + size * 0.36, s, size, color, 500, mono=mono)
        x += w + gap
    return y + h


def box_title(g: Svg, x, y, title, sub, color):
    g.text(x, y, title, 15, color, 700)
    if sub:
        g.text(x, y + 20, sub, 12, g.t["muted"])


def fig_architecture(theme: str) -> Svg:
    g = Svg(W, theme, "academic-pipeline 系統架構",
            "研究者在最上層做確認與取捨；skills 依序執行流程站，委派 agents 判斷、執行確定性腳本 gate；"
            "所有狀態寫入 SSOT artifacts；右側進度層唯讀 artifacts，回報下一步與待裁決事項。")
    t = g.t
    L0, L1 = 24, 680          # 左欄
    R0, R1 = 704, W - 24      # 右欄
    # A：你
    ay, ah = 20, 70
    g.rect(L0, ay, L1 - L0, ah, t["human_fill"], t["human_stroke"], 2, 12)
    g.circle(L0 + 34, ay + ah / 2 - 7, 8, t["human_stroke"])
    g.path(f"M{L0 + 20:.1f},{ay + ah / 2 + 17:.1f} Q{L0 + 34:.1f},{ay + ah / 2 - 4:.1f} {L0 + 48:.1f},{ay + ah / 2 + 17:.1f}",
           t["human_stroke"], 3.2)
    g.text(L0 + 64, ay + 30, "你（研究者）", 16, t["human_text"], 700)
    g.text(L0 + 64, ay + 52, "11 個人工確認關卡 · 方向性取捨一律寫入 decisions.yaml（D#）", 12.5, t["human_sub"])
    # B：skills
    by, bh = 136, 100
    g.rect(L0, by, L1 - L0, bh, t["band"], t["band_stroke"], 1.2, 12)
    box_title(g, L0 + 18, by + 26, "Skills · 26 個流程站", "依七個階段串成主流程；每一站做同一件事：", t["text"])
    steps = ["讀 artifacts", "委派 agent", "跑腳本 gate", "呈你確認", "寫回 artifacts"]
    sx = L0 + 18
    for i, s in enumerate(steps):
        human = s == "呈你確認"
        w = tw(s, 12.5, bold=True) + 22
        g.rect(sx, by + 58, w, 28, t["human_fill"] if human else t["chip"],
               t["human_stroke"] if human else t["chip_stroke"], 1.6 if human else 1.1, 14)
        g.text(sx + w / 2, by + 76.5, s, 12.5, t["human_text"] if human else t["text"], 600, anchor="middle")
        if i < len(steps) - 1:
            g.path(f"M{sx + w + 4:.1f},{by + 72} L{sx + w + 22:.1f},{by + 72}", t["line"], 1.4, "a-line")
        sx += w + 26
    assert sx < L1, "skills 步驟列超寬"
    # A ⇄ B
    for xo, up, lab in ((L0 + 200, False, "呈確認、待裁決"), (L0 + 420, True, "確認 · 推翻 · 取捨")):
        y1, y2 = (ay + ah + 3, by - 4) if not up else (by - 3, ay + ah + 4)
        g.path(f"M{xo},{y1} L{xo},{y2}", t["human_stroke"], 1.6, "a-human")
        g.text(xo + 10, (ay + ah + by) / 2 + 4, lab, 11.5, t["human_sub"], 600)
    # C1：agents、C2：scripts
    cy, chh = 286, 274
    cw = 344                              # agents 框較寬，scripts 框取剩餘
    cw2 = L1 - L0 - 16 - cw
    c1x, c2x = L0, L0 + cw + 16
    g.rect(c1x, cy, cw, chh, t["agent_fill"], t["agent_stroke"], 1.4, 12)
    box_title(g, c1x + 16, cy + 26, "Agents · 18 個角色", "判斷交給 agent；起草者不審自己的產出", t["agent_text"])
    py = cy + 84
    hx = c1x + 16 + tw("research-designer", 11.5, mono=True) + 36
    g.text(c1x + 16, py - 20, "起草／執行", 11, t["muted"], 600)
    g.text(hx, py - 20, "獨立審查", 11, t["agent_text"], 600)
    for a, b in AGENT_PAIRS:
        g.text(c1x + 16, py, a, 11.5, t["text"], 600, mono=True)
        ax = c1x + 16 + tw("research-designer", 11.5, mono=True) + 8
        g.path(f"M{ax:.1f},{py - 4} L{ax + 20:.1f},{py - 4}", t["agent_stroke"], 1.4, "a-line")
        g.text(ax + 28, py, b, 11.5, t["agent_text"], 700, mono=True)
        assert ax + 28 + tw(b, 11.5, mono=True) < c1x + cw - 8, b
        py += 22
    py += 12
    for ln in wrap("其餘：" + AGENT_OTHERS, 11, cw - 32):
        g.text(c1x + 16, py, ln, 11, t["muted"])
        py += 16
    assert py < cy + chh, "agents 框超高"
    g.rect(c2x, cy, cw2, chh, t["mech_fill"], t["mech_stroke"], 1.4, 12)
    box_title(g, c2x + 16, cy + 26, "確定性腳本 gate", "能機械判定的一律交給腳本", t["mech_text"])
    bottom = flow_chips(g, SCRIPTS, c2x + 16, cy + 60, cw2 - 32, 11, t["chip"], t["mech_stroke"], t["mech_text"])
    assert bottom < cy + chh - 6, "scripts 框超高"
    # B → C
    for xo, lab in ((c1x + cw / 2, "委派：只給材料，不給辯解"), (c2x + cw2 / 2, "執行 gate、讀 exit code")):
        g.path(f"M{xo:.1f},{by + bh + 3} L{xo:.1f},{cy - 4}", t["line"], 1.5, "a-line")
        g.text(xo + 9, (by + bh + cy) / 2 + 4, lab, 11.5, t["muted"])
    # D：artifacts
    dy = cy + chh + 50
    d_items_top = dy + 58
    d_args = (ARTIFACTS, L0 + 18, d_items_top, L1 - L0 - 36, 11.5)
    dh = flow_chips(None, *d_args, h=25) - dy + 18
    g.rect(L0, dy, L1 - L0, dh, t["band"], t["accent"], 1.6, 12)
    flow_chips(g, *d_args, t["chip"], t["chip_stroke"], t["text"], h=25)
    box_title(g, L0 + 18, dy + 26, "SSOT artifacts · 狀態真相",
              "project.yaml 的 state 只是快取；承重來源一變，下游 pass 全部失效", t["accent"])
    for xo, lab in ((c1x + cw / 2, "起草 · 稽核報告"), (c2x + cw2 / 2, "驗證 · 封存 · fingerprint")):
        g.path(f"M{xo:.1f},{cy + chh + 3} L{xo:.1f},{dy - 4}", t["line"], 1.5, "a-line")
        g.text(xo + 9, cy + chh + 30, lab, 11.5, t["muted"])
    # E：進度層（右欄）
    ey = by
    eh = dy + dh - ey
    g.rect(R0, ey, R1 - R0, eh, t["band"], t["band_stroke"], 1.2, 12, dash="6 4")
    box_title(g, R0 + 16, ey + 26, "進度層 · 流程線外", "唯讀 artifacts，不改任何 SSOT", t["text"])
    iy = ey + 62
    for name, desc in PROGRESS_ITEMS:
        lines = wrap(desc, 11, R1 - R0 - 32 - 12)
        ih = 26 + 15 * len(lines)
        g.rect(R0 + 12, iy, R1 - R0 - 24, ih, t["chip"], t["chip_stroke"], 1, 8)
        g.text(R0 + 22, iy + 18, name, 12, t["text"], 600, mono=name.isascii())
        for k, ln in enumerate(lines):
            g.text(R0 + 22, iy + 35 + 15 * k, ln, 11, t["muted"])
        iy += ih + 8
    assert iy < ey + eh, "進度層超高"
    # D → E、E → A
    g.path(f"M{L1 + 3},{dy + dh / 2:.1f} L{R0 - 4},{dy + dh / 2:.1f}", t["line"], 1.5, "a-line")
    g.path(rounded([((R0 + R1) / 2, ey - 3), ((R0 + R1) / 2, ay + ah / 2), (L1 + 4, ay + ah / 2)]),
           t["human_stroke"], 1.6, "a-human")
    g.text((L1 + (R0 + R1) / 2) / 2, ay + ah / 2 - 8, "下一步 · 待裁決", 11.5, t["human_sub"], 600, anchor="middle")
    g.h = int(dy + dh + 24)
    return g


# ---------------------------------------------------------------- 圖三：Pipeline 流程

X0 = 156                    # 站點起始 x
SPINE = X0 - 14             # 換行連接線 x
TRACK_GAP = 22              # 站點間距
LINE_GAP = 24               # 同一階段內兩行的垂直間距
BAND_PAD = 14
BAND_GAP = 18
XMAX = W - 24


@dataclass
class Line:
    chips: list
    gaps: list = field(default_factory=list)   # 自訂站點間距（None＝預設）


def layout_line(chips, y, gaps=None):
    x = X0
    for i, c in enumerate(chips):
        c.x, c.y = x, y + (CH - c.h) / 2
        gap = (gaps[i] if gaps and i < len(gaps) and gaps[i] else TRACK_GAP)
        x = c.r + gap
    assert chips[-1].r <= XMAX, f"line overflow: {[c.id for c in chips]} → {chips[-1].r:.0f} > {XMAX}"


def fig_flow(theme: str) -> Svg:
    g = Svg(W, theme, "academic-pipeline Pipeline 流程",
            "七個階段的站點順序。橙色為人工確認關卡（編號對應 README 表格），青色為確定性腳本 gate，"
            "虛線為內建選用站；分析線與文獻線並行後匯入判讀階段；peer-review 與 revise 循環至收斂。")
    t = g.t

    # ---- 站點
    c = {}
    def reg(*chips):
        for ch in chips:
            c[ch.id] = ch
        return list(chips)

    p1a = reg(S("project-init", "建立專案 · 拆解 goals"), S("methodology-router", "選定方法 adapter"),
              H(1, "route 確認", "推翻建議記 D#"))
    p1b = reg(S("integrity-check", "prestudy 倫理 · 資料治理", id="integrity-pre"),
              S("study-design", "protocol ＋ plans ＋ 設計審"), H(2, "計畫封存", "逐項確認後 seal"))
    p2a = reg(S("data-audit", "缺失 · 重複 · 洩漏"), H(3, "資料處置", "剔除／插補記 D#"))
    p2b = reg(S("analyze-data", "執行 sealed plan"), M("rerun_all.py", "clean-room 重跑"),
              S("code-review", "reviewer-methods"), S("validate-results", "穩健性 · 獨立重算"),
              H(4, "結果契合", "確認後 SQ 才結案"))
    p2c = reg(S("lit-review", "literature-scout"), S("evidence-synthesis", "風險偏誤 · 引用 entailment"))
    p3 = reg(S("evaluate", "full · 目標覆蓋裁決"), S("interpret-results", "interpreter 草擬 claims"),
             S("claim-audit", "claim-critic 反方審查"), H(5, "claims 確認", "confirmed: true"))
    p4a = reg(S("figure-design", "figure story · 出版級圖表"), H(6, "圖表驗收", "色盲 · 解析度 · 位數"),
              S("write-manuscript", "繁體中文稿"), H(7, "中文成稿", "全稿內容與數字"))
    p4b = reg(S("write-supplementary", "SI 收尾"), M("check-consistency", "zh · check_gate.py", id="cc-zh"))
    p5a = reg(S("peer-review", "persona 席 ＋ editor"), S("revise", "issue-ledger 逐點結案"),
              S("journal-match", "選刊 · cascade 改投"))
    p5b = reg(O("chinese-academic-editing", "中文潤稿 · 內建選用"), H(8, "★ 中文定稿", "state.zh_final"))
    p6 = reg(S("translate-en", "翻譯 ＋ 語言審查"), O("academic-english-editing", "英文潤稿 · 內建選用"),
             H(9, "★ 英文確認", "語意與術語"), M("check-consistency", "en · 全量重跑", id="cc-en"))
    p7a = reg(S("submission-prep", "cover letter · 重現性打包"), H(10, "投稿包補件", "【請人工補】逐項"),
              S("integrity-check", "presubmission", id="integrity-sub"), M("check_gate.py", "最終 gate", id="final"))
    p7b = reg(S("typeset", "docx／LaTeX · 雙匿名 · 行號"), H(11, "排版收尾", "產物與自引清單"), E("投稿"))
    offline = reg(S("status", "隨時：指出第一個未過的 gate", id="status"),
                  S("debug-pipeline", "失敗且根因未知時", id="debug"))

    bands = [
        ("01", "立案與設計", [Line(p1a), Line(p1b)]),
        ("02", "資料與證據", [Line(p2a), Line(p2b), Line(p2c)]),
        ("03", "判讀與主張", [Line(p3)]),
        ("04", "撰稿", [Line(p4a), Line(p4b)]),
        ("05", "審查與中文定稿", [Line(p5a, gaps=[74, 92]), Line(p5b)]),
        ("06", "英文化", [Line(p6)]),
        ("07", "投稿", [Line(p7a), Line(p7b)]),
    ]

    # ---- 圖例
    lx, ly = 24, 14
    legend = [("human", "人工確認關卡（編號同下表）"), ("mech", "確定性腳本 gate"),
              ("skill", "skill 流程站"), ("opt", "內建選用站")]
    for kind, lab in legend:
        if kind == "human":
            g.rect(lx, ly, 26, 20, t["human_fill"], t["human_stroke"], 1.8, 6)
            g.circle(lx + 13, ly + 10, 6.5, t["badge"])
        elif kind == "mech":
            g.rect(lx, ly, 26, 20, t["mech_fill"], t["mech_stroke"], 1.5, 6)
        elif kind == "skill":
            g.rect(lx, ly, 26, 20, t["chip"], t["chip_stroke"], 1.2, 6)
        else:
            g.rect(lx, ly, 26, 20, t["chip"], t["opt_stroke"], 1.2, 6, dash="4 3")
        g.text(lx + 34, ly + 14.5, lab, 12, t["text"], 600 if kind == "human" else 400)
        lx += 34 + tw(lab, 12) + 26

    # ---- 版面
    y = 54
    band_rects = []
    for num, name, lines in bands:
        top = y
        y += BAND_PAD + (14 if num == "05" else 0)   # 05 上方留給改投回程線
        for li, ln in enumerate(lines):
            layout_line(ln.chips, y, ln.gaps)
            y += CH
            if li < len(lines) - 1:
                y += LINE_GAP
        y += BAND_PAD
        band_rects.append((num, name, top, y))
        y += BAND_GAP
    # 流程線外
    off_top = y + 6
    for i, ch in enumerate(offline):
        ch.y = off_top + BAND_PAD
        ch.x = X0 if i == 0 else offline[i - 1].r + 26
    off_bottom = off_top + BAND_PAD * 2 + CH
    g.h = int(off_bottom + 20)

    # 階段底色與標籤
    for num, name, top, bot in band_rects:
        g.rect(24, top, W - 48, bot - top, t["band"], t["band_stroke"], 1, 12)
        g.text(38, top + 30, num, 20, t["accent"], 700, mono=True)
        g.text(38, top + 50, name, 13, t["text"], 700)
    g.rect(24, off_top, W - 48, off_bottom - off_top, "none", t["band_stroke"], 1.2, 12, dash="6 4")
    g.text(38, off_top + 30, "線外", 13, t["muted"], 700)
    g.text(38, off_top + 48, "任何時點", 11, t["faint"])

    line_col = t["line"]

    def seq(chips, skip=()):
        for a, b in zip(chips, chips[1:]):
            if (a.id, b.id) not in skip:
                arrow_h(g, a, b)

    def zconn(a: Chip, b: Chip, gap_y: float, from_bottom=False, label=None):
        if from_bottom:
            pts = [(a.cx, a.b + 2), (a.cx, gap_y), (SPINE, gap_y), (SPINE, b.cy), (b.x - 3, b.cy)]
        else:
            pts = [(a.r + 2, a.cy), (a.r + 12, a.cy), (a.r + 12, gap_y), (SPINE, gap_y), (SPINE, b.cy), (b.x - 3, b.cy)]
        g.path(rounded(pts), line_col, 1.5, "a-line")
        if label:
            g.text(a.cx + 8, (a.b + gap_y) / 2 + 4, label, 10.5, t["muted"])

    def mid(a: Chip, b: Chip):
        return (a.b + b.y) / 2

    # 01
    seq(p1a); seq(p1b)
    zconn(p1a[-1], p1b[0], mid(p1a[0], p1b[0]))
    zconn(p1b[-1], p2a[0], mid(p1b[0], p2a[0]))
    # 02：分析線與文獻線並行
    seq(p2a); seq(p2b); seq(p2c)
    zconn(p2a[-1], p2b[0], mid(p2a[0], p2b[0]))
    g.path(rounded([(SPINE, p2b[0].cy - 10), (SPINE, p2c[0].cy), (p2c[0].x - 3, p2c[0].cy)]), line_col, 1.5, "a-line")
    g.text(p2c[-1].r + 10, p2c[0].cy + 4, "∥ 與分析線並行", 10.5, t["muted"])
    end2 = p2b[-1]
    gap23 = mid(p2c[0], p3[0])
    g.path(rounded([(end2.r + 2, end2.cy), (end2.r + 14, end2.cy), (end2.r + 14, gap23), (SPINE, gap23),
                    (SPINE, p3[0].cy), (p3[0].x - 3, p3[0].cy)]), line_col, 1.5, "a-line")
    lab_w = tw("∥ 與分析線並行", 10.5) + 14
    g.path(rounded([(p2c[-1].r + lab_w + 2, p2c[-1].cy), (end2.r + 14, p2c[-1].cy)]), line_col, 1.5)
    g.circle(end2.r + 14, p2c[-1].cy, 3.2, line_col)
    # 03
    seq(p3)
    zconn(p3[-1], p4a[0], mid(p3[0], p4a[0]))
    # 04
    seq(p4a); seq(p4b)
    zconn(p4a[-1], p4b[0], mid(p4a[0], p4b[0]))
    zconn(p4b[-1], p5a[0], mid(p4b[0], p5a[0]))
    # 05：peer-review ⇄ revise；reject → journal-match → 回 peer-review；accept → 中文潤稿
    pr, rv, jm = p5a
    arrow_h(g, pr, rv, dy=-8, label="major／minor")
    g.path(f"M{rv.x - 2:.1f},{rv.cy + 8:.1f} L{pr.r + 3:.1f},{rv.cy + 8:.1f}", line_col, 1.5, "a-line")
    g.text((pr.r + rv.x) / 2, rv.cy + 23, "未收斂", 10.5, t["muted"], anchor="middle")
    arrow_h(g, rv, jm, label="reject")
    ret_y = pr.y - 9
    g.path(rounded([(jm.cx, jm.y - 2), (jm.cx, ret_y), (pr.cx, ret_y), (pr.cx, pr.y - 3)], 6), line_col, 1.3,
           "a-line", dash="4 3")
    g.text(jm.cx - 8, ret_y - 4, "改投後重審", 10.5, t["muted"], anchor="end")
    zconn(rv, p5b[0], mid(rv, p5b[0]), from_bottom=True, label="accept／覆核通過")
    seq(p5b)
    zconn(p5b[-1], p6[0], mid(p5b[0], p6[0]))
    # 06、07
    seq(p6)
    zconn(p6[-1], p7a[0], mid(p6[0], p7a[0]))
    seq(p7a); seq(p7b)
    zconn(p7a[-1], p7b[0], mid(p7a[0], p7b[0]))

    for ch in c.values():
        draw_chip(g, ch)
    return g


# ---------------------------------------------------------------- 輸出

FIGS = {
    "pipeline-overview": fig_overview,
    "architecture": fig_architecture,
    "pipeline-flow": fig_flow,
}


def main() -> int:
    for stem, fn in FIGS.items():
        for theme in THEMES:
            svg = fn(theme).render()
            path = OUT / f"{stem}-{theme}.svg"
            path.write_text(svg, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(OUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
