"""dev_format.py — Policy HTML to dev/design team friendly export.

Reads ncstudio policy HTML, extracts entities and relationships,
emits 5 artifacts in `output/exports/{slug}/`:
  - 00_INDEX.md      — Claude Code entry point / routing guide
  - usecase_*.md     — per-UC slice with all related entities inline
  - mapping.csv      — flat N:N mapping matrix
  - entities.yaml    — identity + relationships + data dictionary
  - warnings.md      — automated validation report

No LLM calls. Pure HTML→structured transform.

Run as module:
    python -m src.exporters.dev_format --input <html_path> [--output <dir>]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants and patterns
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z0-9]+){1,})\b")

# Map ID prefix to entity bucket (the canonical "primary type" of an ID).
# Both `POL-` and `PI-` are accepted as policy_item prefixes — different policy
# documents use one or the other (e.g. POL-MBR-TERM-001-01 vs PI-AIS-SCP-001).
PREFIX_TO_TYPE: dict[str, str] = {
    "POL": "policy_items",
    "PI":  "policy_items",
    "TM":  "terms",
    "ACT": "actors",
    "US":  "usecases",
    "ST":  "states",
    "PR":  "processes",
    "FN":  "functions",
    "PG":  "policy_groups",
}

# Regex fragment matching either PI- or POL- prefixed IDs in headings/text.
PI_PREFIX_RE = r"(?:PI|POL)-[A-Z0-9-]+"

# 최신 정책서(상품상세/담기 v0.11 이후)의 의미적 CSS class → bucket 매핑.
# 회원가입/탈퇴 등 legacy 정책서는 class 없는 일반 <table>을 사용 → 헤더 fallback으로
# 처리됨 (backward compat). 미래 정책서가 컬럼명을 미묘하게 바꿔도(예: "프로세스 ID"
# → "PR ID") class가 있으면 안전하게 분류된다.
CLASS_TO_BUCKET: dict[str, str] = {
    "meta":                    "meta",
    "usecase-list-table":      "usecases",
    "process-list-table":      "processes",
    "function-list-table":     "functions",
    "policy-list-table":       "policy_list",
    "state-code-table":        "states",
    "state-transition-table":  "transitions",
}

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

@dataclass
class Cell:
    text: str = ""
    is_header: bool = False
    ids: list[str] = field(default_factory=list)
    colspan: int = 1  # L1-rich: detail_tables 변환 시 셀 확장용(추가형)


@dataclass
class Table:
    section_h2: str = ""
    section_h3: str = ""
    section_h4: str = ""            # nearest preceding <h4> — used by per-process function/policy lists
    table_class: str = ""           # CSS class on the <table> tag, used to identify the meta table
    headers: list[str] = field(default_factory=list)
    rows: list[list[Cell]] = field(default_factory=list)


@dataclass
class PolicyDetailItem:
    """Parsed from <div class="policy-item"> blocks."""
    pi_id: str
    pg_id: str
    name: str
    content: str
    # L1-rich: 본문 내부 구조(평면 content 외 구조화 필드 — 추가형, 기존 소비자 무영향)
    rules: list[str] = field(default_factory=list)            # pi-detail-list / policy-item-content <li>
    core_question: dict | None = None                         # {question, answers} (pi-core-question)
    detail_tables: list[dict] = field(default_factory=list)   # policy-detail-subtable


class PolicyHTMLParser(HTMLParser):
    """Walk policy HTML, collect tables with surrounding section context.

    Also collects:
      - policy_detail_items: parsed from <div class="policy-item"> blocks
        (the policy detail section uses divs, not tables).
      - policy_group_h4: list of (PG-id, group title) seen in <h4> headers
        within the policy detail section, used to anchor div items.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self.policy_detail_items: list[PolicyDetailItem] = []
        self.title_h1 = ""
        self._h1 = ""
        self._h2 = ""
        self._h3 = ""
        self._h4 = ""
        self._current_pg_in_detail = ""  # PG-id active in the policy detail section
        self._h4_id = ""  # 가장 최근 h4의 id= 속성(PG 컨텍스트 fallback)
        # active text buffer (h2/h3/h4 title or cell content or div text)
        self._buf: list[str] | None = None
        # support nested tables (e.g., macro tables embedded in cells)
        self._table_stack: list[Table] = []
        self._row: list[Cell] | None = None
        self._cell: Cell | None = None
        self._cell_is_th: bool = False
        # policy-item div parsing
        self._in_policy_item: bool = False
        self._in_policy_item_title: bool = False
        self._in_policy_item_content: bool = False
        self._pi_title_buf: list[str] = []
        self._pi_content_buf: list[str] = []
        # 제목 중첩 깊이: 제목이 <div.policy-item-title><div.policy-item-title>…로
        # 이중 중첩될 때(AI검색 ADM 등) 바깥 제목 </div>를 wrapper 종료로 오인해 content
        # 전에 항목이 조기 확정되는 것을 막는다(RC-B). 제목은 nest가 0으로 돌아올 때만 닫는다.
        # wrapper 종료 판단은 기존대로 '제목/본문이 아닌 첫 </div>'를 유지해 깨진 중첩
        # (한 wrapper 안에 형제 PI가 미종료 div로 끼워진 AI검색 RES-106 등)에서 항목이
        # 통째로 합쳐지지 않게 한다.
        self._pi_title_nest: int = 0
        # 본문 연속 누적기: 중첩 <table> 셀의 <td>/<th>가 _buf를 리셋해도(RC-A) 본문이
        # 사라지지 않도록 _in_policy_item_content 동안 모든 텍스트를 별도로 모은다.
        self._pi_content_acc: list[str] = []
        # pi-detail-title 변형(주문계약가입 등): 제목이 div.policy-item로 감싸지지 않고
        # <p class="pi-detail-title">… 형태로 독립 등장. 본문은 다음 제목/heading 전까지.
        self._pi_detail_active: bool = False
        self._in_pi_detail_title: bool = False
        self._pi_detail_title_tag: str = ""
        self._pi_detail_title_buf: list[str] = []
        self._pi_detail_body_buf: list[str] = []
        self._pi_detail_title_id: str = ""  # 제목 요소 id= 속성(텍스트에 (PI-...) 없을 때 fallback)
        self._seen_pi_ids: set[str] = set()  # 중복 PI 정의 방지(래퍼/단독 동시 등장 등)
        self._item_index: dict[str, int] = {}  # pi_id → policy_detail_items 인덱스(풍부도 교체용)
        # L1-rich: 본문 <li> 규칙 캡처
        self._pi_rules: list[str] = []
        self._in_pi_li: bool = False
        self._pi_li_buf: list[str] = []
        self._pi_family: str = ""        # "pi-detail" | "item" — 규칙 캡처 경계 결정
        self._in_rule_list: bool = False  # <ul class="pi-detail-list"> 내부 여부
        self._detail_block_depth: int = 0  # pi-detail-block div 깊이 — 닫힐 때 항목 확정(경계)
        # L1-rich: 핵심질문(pi-core-question) — 질문 + 답변 bullets
        self._in_core_q_p: bool = False
        self._core_q_pending: bool = False     # 질문 닫힘 후 다음 <ul>이 답변 목록
        self._in_core_q_answers: bool = False
        self._pi_core_question: str = ""
        self._pi_core_answers: list[str] = []
        # L1-rich: policy-detail-subtable
        self._pi_detail_tables: list[dict] = []

    # -- handlers ---------------------------------------------------------

    def _in_body_capture(self) -> bool:
        """PI 본문(content/규칙)을 누적 중인 상태인지."""
        return self._in_policy_item_content or (self._pi_detail_active and not self._in_pi_detail_title)

    def _li_is_rule(self) -> bool:
        """현재 <li>가 규칙(또는 핵심질문 답변)으로 캡처 대상인지.

        pi-detail family는 외곽 표(policy-detail-table)의 PG요약 <td><ul><li>가 직전 PI로
        새지 않도록 pi-detail-list/핵심질문 답변 ul에 한정한다. wrapper/standalone-item
        family는 본문 ul이 곧 규칙이므로 그대로 캡처(검증 완료)."""
        # 충실성은 content-substring backstop(_append_policy_detail)이 보장하므로
        # 여기서는 본문 <li>를 모두 후보로 받는다(타 PI 누수는 backstop이 탈락시킴).
        return True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        cls = (attrs_d.get("class") or "")
        classes = cls.split()
        # 새 PI 앵커(자기 id="pi-..."를 단 policy-item wrapper 또는 policy-item-title/pi-title)
        # 가 진행 중인 wrapper 안에 잘못 중첩되면(AI검색 RES-106처럼 미종료 div로 형제 PI가
        # 끼워진 경우), 현재 wrapper 항목을 먼저 확정해 형제 PI가 통째로 합쳐지지 않게 한다.
        # 이중 중첩 제목(RC-B)의 내부 제목은 id가 없으므로 여기 걸리지 않는다.
        if (tag == "div" and self._in_policy_item
                and (attrs_d.get("id") or "").startswith("pi-")
                and ("policy-item" in classes or "policy-item-title" in classes or "pi-title" in classes)):
            self._finalize_policy_item()
            self._in_policy_item = False
            self._in_policy_item_title = False
            self._in_policy_item_content = False
            self._pi_title_nest = 0
        # 독립(미래핑) 제목 변형 → 본문-경계 머신으로 처리.
        #  - pi-detail-title(주문계약): 항상
        #  - policy-item-title / pi-title: div.policy-item 래퍼 밖일 때만(래퍼 안은 기존 경로)
        # 단, 이미 제목 캡처 중(_in_pi_detail_title)이면 중첩 제목(외곽 id앵커 + 내부 제목,
        # AI검색)이므로 재시작하지 않는다 — 빈 항목이 먼저 등록돼 진짜 항목이 중복 탈락하는 것 방지.
        if not self._in_pi_detail_title and (
            "pi-detail-title" in classes
            or (("policy-item-title" in classes or "pi-title" in classes) and not self._in_policy_item)
        ):
            # 새 항목 시작 — 직전 항목을 닫고 제목 캡처를 연다.
            self._finalize_pi_detail_item()
            self._pi_detail_active = True
            self._in_pi_detail_title = True
            self._pi_detail_title_tag = tag
            self._pi_detail_title_buf = []
            self._pi_detail_body_buf = []
            self._pi_detail_title_id = attrs_d.get("id") or ""
            self._pi_rules = []
            self._in_pi_li = False
            self._pi_family = "pi-detail" if "pi-detail-title" in classes else "item"
            self._in_rule_list = False
            self._buf = []
            return
        if tag in ("h1", "h2", "h3", "h4"):
            # heading 경계 — 진행 중인 항목을 닫고 상태를 정리한다. wrapped 항목이
            # 닫히지 않은 채 다음 섹션으로 상태가 새면 이후 wrapped 항목의 본문 캡처가
            # 깨지므로(AI검색 PG별 detail 표) 여기서 확실히 리셋한다.
            self._finalize_pi_detail_item()
            if self._in_policy_item:
                self._finalize_policy_item()
                self._in_policy_item = False
            self._in_policy_item_title = False
            self._in_policy_item_content = False
            # 깨진/미종료 wrapper가 다음 섹션으로 상태를 흘리지 않도록 확실히 리셋한다.
            self._pi_title_nest = 0
            self._pi_content_acc = []
            if tag == "h4":
                self._h4_id = attrs_d.get("id") or ""
            self._buf = []
        elif tag == "table":
            self._table_stack.append(Table(section_h2=self._h2, section_h3=self._h3,
                                           section_h4=self._h4, table_class=cls))
        elif tag == "tr" and self._table_stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = Cell()
            try:
                self._cell.colspan = max(1, int(attrs_d.get("colspan", 1) or 1))
            except (TypeError, ValueError):
                self._cell.colspan = 1
            self._cell_is_th = (tag == "th")
            self._buf = []
        elif tag == "div":
            if "policy-item" in classes:
                # 래퍼 항목 시작 — 진행 중인 단독 항목이 있으면 먼저 닫는다.
                self._finalize_pi_detail_item()
                self._in_policy_item = True
                self._pi_title_nest = 0
                self._pi_title_buf = []
                self._pi_content_buf = []
                self._pi_content_acc = []
                self._pi_rules = []
                self._in_pi_li = False
                self._pi_family = "item"
                self._in_rule_list = False
            # 제목 div 변형: policy-item-title(AI검색 등) / pi-title(상품상세 v0.30+)
            elif ("policy-item-title" in classes or "pi-title" in classes) and self._in_policy_item:
                # 첫 제목 진입에서만 _buf를 연다. 이중 중첩 제목은 nest만 올려, 바깥
                # </div>가 wrapper 종료로 오인되지 않게 한다(RC-B).
                if self._pi_title_nest == 0:
                    self._in_policy_item_title = True
                    self._buf = []
                self._pi_title_nest += 1
            # 본문 div 변형: policy-item-content / pi-body(상품상세 v0.30+)
            elif ("policy-item-content" in classes or "pi-body" in classes) and self._in_policy_item:
                if self._in_policy_item_title:
                    # 깨진 중첩(AI검색 RES-106): 제목 div가 닫히지 않은 채 본문이 시작되면
                    # 여기서 제목을 확정한다. 그래야 본문의 </div>가 제목 close로 잘못
                    # 소비되지 않고 본문이 정상 캡처·확정된다.
                    self._in_policy_item_title = False
                    self._pi_title_nest = 0
                    self._pi_title_buf = list(self._buf or [])
                self._in_policy_item_content = True
                self._buf = []
                self._pi_content_acc = []
        elif tag == "p" and "pi-core-question" in classes and self._in_body_capture():
            # 핵심질문 문단 — 질문 텍스트를 별도 캡처.
            self._in_core_q_p = True
            self._buf = []
        elif tag == "ul" and self._core_q_pending:
            # 핵심질문 직후 <ul> → 답변 목록.
            self._in_core_q_answers = True
        elif tag == "ul" and "pi-detail-list" in classes:
            self._in_rule_list = True
        elif tag == "li" and self._in_body_capture() and self._li_is_rule():
            # 본문 리스트 항목 — 규칙으로 별도 캡처(content 누적과 병행).
            self._in_pi_li = True
            self._pi_li_buf = []
        elif tag == "br":
            if self._buf is not None:
                self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._in_core_q_p:
            question = self._normalize("".join(self._buf or []))
            question = re.sub(r"^\s*핵심질문\s*[:：]\s*", "", question).strip()
            self._pi_core_question = question
            self._in_core_q_p = False
            self._core_q_pending = True
            self._buf = None
            return
        if tag == "li" and self._in_pi_li:
            text = self._normalize("".join(self._pi_li_buf))
            text = re.sub(r"^[•·\-\*▪]\s*", "", text).strip()
            if text:
                # 핵심질문 답변 목록이면 answers로, 아니면 rules로.
                (self._pi_core_answers if self._in_core_q_answers else self._pi_rules).append(text)
            self._in_pi_li = False
            self._pi_li_buf = []
            return
        if tag == "ul":
            if self._in_core_q_answers:
                self._in_core_q_answers = False
                self._core_q_pending = False
            self._in_rule_list = False
            return
        if self._in_pi_detail_title and tag == self._pi_detail_title_tag:
            # 제목 요소가 닫힘 — 제목 버퍼 확정, 이후 텍스트는 본문으로 누적.
            self._pi_detail_title_buf = list(self._buf or [])
            self._buf = None
            self._in_pi_detail_title = False
            return
        if tag == "h1":
            text = self._flush_text()
            if not self.title_h1:
                self.title_h1 = text
        elif tag == "h2":
            self._h2 = self._flush_text()
            self._h3 = ""  # reset on new section
            self._h4 = ""
            self._current_pg_in_detail = ""
        elif tag == "h3":
            self._h3 = self._flush_text()
            self._h4 = ""
            self._current_pg_in_detail = ""
        elif tag == "h4":
            self._h4 = self._flush_text()
            # If we're in policy detail section, extract the PG-id from the title
            # e.g. "1) 통합 검색 범위 정책 (PG-AIS-SCOPE-001)"
            # h3에 change-badge span 등 후행 텍스트가 붙어도(상품상세 v0.30+) 인식하도록
            # 공백 정규화 후 prefix 비교한다.
            # 열거 글자에 무관하게 "<글자>. 정책 상세" 섹션이면 PG 컨텍스트를 갱신
            # ("나."(AI검색)·"다."(주문계약) 등).
            if re.match(r"[가-힣]\.\s*정책\s*상세", re.sub(r"\s+", " ", self._h3).strip()):
                # PG id: 괄호형 "( PG-... )"(결제) → bare "PG-... 이름"(주문계약) → h4 id= 속성 순.
                m = re.search(r"\(\s*(PG-[A-Z0-9-]+)\s*\)", self._h4) or re.search(r"\b(PG-[A-Z0-9-]+)\b", self._h4)
                pg = m.group(1) if m else ""
                if not pg and self._h4_id:
                    m2 = re.search(r"(PG-[A-Z0-9-]+)", self._h4_id)
                    pg = m2.group(1) if m2 else ""
                if pg:
                    self._current_pg_in_detail = pg
        elif tag in ("td", "th") and self._cell is not None:
            text = self._normalize(self._flush_text())
            self._cell.text = text
            self._cell.is_header = self._cell_is_th
            self._cell.ids = ID_PATTERN.findall(text)
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._finalize_row()
            self._row = None
        elif tag == "table" and self._table_stack:
            t = self._table_stack.pop()
            if "policy-detail-subtable" in (t.table_class or "").split() and (self._pi_detail_active or self._in_policy_item):
                self._pi_detail_tables.append(self._table_to_detail(t))
            if t.rows or t.headers:
                self.tables.append(t)
        elif tag == "div":
            if self._in_policy_item_title:
                # 제목은 중첩이 모두 닫혀 nest가 0이 될 때만 확정한다. 바깥 제목 </div>가
                # 먼저 wrapper 종료로 흘러가지 않게 한다(RC-B). nest>0이면 깊이만 줄인다.
                self._pi_title_nest -= 1
                if self._pi_title_nest <= 0:
                    self._pi_title_nest = 0
                    self._in_policy_item_title = False
                    self._pi_title_buf = list(self._buf or [])
                    self._buf = None
            elif self._in_policy_item_content:
                self._in_policy_item_content = False
                # 연속 누적기를 본문으로 쓴다 — 중첩 표가 _buf를 비워도 본문 보존(RC-A).
                self._pi_content_buf = list(self._pi_content_acc)
                self._pi_content_acc = []
                self._buf = None
            elif self._in_policy_item:
                # closing the policy-item wrapper — finalize an item. 깨진 중첩에서는
                # 제목/본문이 아닌 첫 </div>가 항목 경계로 동작한다(기존 동작 유지).
                self._finalize_policy_item()
                self._in_policy_item = False
                self._pi_title_nest = 0

    def handle_data(self, data: str) -> None:
        if self._in_pi_li:
            self._pi_li_buf.append(data)
        if self._in_policy_item_content:
            # 본문 연속 누적 — _buf와 무관하게 모은다. 중첩 표 셀의 <td>/<th>가 _buf를
            # 리셋해도(RC-A) wrapper 본문이 사라지지 않는다.
            self._pi_content_acc.append(data)
        if self._buf is not None:
            self._buf.append(data)
        elif self._pi_detail_active and not self._in_pi_detail_title:
            # pi-detail 항목 본문 누적(다음 제목/heading 경계 전까지).
            self._pi_detail_body_buf.append(data)

    # -- helpers ----------------------------------------------------------

    def _flush_text(self) -> str:
        text = "".join(self._buf or [])
        self._buf = None
        return text

    @staticmethod
    def _normalize(s: str) -> str:
        # collapse runs of spaces/tabs but preserve newlines
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n\s*\n+", "\n", s)
        return s.strip()

    def _finalize_row(self) -> None:
        if not self._row:
            return
        t = self._table_stack[-1]
        # First all-header row sets the headers; later all-header rows are ignored.
        if not t.headers and all(c.is_header for c in self._row):
            t.headers = [c.text for c in self._row]
        else:
            t.rows.append(self._row)

    def _finalize_policy_item(self) -> None:
        title_text = self._normalize("".join(self._pi_title_buf))
        content_text = self._normalize("".join(self._pi_content_buf))
        # Cosmetic cleanup — HTML 원본의 <li> 또는 "- " 머리표가 그대로 텍스트로
        # 들어와 content 가독성을 해치는 경우를 정리한다.
        #  - leading bullet marker ("- 검색 대상...") → 제거
        #  - 문장 끝 + 다음 bullet ("...다룬다.- 장바구니...") → ". " 결합
        # 한국어 정책서 본문에 ". - "(점·공백·대시) 패턴이 자연 텍스트로 등장할
        # 가능성은 거의 없으므로 안전. real "-" hyphen (예: BSS-001)은 prefix
        # marker가 아니라 ID 일부라 영향 없음.
        content_text = re.sub(r"^[•·\-\*▪]\s*", "", content_text)
        content_text = re.sub(r"(?<=[.!?])\s*[•·\-\*▪]\s+", " ", content_text)
        # title format examples:
        #   "• 검색 대상 범위 (PI-AIS-SCP-001)"
        #   "• 회원 가입 필수 약관 (POL-MBR-TERM-001-01)"
        pi_id, name = self._pi_id_and_name(title_text)
        self._append_policy_detail(pi_id, name, content_text)
        # 확정 후 제목/본문 버퍼를 비운다. wrapper 시작에서도 초기화되지만, 확정 직후
        # 또 다른 finalize가 호출되는 경로가 생기더라도 직전 항목 내용이 재방출되지 않게
        # 방어한다(검수 권고).
        self._pi_title_buf = []
        self._pi_content_buf = []

    def _take_rich(self) -> tuple[list[str], dict | None, list[dict]]:
        """현재 항목의 구조화 본문(rules/core_question/detail_tables)을 꺼내고 초기화."""
        rules = list(self._pi_rules)
        core_question = None
        if self._pi_core_question:
            core_question = {"question": self._pi_core_question, "answers": list(self._pi_core_answers)}
        detail_tables = list(self._pi_detail_tables)
        self._pi_rules = []
        self._in_pi_li = False
        self._pi_core_question = ""
        self._pi_core_answers = []
        self._in_core_q_p = False
        self._core_q_pending = False
        self._in_core_q_answers = False
        self._pi_detail_tables = []
        self._pi_family = ""
        self._in_rule_list = False
        return rules, core_question, detail_tables

    @staticmethod
    def _table_to_detail(t: "Table") -> dict:
        """policy-detail-subtable Table → {caption, note, headers, rows}(colspan 확장)."""
        rows = []
        for row in t.rows:
            cells: list[str] = []
            for c in row:
                cells.extend([c.text] * max(1, getattr(c, "colspan", 1) or 1))
            rows.append(cells)
        return {"caption": "", "note": "", "headers": list(t.headers), "rows": rows}

    def _append_policy_detail(self, pi_id: str, name: str, content: str) -> None:
        """PI 상세 항목을 추가(빈 id·중복 id는 건너뜀)."""
        rules, core_question, detail_tables = self._take_rich()
        # 충실성 backstop: 규칙은 반드시 해당 PI 본문(content)의 부분이어야 한다.
        # content는 표 셀 텍스트가 _buf로 빠져 경계를 넘지 않으므로(누수 없음) 신뢰 기준이다.
        # 타 섹션·인덱스 표에서 새어든 bullet은 content에 없으므로 여기서 탈락 → 날조 0.
        norm_content = re.sub(r"\s+", "", content or "")
        if norm_content:
            rules = [r for r in rules if re.sub(r"\s+", "", r) in norm_content]
        else:
            rules = []
        if not pi_id:
            return
        item = PolicyDetailItem(
            pi_id=pi_id,
            pg_id=self._current_pg_in_detail,
            name=name,
            content=content,
            rules=rules,
            core_question=core_question,
            detail_tables=detail_tables,
        )
        if pi_id in self._seen_pi_ids:
            # 같은 id가 두 번 등장하면(빈 id앵커 placeholder + 실제 정의, 인덱스/요약 등)
            # 더 풍부한 정의가 이긴다 — 순서 무관하게 본문 손실을 막는다.
            idx = self._item_index.get(pi_id)
            if idx is not None and self._richness(item) > self._richness(self.policy_detail_items[idx]):
                self.policy_detail_items[idx] = item
            return
        self._seen_pi_ids.add(pi_id)
        self._item_index[pi_id] = len(self.policy_detail_items)
        self.policy_detail_items.append(item)

    @staticmethod
    def _richness(item: "PolicyDetailItem") -> tuple:
        """정의 풍부도(본문·구조 보유) — 중복 시 더 풍부한 쪽을 채택."""
        return (
            bool((item.content or "").strip()),
            len(item.rules or []),
            len(item.detail_tables or []),
            1 if item.core_question else 0,
            len(item.content or ""),
            len((item.name or "").strip()),
        )

    @staticmethod
    def _pi_id_and_name(title_text: str, id_attr: str = "") -> tuple[str, str]:
        """제목 텍스트(+ id= 속성 fallback)에서 PI/POL id와 항목명을 추출.

        세 가지 형태 지원:
          1) 괄호형:  "• 이름 (PI-...)"          (래퍼·pi-detail-title 다수)
          2) 선두 bare: "PI-... 이름"             (주문계약 div.pi-detail-title)
          3) id= 속성: id="pi-PI-..." (텍스트에 id 없을 때)  (AI검색 단독 policy-item-title)
        """
        m = re.search(rf"\(({PI_PREFIX_RE})\)", title_text)
        pi_id = m.group(1) if m else ""
        if not pi_id:
            m2 = re.match(rf"\s*[•·\-\*▪]*\s*({PI_PREFIX_RE})", title_text)
            pi_id = m2.group(1) if m2 else ""
        if not pi_id and id_attr:
            cand = re.sub(r"^pi-", "", id_attr.strip())
            if re.fullmatch(PI_PREFIX_RE, cand):
                pi_id = cand
        if not pi_id:
            return "", ""
        name = re.sub(rf"\s*\(?{re.escape(pi_id)}\)?\s*", " ", title_text, count=1)
        name = re.sub(r"^[•·\-\*▪]\s*", "", name).strip()
        return pi_id, name

    def _finalize_pi_detail_item(self) -> None:
        """진행 중인 pi-detail-title 항목을 확정한다(없으면 no-op)."""
        if not self._pi_detail_active:
            return
        self._pi_detail_active = False
        self._in_pi_detail_title = False
        title_text = self._normalize("".join(self._pi_detail_title_buf))
        body_text = self._normalize("".join(self._pi_detail_body_buf))
        self._pi_detail_title_buf = []
        self._pi_detail_body_buf = []
        id_attr = self._pi_detail_title_id
        self._pi_detail_title_id = ""
        pi_id, name = self._pi_id_and_name(title_text, id_attr)
        body_text = re.sub(r"^[•·\-\*▪]\s*", "", body_text)
        self._append_policy_detail(pi_id, name, body_text)


def parse_html(path: Path) -> tuple[list[Table], list[PolicyDetailItem], str]:
    p = PolicyHTMLParser()
    p.feed(path.read_text(encoding="utf-8"))
    p._finalize_pi_detail_item()  # 문서 끝에 열려 있던 pi-detail 항목 flush
    return p.tables, p.policy_detail_items, p.title_h1


# ---------------------------------------------------------------------------
# Entity model
# ---------------------------------------------------------------------------

@dataclass
class Meta:
    policy_id: str = ""
    topic: str = ""
    version: str = ""
    source_html: str = ""
    extracted_at: str = ""


@dataclass
class EntityBase:
    id: str
    name: str = ""
    english_name: str = "TBD"          # J placeholder
    aliases: list[str] = field(default_factory=list)  # K hook
    description: str = ""


@dataclass
class Term(EntityBase):
    type: str = "concept"              # G data dictionary
    sample_values: list[str] = field(default_factory=list)
    definition: str = ""


@dataclass
class Actor(EntityBase):
    pass


@dataclass
class UseCase(EntityBase):
    actor_ids: list[str] = field(default_factory=list)
    related_processes: list[str] = field(default_factory=list)
    process_target: str = ""  # Y/N from "프로세스 정의 대상"


@dataclass
class State(EntityBase):
    possible_values: list[str] = field(default_factory=list)  # G
    type: str = "enum"
    followup: str = ""  # "대표 후속 처리"


@dataclass
class Transition:
    from_state: str
    to_state: str
    event: str = ""
    usecase_id: str = ""
    handling: str = ""


@dataclass
class Process(EntityBase):
    usecase_id: str = ""
    actor_ids: list[str] = field(default_factory=list)
    related_function_ids: list[str] = field(default_factory=list)
    related_policy_group_ids: list[str] = field(default_factory=list)
    # Process-detail metadata (HTML "다. 프로세스 상세" vertical table)
    entry_condition: str = ""
    exit_condition: str = ""
    preceding_process: str = ""
    following_process: str = ""


@dataclass
class Function(EntityBase):
    actor_ids: list[str] = field(default_factory=list)  # H
    process_ids: list[str] = field(default_factory=list)  # reverse N:N
    details: str = ""  # "세부 기능 구성" (sub-functions)
    related_policy_group_ids: list[str] = field(default_factory=list)
    # Function-detail metadata (HTML "나. 기능 상세" vertical table)
    input_info: str = ""
    output_info: str = ""
    processing_flow: str = ""   # "처리 (상태-액션-결과)"
    failure_cases: str = ""     # "실패/예외 케이스"
    # Names extracted from "관련 정책" cell (resolved to PG IDs in _post_process)
    related_policy_names: list[str] = field(default_factory=list)


@dataclass
class PolicyGroup(EntityBase):
    pass


@dataclass
class PolicyItem(EntityBase):
    policy_group_id: str = ""
    content: str = ""


@dataclass
class Entities:
    meta: Meta = field(default_factory=Meta)
    terms: dict[str, Term] = field(default_factory=dict)
    actors: dict[str, Actor] = field(default_factory=dict)
    usecases: dict[str, UseCase] = field(default_factory=dict)
    states: dict[str, State] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)
    processes: dict[str, Process] = field(default_factory=dict)
    functions: dict[str, Function] = field(default_factory=dict)
    policy_groups: dict[str, PolicyGroup] = field(default_factory=dict)
    policy_items: dict[str, PolicyItem] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _ids_with_prefix(text: str, prefix: str) -> list[str]:
    return [m for m in ID_PATTERN.findall(text) if m.startswith(prefix + "-")]


HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "액터": (
        "액터",
        "주 액터",
        "주액터",
        "주 액터(액터 ID)",
        "주 액터(액터ID)",
        "주액터(액터 ID)",
        "주액터(액터ID)",
        "주 액터 액터 ID",
        "주액터액터ID",
        "주 액터 ID",
        "수행 주체",
        "책임 주체",
        "담당 주체",
        "primary actor",
    ),
    "액터 ID": ("액터 ID", "액터ID", "actor id"),
    "액터명": ("액터명", "액터 명", "액터 이름", "액터", "actor name", "actor"),
    "유즈케이스 ID": ("유즈케이스 ID", "유즈케이스ID", "유스케이스 ID", "관련 유즈케이스", "연결 유즈케이스", "usecase id", "use case id", "uc id"),
    "유즈케이스명": ("유즈케이스명", "유즈케이스 명", "유스케이스명", "유스케이스 명", "유즈케이스 그룹", "유즈케이스그룹", "업무 그룹", "usecase name", "use case name", "usecase group", "use case group"),
    "프로세스 정의 대상": ("프로세스 정의 대상", "프로세스정의대상", "프로세스 대상", "프로세스화 여부", "프로세스 필요 여부", "process target"),
    "프로세스 ID": ("프로세스 ID", "프로세스ID", "관련 프로세스", "연결 프로세스", "process id", "pr id"),
    "프로세스명": ("프로세스명", "프로세스 명", "프로세스 이름", "process name"),
    "관련 기능": ("관련 기능", "관련기능", "기능 ID", "기능 연결", "연결 기능", "related functions"),
    "관련 정책": ("관련 정책", "관련정책", "정책 ID", "정책 연결", "연결 정책", "related policies"),
    "기능 ID": ("기능 ID", "기능ID", "function id", "fn id"),
    "기능명": ("기능명", "기능 명", "기능 이름", "function name"),
    "세부 기능 구성": ("세부 기능 구성", "세부기능구성", "세부 구성", "하위 기능", "sub functions"),
    "정책 ID": ("정책 ID", "정책ID", "policy id", "pg id"),
    "정책명": ("정책명", "정책 명", "정책 이름", "policy name"),
    "정책 항목": ("정책 항목", "정책항목", "정책 상세", "세부 정책 항목", "policy items"),
    "상태 코드": ("상태 코드", "상태코드", "state id", "state code"),
    "상태명": ("상태명", "상태 명", "상태 이름", "state name"),
    "현재 상태": ("현재 상태", "현재상태", "from state"),
    "다음 상태": ("다음 상태", "다음상태", "to state"),
    "전이 이벤트": ("전이 이벤트", "전이이벤트", "event"),
    "처리 기준 및 후속 처리": ("처리 기준 및 후속 처리", "처리기준및후속처리", "처리 기준", "후속 처리"),
}


def _normalize_header(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", str(value or "")).casefold()


def _header_targets(header_name: str) -> set[str]:
    return {_normalize_header(value) for value in HEADER_ALIASES.get(header_name, (header_name,))}


def _matches_header(value: str, header_name: str) -> bool:
    return _normalize_header(value) in _header_targets(header_name)


def _has_header(headers: list[str], header_name: str) -> bool:
    return any(_matches_header(header, header_name) for header in headers)


def _column(row: list[Cell], headers: list[str], header_name: str) -> Cell | None:
    """Find a cell by its header name, return None if not present."""
    for i, h in enumerate(headers):
        if _matches_header(h, header_name) and i < len(row):
            return row[i]
    return None


def _column_text(row: list[Cell], headers: list[str], header_name: str) -> str:
    c = _column(row, headers, header_name)
    return c.text if c else ""


def _first_id_with_prefix(row: list[Cell], prefix: str) -> str:
    for c in row:
        for i in c.ids:
            if i.startswith(prefix + "-"):
                return i
    return ""


def classify_table(t: Table) -> str:
    """Classify a table by its CSS class (preferred) or headers (fallback).

    Class-first lookup (CLASS_TO_BUCKET)은 최신 정책서(상품상세/담기 v0.11 이후)
    의 의미적 class에 대응. Header fallback은 legacy 정책서(class 없음, 회원가입/탈퇴
    등) backward compat.
    """
    h = set(t.headers)
    classes = t.table_class.split()

    # Meta table has no <thead> — each row is <th>field</th><td>value</td>.
    # Detect by class="meta" or by inspecting first row.
    if "meta" in classes:
        return "meta"
    if not t.headers and t.rows and len(t.rows[0]) >= 2 and t.rows[0][0].is_header:
        first_key = t.rows[0][0].text.strip()
        if first_key in ("정책서 ID", "문서 구분", "버전"):
            return "meta"

    # Class-first: 의미적 class가 있으면 우선 분류 (최신 패턴 대응).
    # 회원가입/탈퇴 등 legacy 정책서는 이 단계 통과 후 헤더 fallback에 도달.
    for cls in classes:
        if cls in CLASS_TO_BUCKET:
            return CLASS_TO_BUCKET[cls]

    if "정책서 ID" in h:
        return "meta"
    if "용어 ID" in h and "용어" in h:
        return "terms"
    if _has_header(t.headers, "액터 ID") and (_has_header(t.headers, "액터명") or _has_header(t.headers, "액터")):
        return "actors"
    if _has_header(t.headers, "유즈케이스 ID") and _has_header(t.headers, "유즈케이스명"):
        return "usecases"
    if _has_header(t.headers, "상태 코드") and _has_header(t.headers, "상태명"):
        return "states"
    if _has_header(t.headers, "현재 상태") and _has_header(t.headers, "다음 상태"):
        return "transitions"
    if _has_header(t.headers, "프로세스 ID") and _has_header(t.headers, "프로세스명"):
        return "processes"
    # process detail table — vertical layout ([항목, 내용]), first row "프로세스 ID".
    # Carries actor / related-fn / related-pg cells as named-text only.
    if h == {"항목", "내용"} and t.rows and t.rows[0] and _matches_header(t.rows[0][0].text.strip(), "프로세스 ID"):
        return "process_detail"
    # function detail table — vertical layout, first row "기능 ID". Carries
    # input/processing/sub-functions/output/failure rows + related-policy names.
    if h == {"항목", "내용"} and t.rows and t.rows[0] and _matches_header(t.rows[0][0].text.strip(), "기능 ID"):
        return "function_detail"
    if _has_header(t.headers, "기능 ID") and _has_header(t.headers, "기능명"):
        return "functions"
    # 정책 목록: 정책 ID, 정책명, 설명, 정책 항목
    if _has_header(t.headers, "정책 ID") and _has_header(t.headers, "정책명") and _has_header(t.headers, "정책 항목"):
        return "policy_list"  # policy_groups (with embedded item ids)
    # 정책 상세: 정책 항목, 정책 ID 등 (다른 구조)
    if _has_header(t.headers, "정책 항목") and _has_header(t.headers, "정책 ID"):
        return "policy_detail"
    return ""


def split_id_name(text: str, prefix: str) -> tuple[str, str]:
    """Defensive: handle 'FN-XXX 기능명' mixed strings by extracting ID + leftover name."""
    text = text.strip()
    m = re.match(rf"^({re.escape(prefix)}-[A-Z0-9-]+)\s+(.*)$", text)
    if m:
        return m.group(1), m.group(2).strip()
    # plain ID only
    if re.match(rf"^{re.escape(prefix)}-[A-Z0-9-]+$", text):
        return text, ""
    return "", text  # not an ID with that prefix


def _split_id_list(text: str) -> list[str]:
    """Split a cell containing multiple IDs separated by commas/newlines.

    Handles 'FN-X 기능명, FN-Y 기능명' or 'FN-X\nFN-Y' patterns.
    Returns a deduplicated list of pure IDs (any prefix).
    """
    if not text:
        return []
    parts = re.split(r"[,\n;/]+", text)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for mid in ID_PATTERN.findall(part):
            if mid not in seen:
                out.append(mid)
                seen.add(mid)
    return out


def extract_entities(
    tables: list[Table],
    policy_detail_items: list[PolicyDetailItem],
    source_html_path: Path,
    title_h1: str = "",
) -> Entities:
    ents = Entities()
    ents.meta.source_html = str(source_html_path)
    ents.meta.extracted_at = datetime.now(KST).isoformat(timespec="seconds")
    # Derive topic from <h1> ("AI 검색 정책서" → "AI 검색")
    if title_h1:
        ents.meta.topic = re.sub(r"\s*정책서\s*$", "", title_h1).strip()

    for t in tables:
        bucket = classify_table(t)
        if not bucket:
            continue

        if bucket == "meta":
            _extract_meta(t, ents)
        elif bucket == "terms":
            _extract_terms(t, ents)
        elif bucket == "actors":
            _extract_actors(t, ents)
        elif bucket == "usecases":
            _extract_usecases(t, ents)
        elif bucket == "states":
            _extract_states(t, ents)
        elif bucket == "transitions":
            _extract_transitions(t, ents)
        elif bucket == "processes":
            _extract_processes(t, ents)
        elif bucket == "process_detail":
            _extract_process_detail(t, ents)
        elif bucket == "function_detail":
            _extract_function_detail(t, ents)
        elif bucket == "functions":
            _extract_functions(t, ents)
        elif bucket == "policy_list":
            _extract_policy_list(t, ents)
        elif bucket == "policy_detail":
            _extract_policy_detail(t, ents)

    # absorb div-based policy detail items
    for item in policy_detail_items:
        pi = ents.policy_items.get(item.pi_id) or PolicyItem(id=item.pi_id)
        pi.name = pi.name or item.name
        pi.content = pi.content or item.content
        if item.pg_id:
            pi.policy_group_id = pi.policy_group_id or item.pg_id
        ents.policy_items[item.pi_id] = pi

    # post-processing: derive missing relationships
    _post_process(ents)

    return ents


# ---------------------------------------------------------------------------
# Post-processing: derive missing relationships
# ---------------------------------------------------------------------------

def _post_process(ents: Entities) -> None:
    """Derive relationships not explicitly present in HTML.

    The policy HTML omits some links between entities:
      - State transitions reference states by name, not by code (ST-...).
      - UC tables reference actors by name only; we map name → actor id.
      - Processes do not carry a 유즈케이스 ID column; UC↔Process is implicit
        in the process ID pattern (PR-AIS-CUS-001-... ↔ US-AIS-CUS-001).
      - Process and Function tables do not have an 액터 column. We derive
        actors by walking the UC → Process → Function chain.
    """

    # Actor name → ID map (used to map UC actor cells, which contain only names)
    name_to_actor = {a.name: a.id for a in ents.actors.values() if a.name}
    for uc in ents.usecases.values():
        mapped: list[str] = []
        for entry in uc.actor_ids:
            if entry.startswith("ACT-") and entry in ents.actors:
                mapped.append(entry)
            elif entry in name_to_actor:
                mapped.append(name_to_actor[entry])
            # else: drop unrecognized entries (text without matching actor)
        # The actor cell in the UC table may have stored the raw "고객" text in
        # name form. If we didn't capture it via .ids above, the cell text was
        # treated as one entry — try to map it now.
        if not mapped and uc.actor_ids:
            for entry in uc.actor_ids:
                if entry in name_to_actor:
                    mapped.append(name_to_actor[entry])
        uc.actor_ids = mapped

    # State name → ID map
    name_to_st = {st.name: st.id for st in ents.states.values() if st.name}
    for tr in ents.transitions:
        if not tr.from_state.startswith("ST-") and tr.from_state in name_to_st:
            tr.from_state = name_to_st[tr.from_state]
        if not tr.to_state.startswith("ST-") and tr.to_state in name_to_st:
            tr.to_state = name_to_st[tr.to_state]

    # Process.usecase_id derived from ID pattern.
    # PR-{topic}-{slug}-{num}[-{sub}...] ↔ US-{topic}-{slug}-{num}.
    # Two-stage matching: (1) progressively trim trailing segments looking for
    # an exact UC, (2) if none matches, look for any UC whose ID starts with
    # the candidate prefix (handles e.g. PR-AIS-OPR-002..006 → US-AIS-OPR-001).
    uc_ids = list(ents.usecases.keys())
    uc_set = set(uc_ids)
    for proc in ents.processes.values():
        if proc.usecase_id and proc.usecase_id in uc_set:
            continue
        if not proc.id.startswith("PR-"):
            continue
        # stage 1: exact match with progressive trimming
        candidate = "US-" + proc.id[3:]
        matched = ""
        while candidate.count("-") >= 1:
            if candidate in uc_set:
                matched = candidate
                break
            idx = candidate.rfind("-")
            if idx == -1:
                break
            candidate = candidate[:idx]
        # stage 2: prefix match against UC IDs
        if not matched:
            candidate = "US-" + proc.id[3:]
            while candidate.count("-") >= 2:
                prefix_hits = [u for u in uc_ids if u.startswith(candidate + "-") or u == candidate]
                if prefix_hits:
                    matched = sorted(prefix_hits)[0]
                    break
                idx = candidate.rfind("-")
                if idx == -1:
                    break
                candidate = candidate[:idx]
            # final fallback: any UC sharing the same slug segment
            if not matched:
                parts = proc.id.split("-")
                if len(parts) >= 3:
                    slug = parts[2]  # e.g. OPR, CUS, SYS
                    candidates = [u for u in uc_ids if f"-{slug}-" in u or u.endswith(f"-{slug}")]
                    if candidates:
                        matched = sorted(candidates)[0]
        if matched:
            proc.usecase_id = matched

    # Process.actor_ids: resolve names → IDs (cells often carry "고객, 외부 인증기관"
    # without ACT- IDs). Drop entries we can't map, falling back to the parent UC.
    for proc in ents.processes.values():
        resolved: list[str] = []
        for entry in proc.actor_ids:
            if entry.startswith("ACT-") and entry in ents.actors:
                resolved.append(entry)
            elif entry in name_to_actor:
                aid = name_to_actor[entry]
                if aid not in resolved:
                    resolved.append(aid)
        if resolved:
            proc.actor_ids = resolved
        elif proc.usecase_id and proc.usecase_id in ents.usecases:
            proc.actor_ids = list(ents.usecases[proc.usecase_id].actor_ids)
        else:
            proc.actor_ids = []

    # Resolve any process-side pending function/policy_group names captured by
    # _extract_process_detail. Exact name match only — name drift between the
    # process-detail cell and the function/policy_group registry is reported as
    # a soft warning; the canonical mapping comes from the function/policy list
    # H4 sections.
    name_to_fn = {fn.name: fn.id for fn in ents.functions.values() if fn.name}
    name_to_pg = {pg.name: pg.id for pg in ents.policy_groups.values() if pg.name}
    for proc in ents.processes.values():
        for nm in getattr(proc, "_pending_fn_names", []) or []:
            fid = name_to_fn.get(nm)
            if fid and fid not in proc.related_function_ids:
                proc.related_function_ids.append(fid)
        for nm in getattr(proc, "_pending_pg_names", []) or []:
            pid = name_to_pg.get(nm)
            if pid and pid not in proc.related_policy_group_ids:
                proc.related_policy_group_ids.append(pid)
        # clean up tmp attrs so they don't end up serialized
        for attr in ("_pending_fn_names", "_pending_pg_names"):
            if hasattr(proc, attr):
                try:
                    delattr(proc, attr)
                except AttributeError:
                    pass

    # Function.related_policy_names → related_policy_group_ids via name match.
    # The HTML "관련 정책" cell carries PG names (not IDs); resolve them now.
    # This is the narrow Function→PG mapping; it takes precedence over the
    # PR-union fallback derived later in normalize_cross_refs (which only fires
    # when fn.related_policy_group_ids is still empty).
    for fn in ents.functions.values():
        for nm in fn.related_policy_names:
            pid = name_to_pg.get(nm)
            if pid and pid not in fn.related_policy_group_ids:
                fn.related_policy_group_ids.append(pid)

    # Transitions: split compound state expressions ("미가입 또는 정상" → 2 rows,
    # "전체 상태" → one row per defined state). The HTML packs these into one
    # cell, but as separate transitions they're easier to verify and map to IDs.
    expanded: list[Transition] = []
    state_codes = list(ents.states.keys())
    for tr in ents.transitions:
        from_options = _expand_state_expr(tr.from_state, name_to_st, state_codes)
        to_options = _expand_state_expr(tr.to_state, name_to_st, state_codes)
        # "기존 상태 유지" / 빈 to_state → self-loop semantically (no state change),
        # so we keep the original from_state on the right side. Same for the
        # mirror case (rare in practice).
        if not from_options and to_options:
            from_options = list(to_options)
        elif not to_options and from_options:
            to_options = list(from_options)
        elif not from_options and not to_options:
            # Both sides unresolved — keep the row but skip emission to avoid
            # filling broken_refs with "기존 상태 유지" noise. The fact that the
            # cell text exists is still captured by the state-transition table
            # in usecase_*.md / entities.yaml downstream tooling.
            continue
        for f in from_options:
            for to in to_options:
                expanded.append(Transition(
                    from_state=f, to_state=to,
                    event=tr.event, usecase_id=tr.usecase_id, handling=tr.handling,
                ))
    ents.transitions = expanded

    # Function.actor_ids derived from union of its processes' actors.
    # (Function.process_ids is filled in normalize_cross_refs; do that there.)


def _expand_state_expr(expr: str, name_to_st: dict[str, str],
                       all_state_codes: list[str]) -> list[str]:
    """Resolve a compound state expression to a list of state IDs.

    Examples:
      "정상" → ["ST-..."] (single)
      "미가입 또는 정상" → ["ST-A", "ST-B"]
      "전체 상태" / "모든 상태" → [<all state codes>]
      "기존 상태 유지" / "" → []   (caller keeps the original cell text)
    """
    s = (expr or "").strip()
    if not s:
        return []
    if s.startswith("ST-") and s in name_to_st.values():
        return [s]
    # special wildcards — no-op transition markers
    if s in ("기존 상태 유지", "현재 상태 유지", "변경 없음"):
        return []
    if s in ("전체 상태", "모든 상태"):
        return list(all_state_codes)
    # split on "또는", "/", ","
    parts = re.split(r"\s*(?:또는|,|/)\s*", s)
    resolved: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p.startswith("ST-"):
            resolved.append(p)
        elif p in name_to_st:
            resolved.append(name_to_st[p])
        else:
            # unresolved — keep original text so collect_warnings reports it
            resolved.append(p)
    return resolved


# ---------------------------------------------------------------------------


def _extract_meta(t: Table, ents: Entities) -> None:
    """Meta table has rows of [<th>field</th>, <td>value</td>] pairs."""
    for row in t.rows:
        if len(row) < 2:
            continue
        key = row[0].text.strip()
        val = row[1].text.strip()
        if key == "정책서 ID":
            ents.meta.policy_id = val
        elif key == "버전":
            ents.meta.version = val
        elif key == "정책서명" or key == "주제":
            ents.meta.topic = val


def _extract_simple(
    t: Table,
    target: dict,
    cls,
    id_col: str,
    name_col: str,
    desc_col: str = "설명",
) -> None:
    for row in t.rows:
        id_cell = _column(row, t.headers, id_col)
        if not id_cell or not id_cell.text.strip():
            continue
        eid = id_cell.text.strip()
        name = _column_text(row, t.headers, name_col)
        desc = _column_text(row, t.headers, desc_col)
        if eid in target:
            existing = target[eid]
            if not existing.description and desc:
                existing.description = desc
            if not existing.name and name:
                existing.name = name
        else:
            kwargs = dict(id=eid, name=name, description=desc)
            if cls is Term:
                # term description column is "정의"
                kwargs["definition"] = desc
            target[eid] = cls(**kwargs)


def _extract_terms(t: Table, ents: Entities) -> None:
    """Terms table. Column "설명" carries the definition in the canonical
    NC policy HTML; some older docs use "정의" instead — try both."""
    for row in t.rows:
        eid = _column_text(row, t.headers, "용어 ID").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, "용어")
        definition = (
            _column_text(row, t.headers, "설명")
            or _column_text(row, t.headers, "정의")
        )
        term = ents.terms.get(eid)
        if term is None:
            ents.terms[eid] = Term(
                id=eid, name=name, description=definition, definition=definition
            )
        else:
            if not term.name and name:
                term.name = name
            if not term.description and definition:
                term.description = definition
            if not term.definition and definition:
                term.definition = definition


def _extract_actors(t: Table, ents: Entities) -> None:
    name_col = "액터명" if "액터명" in t.headers else "액터"
    for row in t.rows:
        eid = _column_text(row, t.headers, "액터 ID").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, name_col)
        desc = _column_text(row, t.headers, "설명")
        if eid in ents.actors:
            a = ents.actors[eid]
            a.name = a.name or name
            a.description = a.description or desc
        else:
            ents.actors[eid] = Actor(id=eid, name=name, description=desc)


def _extract_usecases(t: Table, ents: Entities) -> None:
    for row in t.rows:
        eid = _column_text(row, t.headers, "유즈케이스 ID").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, "유즈케이스명")
        desc = _column_text(row, t.headers, "설명")
        actor_cell = _column(row, t.headers, "액터")
        # Cell may carry IDs (preferred) or just name text — post_process resolves names.
        if actor_cell:
            if actor_cell.ids:
                actor_ids = list(actor_cell.ids)
            elif actor_cell.text.strip():
                actor_ids = [actor_cell.text.strip()]
            else:
                actor_ids = []
        else:
            actor_ids = []
        target_cell = _column(row, t.headers, "프로세스 정의 대상")
        process_target = (target_cell.text or "").strip() if target_cell else ""
        uc = ents.usecases.get(eid) or UseCase(id=eid)
        uc.name = uc.name or name
        uc.description = uc.description or desc
        uc.actor_ids = uc.actor_ids or actor_ids
        uc.process_target = uc.process_target or process_target
        ents.usecases[eid] = uc


def _extract_states(t: Table, ents: Entities) -> None:
    for row in t.rows:
        eid = _column_text(row, t.headers, "상태 코드").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, "상태명")
        desc = _column_text(row, t.headers, "설명")
        followup = _column_text(row, t.headers, "대표 후속 처리")
        st = ents.states.get(eid) or State(id=eid)
        st.name = st.name or name
        st.description = st.description or desc
        st.followup = st.followup or followup
        ents.states[eid] = st


def _extract_transitions(t: Table, ents: Entities) -> None:
    for row in t.rows:
        cur = _column_text(row, t.headers, "현재 상태").strip()
        nxt = _column_text(row, t.headers, "다음 상태").strip()
        # cells may contain "ST-XXX 상태명" — extract first ST- id
        cur_id = _first_id_with_prefix([Cell(text=cur, ids=ID_PATTERN.findall(cur))], "ST") or cur
        nxt_id = _first_id_with_prefix([Cell(text=nxt, ids=ID_PATTERN.findall(nxt))], "ST") or nxt
        if not cur_id or not nxt_id:
            continue
        event = _column_text(row, t.headers, "전이 이벤트")
        handling = _column_text(row, t.headers, "처리 기준 및 후속 처리")
        uc_cell = _column(row, t.headers, "유즈케이스 ID")
        uc_id = ""
        if uc_cell:
            for i in uc_cell.ids:
                if i.startswith("US-"):
                    uc_id = i
                    break
            if not uc_id:
                uc_id = uc_cell.text.strip()
        ents.transitions.append(Transition(
            from_state=cur_id, to_state=nxt_id,
            event=event, usecase_id=uc_id, handling=handling,
        ))


def _extract_processes(t: Table, ents: Entities) -> None:
    for row in t.rows:
        eid = _column_text(row, t.headers, "프로세스 ID").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, "프로세스명")
        desc = _column_text(row, t.headers, "설명")
        # usecase id may live in a "유즈케이스 ID" column or be embedded in description
        uc_cell = _column(row, t.headers, "유즈케이스 ID")
        uc_id = ""
        if uc_cell:
            for i in uc_cell.ids:
                if i.startswith("US-"):
                    uc_id = i
                    break
        if not uc_id:
            # Fallback 1: extract UC ID from the table's nearest H4 section header.
            # 정책서마다 process-list 표가 UC 단위로 묶이고 h4가
            # "1) 상품 가치 탐색과 이해 (US-PDD-CUS-001)" 형태로 UC ID를 명시한다.
            # 이전 _post_process의 PR↔UC slug derive는 PR slug와 UC slug가
            # 같은 분류 체계일 때만 동작하므로, slug가 다른 정책서(예: 상품상세/담기는
            # PR=DTL/CMP/SEL, UC=CUS/OPS/CS/SYS)에서는 이 fallback이 필수.
            if t.section_h4:
                for mid in ID_PATTERN.findall(t.section_h4):
                    if mid.startswith("US-"):
                        uc_id = mid
                        break
        if not uc_id:
            # try to derive from process id pattern PR-AAA-XXX-NN → look up UC by AAA
            # (handled later by _post_process slug-derivation pass)
            pass
        actor_cell = _column(row, t.headers, "액터")
        if actor_cell and actor_cell.ids:
            actor_ids = list(actor_cell.ids)
        elif actor_cell and actor_cell.text.strip():
            # cell carries names only ("고객, 외부 인증기관") — keep raw names,
            # _post_process will resolve them via the actor name→id map.
            parts = re.split(r"[,/\n;·]+", actor_cell.text)
            actor_ids = [p.strip() for p in parts if p.strip()]
        else:
            actor_ids = []
        rfn_cell = _column(row, t.headers, "관련 기능")
        related_functions = rfn_cell.ids if rfn_cell else []
        rpg_cell = _column(row, t.headers, "관련 정책")
        related_policy_groups = [i for i in (rpg_cell.ids if rpg_cell else []) if i.startswith("PG-")]

        proc = ents.processes.get(eid) or Process(id=eid)
        proc.name = proc.name or name
        proc.description = proc.description or desc
        proc.usecase_id = proc.usecase_id or uc_id
        proc.actor_ids = proc.actor_ids or actor_ids
        # Merge — do not overwrite — so the H4-derived list from _extract_functions /
        # _extract_policy_list (which may have arrived first) is preserved.
        for fid in related_functions:
            if fid not in proc.related_function_ids:
                proc.related_function_ids.append(fid)
        for pgid in related_policy_groups:
            if pgid not in proc.related_policy_group_ids:
                proc.related_policy_group_ids.append(pgid)
        ents.processes[eid] = proc


def _extract_process_detail(t: Table, ents: Entities) -> None:
    """Vertical process detail table — rows are [항목, 내용] pairs.

    The HTML uses a single 2-col table per process with rows like:
      | 프로세스 ID   | PR-MBR-CS-003-01            |
      | 액터          | 고객, 외부 인증기관           |
      | 관련 기능     | 본인인증 처리                 |
      | 관련 정책     | 탈퇴 본인인증 적용 기준 정책... |

    Names (no IDs) are stored raw in actor_ids / fn-name / pg-name buckets;
    _post_process resolves them to IDs via the name→id maps once all entities
    have been loaded.
    """
    fields: dict[str, str] = {}
    for row in t.rows:
        if len(row) < 2:
            continue
        key = row[0].text.strip()
        val = row[1].text
        if key and val:
            fields[key] = val

    pr_id = fields.get("프로세스 ID", "").strip()
    if not pr_id or not pr_id.startswith("PR-"):
        return
    proc = ents.processes.get(pr_id) or Process(id=pr_id)
    if not proc.name:
        proc.name = fields.get("프로세스명", "").strip()
    if not proc.description:
        proc.description = fields.get("설명", "").strip()

    # actors
    actor_text = fields.get("액터", "")
    if actor_text and not proc.actor_ids:
        parts = re.split(r"[,/\n;·]+", actor_text)
        proc.actor_ids = [p.strip() for p in parts if p.strip()]

    # process-detail metadata
    if not proc.entry_condition:
        proc.entry_condition = fields.get("진입 조건", "").strip()
    if not proc.exit_condition:
        proc.exit_condition = fields.get("종료 조건", "").strip()
    if not proc.preceding_process:
        proc.preceding_process = fields.get("선행 프로세스", "").strip()
    if not proc.following_process:
        proc.following_process = fields.get("후행 프로세스", "").strip()

    # related functions — names separated by <br/>, commas, or newlines.
    # Stored on a temp attribute; _post_process resolves to FN IDs.
    rfn_text = fields.get("관련 기능", "")
    if rfn_text:
        names = [n.strip() for n in re.split(r"[\n,;]+", rfn_text) if n.strip()]
        # Also pick up any IDs already present.
        ids_in_text = ID_PATTERN.findall(rfn_text)
        for fid in ids_in_text:
            if fid.startswith("FN-") and fid not in proc.related_function_ids:
                proc.related_function_ids.append(fid)
        # Stash name-only entries for later resolution.
        if names:
            proc._pending_fn_names = [n for n in names if not n.startswith("FN-")]  # type: ignore[attr-defined]

    # related policy groups — names separated by <br/>.
    rpg_text = fields.get("관련 정책", "")
    if rpg_text:
        names = [n.strip() for n in re.split(r"[\n,;]+", rpg_text) if n.strip()]
        ids_in_text = ID_PATTERN.findall(rpg_text)
        for pid in ids_in_text:
            if pid.startswith("PG-") and pid not in proc.related_policy_group_ids:
                proc.related_policy_group_ids.append(pid)
        if names:
            proc._pending_pg_names = [n for n in names if not n.startswith("PG-")]  # type: ignore[attr-defined]

    ents.processes[pr_id] = proc


def _extract_function_detail(t: Table, ents: Entities) -> None:
    """Vertical function detail table — rows are [항목, 내용] pairs.

    The HTML uses a single 2-col table per function with rows like:
      | 기능 ID            | FN-MBR-COM-001                 |
      | 기능명             | 회원 식별 및 상태 조회          |
      | 설명               | …                              |
      | 입력 정보          | CI/DI, 회원ID, …               |
      | 처리 (상태-액션-결과) | …                            |
      | 세부 기능 구성     | …                              |
      | 출력 정보          | …                              |
      | 실패/예외 케이스   | …                              |
      | 관련 정책          | PG 이름들 (br-separated)        |

    The "관련 정책" cell carries policy-group *names* without IDs; we stash
    them on related_policy_names and let _post_process resolve to PG IDs.
    """
    fields: dict[str, str] = {}
    for row in t.rows:
        if len(row) < 2:
            continue
        key = row[0].text.strip()
        val = row[1].text
        if key:
            fields[key] = val or ""

    fn_id = fields.get("기능 ID", "").strip()
    if not fn_id or not fn_id.startswith("FN-"):
        return
    fn = ents.functions.get(fn_id) or Function(id=fn_id)

    # Identity fields — fill only when empty (don't overwrite existing).
    if not fn.name:
        fn.name = fields.get("기능명", "").strip()
    if not fn.description:
        fn.description = fields.get("설명", "").strip()
    # "세부 기능 구성" lands in `details` (kept name for backward compat).
    if not fn.details:
        fn.details = fields.get("세부 기능 구성", "").strip()

    # New metadata rows — only filled by this extractor.
    if not fn.input_info:
        fn.input_info = fields.get("입력 정보", "").strip()
    if not fn.output_info:
        fn.output_info = fields.get("출력 정보", "").strip()
    if not fn.processing_flow:
        fn.processing_flow = (
            fields.get("처리 (상태-액션-결과)", "")
            or fields.get("처리 흐름", "")
            or fields.get("처리", "")
        ).strip()
    if not fn.failure_cases:
        fn.failure_cases = (
            fields.get("실패/예외 케이스", "")
            or fields.get("실패·예외", "")
            or fields.get("예외 케이스", "")
        ).strip()

    # related policy — names + any inline PG IDs.
    rpg_text = fields.get("관련 정책", "")
    if rpg_text:
        ids_in_text = ID_PATTERN.findall(rpg_text)
        for pid in ids_in_text:
            if pid.startswith("PG-") and pid not in fn.related_policy_group_ids:
                fn.related_policy_group_ids.append(pid)
        names = [n.strip() for n in re.split(r"[\n,;]+", rpg_text) if n.strip()]
        for nm in names:
            if nm.startswith("PG-"):
                continue
            if nm not in fn.related_policy_names:
                fn.related_policy_names.append(nm)

    ents.functions[fn_id] = fn


def _extract_functions(t: Table, ents: Entities) -> None:
    # In "가. 기능 목록" the table sits under an <h4> like
    #   "1) 약관 동의 (PR-MBR-CS-001-01)"
    # — every function ID in this table is then a related_function_id of that PR.
    # This is the canonical source of process→function mapping (cf. policy doc
    # v9.31/9.32: "기능 목록을 22개 프로세스 ID 기준으로 재정리").
    pr_from_h4 = ""
    if t.section_h3 in ("가. 기능 목록", "기능 목록"):
        m = re.search(r"\(PR-[A-Z0-9-]+\)", t.section_h4 or "")
        if m:
            pr_from_h4 = m.group(0).strip("()")

    for row in t.rows:
        eid = _column_text(row, t.headers, "기능 ID").strip()
        if not eid:
            continue
        name = _column_text(row, t.headers, "기능명")
        desc = _column_text(row, t.headers, "설명")
        details = _column_text(row, t.headers, "세부 기능 구성")
        actor_cell = _column(row, t.headers, "액터")
        actor_ids = actor_cell.ids if actor_cell else []
        row_process_cell = _column(row, t.headers, "프로세스 ID")
        process_ids = [pr_from_h4] if pr_from_h4 else []
        if row_process_cell:
            process_ids.extend([item_id for item_id in row_process_cell.ids if item_id.startswith("PR-")])
        fn = ents.functions.get(eid) or Function(id=eid)
        fn.name = fn.name or name
        fn.description = fn.description or desc
        fn.details = fn.details or details
        fn.actor_ids = fn.actor_ids or actor_ids
        ents.functions[eid] = fn

        # If this row sits under "가. 기능 목록 > PR-...", wire the PR→FN link.
        # The Process row may not be in ents yet — create a stub; _extract_processes
        # will fill in name/desc/actor on its own pass.
        for process_id in process_ids:
            proc = ents.processes.get(process_id) or Process(id=process_id)
            if eid not in proc.related_function_ids:
                proc.related_function_ids.append(eid)
            ents.processes[process_id] = proc


def _extract_policy_list(t: Table, ents: Entities) -> None:
    """정책 목록: 정책 ID(PG), 정책명, 설명, 정책 항목(text listing PI ids).

    Like the function list, this table sits under <h4> with a PR ID for the
    "가. 정책 목록" subsection. Every PG-... row here is a related_policy_group
    of that PR.
    """
    pr_from_h4 = ""
    if t.section_h3 in ("가. 정책 목록", "정책 목록"):
        m = re.search(r"\(PR-[A-Z0-9-]+\)", t.section_h4 or "")
        if m:
            pr_from_h4 = m.group(0).strip("()")

    for row in t.rows:
        eid = _column_text(row, t.headers, "정책 ID").strip()
        if not eid or not eid.startswith("PG-"):
            continue
        name = _column_text(row, t.headers, "정책명")
        desc = _column_text(row, t.headers, "설명")
        pg = ents.policy_groups.get(eid) or PolicyGroup(id=eid)
        pg.name = pg.name or name
        pg.description = pg.description or desc
        ents.policy_groups[eid] = pg
        row_process_cell = _column(row, t.headers, "프로세스 ID")
        process_ids = [pr_from_h4] if pr_from_h4 else []
        if row_process_cell:
            process_ids.extend([item_id for item_id in row_process_cell.ids if item_id.startswith("PR-")])
        # 정책 항목 셀: contains PI/POL IDs and (optionally) names
        items_cell = _column(row, t.headers, "정책 항목")
        if items_cell:
            for pi_id in items_cell.ids:
                if not pi_id.startswith(("PI-", "POL-")):
                    continue
                pi = ents.policy_items.get(pi_id) or PolicyItem(id=pi_id, policy_group_id=eid)
                pi.policy_group_id = pi.policy_group_id or eid
                ents.policy_items[pi_id] = pi

        # PR→PG link from "가. 정책 목록 > <h4> PR-...".
        for process_id in process_ids:
            proc = ents.processes.get(process_id) or Process(id=process_id)
            if eid not in proc.related_policy_group_ids:
                proc.related_policy_group_ids.append(eid)
            ents.processes[process_id] = proc


def _extract_policy_detail(t: Table, ents: Entities) -> None:
    """정책 상세: rows describing individual policy items.

    Headers vary but typically contain 정책 ID (PG or PI), 정책 항목 (name+content).
    Strategy: find any PI- id in row, accumulate its content text.
    """
    for row in t.rows:
        pi_id = ""
        pg_id = ""
        for c in row:
            for cid in c.ids:
                if cid.startswith(("PI-", "POL-")) and not pi_id:
                    pi_id = cid
                elif cid.startswith("PG-") and not pg_id:
                    pg_id = cid
        if not pi_id:
            continue
        # Try to find a name column "정책 항목" — it may include "PI-XXX 이름" form.
        item_cell = _column(row, t.headers, "정책 항목")
        name = ""
        content = ""
        if item_cell:
            name = item_cell.text
            # strip leading PI/POL id from name if present
            name = re.sub(rf"^{re.escape(pi_id)}\s*", "", name).strip()
        # content may live in another column
        for hname in ("정책 내용", "내용", "설명", "작성 기준"):
            c = _column(row, t.headers, hname)
            if c and c.text:
                content = c.text
                break
        pi = ents.policy_items.get(pi_id) or PolicyItem(id=pi_id)
        pi.name = pi.name or name
        pi.content = pi.content or content
        pi.policy_group_id = pi.policy_group_id or pg_id
        ents.policy_items[pi_id] = pi


# ---------------------------------------------------------------------------
# Cross-ref normalization (derive reverse links, build cross_refs map)
# ---------------------------------------------------------------------------

def normalize_cross_refs(ents: Entities) -> dict[str, dict[str, list[str]]]:
    # Process → Functions (forward); Function.process_ids (reverse) derived.
    for proc in ents.processes.values():
        for fn_id in proc.related_function_ids:
            fn = ents.functions.get(fn_id)
            if fn and proc.id not in fn.process_ids:
                fn.process_ids.append(proc.id)

    # Function.actor_ids derived from union of its processes' actors.
    for fn in ents.functions.values():
        if fn.actor_ids:
            continue
        seen = set()
        for pid in fn.process_ids:
            proc = ents.processes.get(pid)
            if not proc:
                continue
            for aid in proc.actor_ids:
                if aid not in seen:
                    fn.actor_ids.append(aid)
                    seen.add(aid)

    # Function.related_policy_group_ids derived from union of its processes' PG.
    # Wider than the truly-narrow Function→PG mapping (which lives in the
    # function-detail vertical table, not yet extracted), but enough to surface
    # which policy packages a function participates in. Skipped when already
    # populated upstream so Phase B's function-detail extractor can override.
    for fn in ents.functions.values():
        if fn.related_policy_group_ids:
            continue
        seen_pg: set[str] = set()
        for pid in fn.process_ids:
            proc = ents.processes.get(pid)
            if not proc:
                continue
            for pgid in proc.related_policy_group_ids:
                if pgid not in seen_pg:
                    fn.related_policy_group_ids.append(pgid)
                    seen_pg.add(pgid)

    # PolicyItems already carry policy_group_id; build group→items cross_ref later.

    cross: dict[str, dict[str, list[str]]] = {
        "function_to_processes": {},
        "process_to_functions": {},
        "process_to_policy_groups": {},
        "policy_group_to_items": {},
        "usecase_to_processes": {},
    }
    for proc in ents.processes.values():
        cross["process_to_functions"][proc.id] = list(proc.related_function_ids)
        cross["process_to_policy_groups"][proc.id] = list(proc.related_policy_group_ids)
    for fn in ents.functions.values():
        cross["function_to_processes"][fn.id] = list(fn.process_ids)
    for pi in ents.policy_items.values():
        if pi.policy_group_id:
            cross["policy_group_to_items"].setdefault(pi.policy_group_id, []).append(pi.id)
    for uc in ents.usecases.values():
        related = [p.id for p in ents.processes.values() if p.usecase_id == uc.id]
        uc.related_processes = related
        cross["usecase_to_processes"][uc.id] = related
    return cross


def build_hierarchy(ents: Entities) -> list[dict[str, Any]]:
    """UC → Process → Function tree."""
    tree: list[dict[str, Any]] = []
    for uc in ents.usecases.values():
        node = {"id": uc.id, "children": []}
        for proc_id in uc.related_processes:
            proc = ents.processes.get(proc_id)
            if not proc:
                continue
            pnode = {"id": proc.id, "children": []}
            for fn_id in proc.related_function_ids:
                pnode["children"].append({"id": fn_id})
            node["children"].append(pnode)
        tree.append(node)
    return tree


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

def collect_warnings(ents: Entities, cross: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    w: dict[str, list[str]] = {
        "broken_refs": [],
        "orphan_entities": [],
        "n_n_inconsistent": [],
        "id_format_violations": [],
        "suspected_missing_policies": [],
        # P0: silent failure 감지 — 변환은 성공한 듯 보이지만 입력 신호 대비
        # 산출물이 비정상적으로 적은 경우 (회원가입/탈퇴와 다른 패턴 정책서를
        # 변환할 때 cold review 없이도 즉시 catch). 비어 있으면 정상.
        "silent_failure_suspect": [],
        # P2: PREFIX_TO_TYPE에 없는 prefix가 셀/정책 상세에서 발견된 경우.
        # 새 정책서가 도입한 신규 ID 종류를 사용자/코덱스가 검토 후 등록할
        # 수 있게 단순 알람만 띄운다.
        "unknown_id_prefixes": [],
    }
    def known(eid: str) -> bool:
        for d in (ents.terms, ents.actors, ents.usecases, ents.states,
                  ents.processes, ents.functions, ents.policy_groups, ents.policy_items):
            if eid in d:
                return True
        return False

    # broken refs
    for proc in ents.processes.values():
        for fid in proc.related_function_ids:
            if fid not in ents.functions:
                w["broken_refs"].append(f"{proc.id} → unknown FN {fid}")
        for pg in proc.related_policy_group_ids:
            if pg not in ents.policy_groups:
                w["broken_refs"].append(f"{proc.id} → unknown PG {pg}")
        if proc.usecase_id and proc.usecase_id not in ents.usecases:
            w["broken_refs"].append(f"{proc.id} → unknown UC {proc.usecase_id}")
    for fn in ents.functions.values():
        for pid in fn.process_ids:
            if pid not in ents.processes:
                w["broken_refs"].append(f"{fn.id} → unknown PR {pid}")
    for pi in ents.policy_items.values():
        if pi.policy_group_id and pi.policy_group_id not in ents.policy_groups:
            w["broken_refs"].append(f"{pi.id} → unknown PG {pi.policy_group_id}")
    for tr in ents.transitions:
        if tr.from_state and tr.from_state not in ents.states:
            w["broken_refs"].append(f"transition → unknown ST {tr.from_state}")
        if tr.to_state and tr.to_state not in ents.states:
            w["broken_refs"].append(f"transition → unknown ST {tr.to_state}")
        if tr.usecase_id and tr.usecase_id not in ents.usecases:
            w["broken_refs"].append(f"transition → unknown UC {tr.usecase_id}")

    # orphans
    referenced_fns = {fid for p in ents.processes.values() for fid in p.related_function_ids}
    for fid in ents.functions:
        if fid not in referenced_fns:
            w["orphan_entities"].append(f"FN {fid} not referenced by any process")
    referenced_pgs = {pg for p in ents.processes.values() for pg in p.related_policy_group_ids}
    for pgid in ents.policy_groups:
        if pgid not in referenced_pgs:
            w["orphan_entities"].append(f"PG {pgid} not referenced by any process")
    grouped_pis = {pi.id for pi in ents.policy_items.values() if pi.policy_group_id}
    for piid in ents.policy_items:
        if piid not in grouped_pis:
            w["orphan_entities"].append(f"PI {piid} has no parent PG")

    # ID format violations (any uppercase-dash IDs that don't match known prefix).
    # `ents.states` is intentionally excluded: state codes such as MBR_NONE are
    # prefix-less by domain convention. They're already validated via broken_refs
    # against ents.states membership, so format-prefix checks would only produce
    # false positives.
    for table_ents in (ents.terms, ents.actors, ents.usecases,
                       ents.processes, ents.functions, ents.policy_groups, ents.policy_items):
        for eid in table_ents:
            prefix = eid.split("-", 1)[0]
            if prefix not in PREFIX_TO_TYPE:
                w["id_format_violations"].append(eid)

    return w


def append_silent_failure_warnings(
    w: dict[str, list[str]],
    ents: Entities,
    tables: list[Table],
    policy_detail_items: list[PolicyDetailItem],
    html_text: str,
    diagrams: list[Diagram],
) -> None:
    """P0 + P2 추가 감지. build_dev_format이 base warnings 위에 호출.

    상품상세/담기(v0.11) 변환 후 발견된 위험 패턴을 정량적으로 catch.
    기존 3 baseline은 모두 정상 범위이므로 새 warning 발생 안 함 (회귀 0).
    """
    # P0.1 — diagram-wrap 발견 vs 추출된 다이어그램 수 비교
    diagram_wrap_re = re.compile(r'<div [^>]*class="[^"]*\bdiagram-wrap\b[^"]*"')
    wrap_count = len(diagram_wrap_re.findall(html_text))
    if wrap_count > 0 and not diagrams:
        w["silent_failure_suspect"].append(
            f"{wrap_count}개의 <div class='diagram-wrap'> 가 입력에 있지만 추출된 "
            "다이어그램이 0개입니다. extract_diagrams regex 또는 SVG 파싱 회귀 의심."
        )

    # P0.2 — state-transition table 행 수 vs 추출된 transitions
    transition_table_rows = 0
    for t in tables:
        if classify_table(t) == "transitions":
            transition_table_rows += len(t.rows)
    if transition_table_rows > 0 and len(ents.transitions) == 0:
        w["silent_failure_suspect"].append(
            f"state-transition 분류 테이블에 {transition_table_rows}개 행이 있지만 "
            "ents.transitions가 0개입니다. _extract_transitions 또는 헤더 컬럼명 alias 회귀 의심."
        )

    # P0.3 — placeholder UC 비율 (process가 하나도 연결 안 된 UC)
    # 시스템/BSS UC들은 process 없는 게 정상 패턴이라 임계치를 보수적으로 80%로 둠
    # (회원가입/탈퇴 baseline: 9/13 = 69% placeholder인데 BSS·AUTH·GRD UC라 정상).
    # 80% 넘으면 mapping 자체가 broken인 경우만 catch.
    # 참고: 상품상세/담기 fix 전은 15/16 = 94%였으므로 이 임계치로 잡혔을 것.
    if ents.usecases:
        placeholder = [uc.id for uc in ents.usecases.values() if not uc.related_processes]
        ratio = len(placeholder) / len(ents.usecases)
        if ratio > 0.8:
            sample = ", ".join(placeholder[:5])
            tail = f" ... 외 {len(placeholder)-5}개" if len(placeholder) > 5 else ""
            w["silent_failure_suspect"].append(
                f"{len(placeholder)}/{len(ents.usecases)} UC가 related_processes가 비어있습니다 "
                f"({ratio*100:.0f}%). PR↔UC derive 미스 의심. 후보: {sample}{tail}"
            )

    # P0.4 — mapping rows vs UC×PR product (너무 적으면 cross-link 누락)
    expected_min = max(len(ents.usecases), len(ents.processes))
    actual_rows = sum(
        1 for uc in ents.usecases.values() for _ in uc.related_processes
    )
    if expected_min >= 10 and actual_rows < expected_min * 0.3:
        w["silent_failure_suspect"].append(
            f"UC×Process 연결이 {actual_rows}건뿐입니다 (UC {len(ents.usecases)}, "
            f"PR {len(ents.processes)}). UC.related_processes 매핑 끊김 의심."
        )

    # P2 — PREFIX_TO_TYPE에 없는 prefix가 셀/정책 상세에서 발견
    seen_unknown: set[str] = set()
    for t in tables:
        for row in t.rows:
            for cell in row:
                for mid in cell.ids:
                    prefix = mid.split("-", 1)[0]
                    if prefix and prefix not in PREFIX_TO_TYPE:
                        seen_unknown.add(prefix)
    for pdi in policy_detail_items:
        for mid in ID_PATTERN.findall((pdi.content or "") + " " + (pdi.name or "")):
            prefix = mid.split("-", 1)[0]
            if prefix and prefix not in PREFIX_TO_TYPE:
                seen_unknown.add(prefix)
    for prefix in sorted(seen_unknown):
        w["unknown_id_prefixes"].append(
            f"'{prefix}-' prefix가 셀/정책 상세에서 발견되었지만 PREFIX_TO_TYPE에 없습니다. "
            "PREFIX_TO_TYPE에 매핑을 추가하거나 false-positive면 무시."
        )


# ---------------------------------------------------------------------------
# YAML output (hand-written, schema is simple)
# ---------------------------------------------------------------------------

def _yaml_escape(s: str) -> str:
    """Quote a string for YAML scalar use. Always double-quote and escape."""
    if s is None:
        return '""'
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _yaml_multiline(s: str, indent: int) -> str:
    """Render multiline string as YAML block scalar (|), or quoted if short."""
    if not s:
        return '""'
    if "\n" not in s:
        return _yaml_escape(s)
    pad = " " * indent
    body = "\n".join(pad + line for line in s.splitlines())
    return f"|\n{body}"


def _yaml_list_inline(items: list[str]) -> str:
    if not items:
        return "[]"
    return "[" + ", ".join(_yaml_escape(i) for i in items) + "]"


def serialize_yaml(ents: Entities, cross: dict[str, dict[str, list[str]]],
                   hierarchy: list[dict[str, Any]],
                   diagrams: list[Diagram] | None = None) -> str:
    lines: list[str] = []

    # meta
    lines.append("meta:")
    lines.append(f"  policy_id: {_yaml_escape(ents.meta.policy_id)}")
    lines.append(f"  topic: {_yaml_escape(ents.meta.topic)}")
    lines.append(f"  version: {_yaml_escape(ents.meta.version)}")
    lines.append(f"  extracted_at: {_yaml_escape(ents.meta.extracted_at)}")
    lines.append(f"  source_html: {_yaml_escape(ents.meta.source_html)}")
    lines.append("")

    # terms
    lines.append("terms:")
    for tid, term in ents.terms.items():
        lines.append(f"  - id: {_yaml_escape(term.id)}")
        lines.append(f"    name: {_yaml_escape(term.name)}")
        lines.append(f"    english_name: {_yaml_escape(term.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(term.aliases)}")
        lines.append(f"    type: {_yaml_escape(term.type)}")
        lines.append(f"    sample_values: {_yaml_list_inline(term.sample_values)}")
        lines.append(f"    definition: {_yaml_multiline(term.definition or term.description, 6)}")
    lines.append("")

    # actors
    lines.append("actors:")
    for aid, act in ents.actors.items():
        lines.append(f"  - id: {_yaml_escape(act.id)}")
        lines.append(f"    name: {_yaml_escape(act.name)}")
        lines.append(f"    english_name: {_yaml_escape(act.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(act.aliases)}")
        lines.append(f"    description: {_yaml_multiline(act.description, 6)}")
    lines.append("")

    # usecases
    lines.append("usecases:")
    for uid, uc in ents.usecases.items():
        lines.append(f"  - id: {_yaml_escape(uc.id)}")
        lines.append(f"    name: {_yaml_escape(uc.name)}")
        lines.append(f"    english_name: {_yaml_escape(uc.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(uc.aliases)}")
        lines.append(f"    process_target: {_yaml_escape(uc.process_target)}")
        lines.append(f"    actor_ids: {_yaml_list_inline(uc.actor_ids)}")
        lines.append(f"    related_processes: {_yaml_list_inline(uc.related_processes)}")
        lines.append(f"    description: {_yaml_multiline(uc.description, 6)}")
    lines.append("")

    # states
    lines.append("states:")
    for sid, st in ents.states.items():
        lines.append(f"  - id: {_yaml_escape(st.id)}")
        lines.append(f"    name: {_yaml_escape(st.name)}")
        lines.append(f"    english_name: {_yaml_escape(st.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(st.aliases)}")
        lines.append(f"    type: {_yaml_escape(st.type)}")
        lines.append(f"    possible_values: {_yaml_list_inline(st.possible_values)}")
        lines.append(f"    description: {_yaml_multiline(st.description, 6)}")
        lines.append(f"    followup: {_yaml_multiline(st.followup, 6)}")
    lines.append("")

    # transitions
    lines.append("transitions:")
    for tr in ents.transitions:
        lines.append(f"  - from_state: {_yaml_escape(tr.from_state)}")
        lines.append(f"    to_state: {_yaml_escape(tr.to_state)}")
        lines.append(f"    event: {_yaml_escape(tr.event)}")
        lines.append(f"    usecase_id: {_yaml_escape(tr.usecase_id)}")
        lines.append(f"    handling: {_yaml_multiline(tr.handling, 6)}")
    lines.append("")

    # processes
    lines.append("processes:")
    for pid, proc in ents.processes.items():
        lines.append(f"  - id: {_yaml_escape(proc.id)}")
        lines.append(f"    name: {_yaml_escape(proc.name)}")
        lines.append(f"    english_name: {_yaml_escape(proc.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(proc.aliases)}")
        lines.append(f"    usecase_id: {_yaml_escape(proc.usecase_id)}")
        lines.append(f"    actor_ids: {_yaml_list_inline(proc.actor_ids)}")
        lines.append(f"    related_function_ids: {_yaml_list_inline(proc.related_function_ids)}")
        lines.append(f"    related_policy_group_ids: {_yaml_list_inline(proc.related_policy_group_ids)}")
        lines.append(f"    entry_condition: {_yaml_multiline(proc.entry_condition, 6)}")
        lines.append(f"    exit_condition: {_yaml_multiline(proc.exit_condition, 6)}")
        lines.append(f"    preceding_process: {_yaml_multiline(proc.preceding_process, 6)}")
        lines.append(f"    following_process: {_yaml_multiline(proc.following_process, 6)}")
        lines.append(f"    description: {_yaml_multiline(proc.description, 6)}")
    lines.append("")

    # functions
    lines.append("functions:")
    for fid, fn in ents.functions.items():
        lines.append(f"  - id: {_yaml_escape(fn.id)}")
        lines.append(f"    name: {_yaml_escape(fn.name)}")
        lines.append(f"    english_name: {_yaml_escape(fn.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(fn.aliases)}")
        lines.append(f"    actor_ids: {_yaml_list_inline(fn.actor_ids)}")
        lines.append(f"    process_ids: {_yaml_list_inline(fn.process_ids)}")
        lines.append(f"    related_policy_group_ids: {_yaml_list_inline(fn.related_policy_group_ids)}")
        lines.append(f"    description: {_yaml_multiline(fn.description, 6)}")
        lines.append(f"    details: {_yaml_multiline(fn.details, 6)}")
        lines.append(f"    input_info: {_yaml_multiline(fn.input_info, 6)}")
        lines.append(f"    output_info: {_yaml_multiline(fn.output_info, 6)}")
        lines.append(f"    processing_flow: {_yaml_multiline(fn.processing_flow, 6)}")
        lines.append(f"    failure_cases: {_yaml_multiline(fn.failure_cases, 6)}")
    lines.append("")

    # policy_groups
    lines.append("policy_groups:")
    for pgid, pg in ents.policy_groups.items():
        lines.append(f"  - id: {_yaml_escape(pg.id)}")
        lines.append(f"    name: {_yaml_escape(pg.name)}")
        lines.append(f"    english_name: {_yaml_escape(pg.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(pg.aliases)}")
        lines.append(f"    description: {_yaml_multiline(pg.description, 6)}")
    lines.append("")

    # policy_items
    lines.append("policy_items:")
    for piid, pi in ents.policy_items.items():
        lines.append(f"  - id: {_yaml_escape(pi.id)}")
        lines.append(f"    name: {_yaml_escape(pi.name)}")
        lines.append(f"    english_name: {_yaml_escape(pi.english_name)}")
        lines.append(f"    aliases: {_yaml_list_inline(pi.aliases)}")
        lines.append(f"    policy_group_id: {_yaml_escape(pi.policy_group_id)}")
        lines.append(f"    content: {_yaml_multiline(pi.content, 6)}")
    lines.append("")

    # cross_refs
    lines.append("cross_refs:")
    for key, mapping in cross.items():
        lines.append(f"  {key}:")
        for k, v in mapping.items():
            lines.append(f"    {_yaml_escape(k)}: {_yaml_list_inline(v)}")
    lines.append("")

    # hierarchy
    lines.append("hierarchy:")
    def _render_node(node: dict[str, Any], depth: int) -> None:
        pad = "  " * depth
        lines.append(f"{pad}- id: {_yaml_escape(node['id'])}")
        children = node.get("children") or []
        if children:
            lines.append(f"{pad}  children:")
            for ch in children:
                _render_node(ch, depth + 2)
    for n in hierarchy:
        _render_node(n, 1)

    # diagrams
    if diagrams:
        lines.append("")
        lines.append("diagrams:")
        for d in diagrams:
            lines.append(f"  - type: {_yaml_escape(d.type)}")
            lines.append(f"    section: {_yaml_escape(d.section)}")
            lines.append(f"    svg_file: {_yaml_escape(d.svg_file)}")
            lines.append(f"    referenced_ids: {_yaml_list_inline(d.referenced_ids)}")
            lines.append(f"    notes: {_yaml_list_inline(d.notes)}")
            # mermaid as block scalar
            if d.mermaid:
                lines.append("    mermaid: |")
                for ln in d.mermaid.split("\n"):
                    lines.append(f"      {ln}")
            else:
                lines.append('    mermaid: ""')

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# INDEX.md
# ---------------------------------------------------------------------------

def _summarize(text: str, n: int = 150) -> str:
    if not text:
        return ""
    one = re.sub(r"\s+", " ", text).strip()
    return one[:n] + ("…" if len(one) > n else "")


def build_index_md(ents: Entities, hierarchy: list[dict[str, Any]],
                   diagrams: list[Diagram] | None = None) -> str:
    lines: list[str] = []
    lines.append(f"# 00_INDEX — {ents.meta.topic} ({ents.meta.policy_id} {ents.meta.version})")
    lines.append("")
    lines.append(f"추출 일시: {ents.meta.extracted_at}  ")
    lines.append(f"원본 HTML: `{ents.meta.source_html}`")
    lines.append("")
    lines.append("## Claude Code 사용 가이드")
    lines.append("")
    lines.append("이 폴더는 정책서 1개를 디자인팀/개발팀 친화 형태로 변환한 결과입니다. Claude Code로 이 폴더를 통째로 받았다면 다음 순서로 활용하세요:")
    lines.append("")
    lines.append("1. **이 INDEX 파일**을 먼저 읽어 전체 구성과 ID 체계를 파악하세요.")
    lines.append("2. **유즈케이스 단위 작업**은 `usecase_<UC-ID>.md`를 읽으세요. 한 파일 안에 그 UC의 Process·Function·Policy가 inline으로 응집되어 있습니다.")
    lines.append("3. **N:N 관계 navigation**(예: 어떤 Function이 어느 Process들에 쓰이는지)은 `mapping.csv` 또는 `entities.yaml#cross_refs`를 보세요.")
    lines.append("4. **머신 처리**(스크립트, 파이프라인 입력)는 `entities.yaml`이 최적입니다.")
    lines.append("5. **데이터 무결성 점검**은 `warnings.md`를 보세요. 깨진 참조·고아 엔티티·누락 의심 항목이 자동 검출됩니다.")
    lines.append("6. **ID 검색**은 정확한 ID 문자열로 폴더 전체 grep을 권장합니다: `grep -r '<ID>' .`")
    lines.append("")
    lines.append("## 파일 구성")
    lines.append("")
    lines.append("| 파일 | 내용 | 권장 사용 시점 |")
    lines.append("|---|---|---|")
    lines.append("| `00_INDEX.md` | 이 진입 가이드 + ID 일람 + 계층 트리 | 폴더를 처음 받았을 때 |")
    lines.append("| `usecase_*.md` | UC별 슬라이스 (Process·Function·Policy inline 응집) | UC 단위로 작업할 때 |")
    lines.append("| `mapping.csv` | UC→Process→Function→Policy→PolicyItem 평탄화 매트릭스 | N:N 관계를 한눈에 볼 때 / Excel 피벗 |")
    lines.append("| `entities.yaml` | 정체성·관계·데이터 딕셔너리 머신 dump | 스크립트·파이프라인 입력 |")
    lines.append("| `warnings.md` | 자동 검증 리포트 (broken refs, orphans, 누락 의심 정책) | 데이터 무결성 점검 |")
    lines.append("")
    lines.append("## 통계")
    lines.append("")
    lines.append(f"- 액터 {len(ents.actors)} · 유즈케이스 {len(ents.usecases)} · 상태 {len(ents.states)} · 상태 전이 {len(ents.transitions)}")
    lines.append(f"- 프로세스 {len(ents.processes)} · 기능 {len(ents.functions)}")
    lines.append(f"- 정책 그룹 {len(ents.policy_groups)} · 정책 항목 {len(ents.policy_items)}")
    lines.append(f"- 용어 {len(ents.terms)}")
    lines.append("")
    lines.append("## UC 일람 + 슬라이스 링크")
    lines.append("")
    lines.append("| UC ID | UC 이름 | 슬라이스 파일 |")
    lines.append("|---|---|---|")
    for uc in ents.usecases.values():
        fname = f"usecase_{uc.id}.md"
        lines.append(f"| `{uc.id}` | {uc.name} | [{fname}](./{fname}) |")
    lines.append("")
    lines.append("## ID Hierarchy 트리 (UC → Process → Function)")
    lines.append("")
    lines.append("```")
    def _tree(node: dict[str, Any], depth: int) -> None:
        pad = "  " * depth
        nm = _entity_name(ents, node["id"])
        lines.append(f"{pad}- {node['id']}{f' — {nm}' if nm else ''}")
        for ch in node.get("children", []):
            _tree(ch, depth + 1)
    for n in hierarchy:
        _tree(n, 0)
    lines.append("```")
    lines.append("")
    lines.append("## 엔티티별 ID 일람")
    lines.append("")
    for label, items, defloc in [
        ("Terms (용어)", ents.terms.values(), "entities.yaml#terms"),
        ("Actors (액터)", ents.actors.values(), "entities.yaml#actors"),
        ("Use Cases", ents.usecases.values(), "각 usecase_*.md"),
        ("States", ents.states.values(), "entities.yaml#states"),
        ("Processes", ents.processes.values(), "해당 UC의 usecase_*.md 안"),
        ("Functions", ents.functions.values(), "해당 Process가 속한 usecase_*.md (반복 등장 OK)"),
        ("Policy Groups", ents.policy_groups.values(), "해당 Process가 속한 usecase_*.md + entities.yaml#policy_groups"),
        ("Policy Items", ents.policy_items.values(), "해당 PG가 속한 usecase_*.md + entities.yaml#policy_items"),
    ]:
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"정의 위치: `{defloc}`")
        lines.append("")
        lines.append("| ID | 이름 |")
        lines.append("|---|---|")
        for e in items:
            lines.append(f"| `{e.id}` | {e.name} |")
        lines.append("")
    lines.append("## N:N 관계 안내")
    lines.append("")
    lines.append("- **Process ↔ Function은 N:N**입니다. 한 Function이 여러 Process에서 쓰일 수 있습니다.")
    lines.append("- 전체 N:N 매트릭스: `mapping.csv` (Excel 피벗) 또는 `entities.yaml#cross_refs.function_to_processes` 참조.")
    lines.append("- UC 슬라이스 안에서는 같은 Function이 여러 Process sub-section에 반복 등장할 수 있습니다 (의도된 응집).")
    if diagrams:
        lines.append("")
        lines.append("## Diagrams (다이어그램)")
        lines.append("")
        lines.append("원본 HTML의 인라인 SVG에서 추출한 Mermaid 텍스트와 SVG fallback. Mermaid는 Claude Code grep·Read·AI input 친화, SVG는 사람 시각 검토용.")
        lines.append("")
        lines.append("| # | 유형 | 원본 섹션 | Mermaid | SVG |")
        lines.append("|---|---|---|---|---|")
        type_label = {"uc": "UC 다이어그램", "state": "상태 전이", "bpmn": "BPMN 업무 흐름도", "unknown": "미분류"}
        for i, d in enumerate(diagrams, 1):
            svg_link = f"[{d.svg_file}](./{d.svg_file})" if d.svg_file else "-"
            ml_anchor = f"#diagram-{i}-{d.type}"
            lines.append(f"| {i} | {type_label.get(d.type, d.type)} | {d.section} | [보기]({ml_anchor}) | {svg_link} |")
        lines.append("")
        for i, d in enumerate(diagrams, 1):
            lines.append(f"### Diagram {i} {type_label.get(d.type, d.type)} {{#diagram-{i}-{d.type}}}")
            lines.append("")
            lines.append(f"- 원본 섹션: {d.section or '(미상)'}")
            if d.referenced_ids:
                lines.append(f"- 참조 ID: {', '.join(f'`{x}`' for x in d.referenced_ids)}")
            if d.svg_file:
                lines.append(f"- SVG fallback: [{d.svg_file}](./{d.svg_file})")
            if d.notes:
                lines.append("- 주의:")
                for n in d.notes:
                    lines.append(f"  - {n}")
            lines.append("")
            if d.mermaid:
                lines.append("```mermaid")
                lines.append(d.mermaid)
                lines.append("```")
            else:
                lines.append("_Mermaid 추출 실패 — SVG fallback 참조._")
            lines.append("")
    return "\n".join(lines) + "\n"


def _entity_name(ents: Entities, eid: str) -> str:
    for d in (ents.terms, ents.actors, ents.usecases, ents.states,
              ents.processes, ents.functions, ents.policy_groups, ents.policy_items):
        if eid in d:
            return getattr(d[eid], "name", "")
    return ""


# ---------------------------------------------------------------------------
# usecase_*.md
# ---------------------------------------------------------------------------

def build_usecase_md(uc: UseCase, ents: Entities) -> str:
    """Render a usecase markdown file in the design-team 4-level layout:

        frontmatter (UC identity)
        # Usecase: UC-ID
        ## Flowchart (linear PR chain — branches in BPMN diagram)
        ## Process: PR-XXX  + yaml + 메타 표
        ### Function: FN-XXX + yaml + 메타 표
        #### Policy Group: PG-XXX + yaml + PI 표

    PR sub-section retains its `{#process-PR-XXX-XX}` anchor for grep/link.
    A process emits each related Function block; a Function emits each PG it
    declares (function.related_policy_group_ids) — when that field is empty,
    falls back to the process-level PG union so no policy is dropped.
    """
    lines: list[str] = []
    referenced_ids: set[str] = {uc.id}

    # ---- frontmatter ----
    actor_names = [
        ents.actors[aid].name if aid in ents.actors else aid for aid in uc.actor_ids
    ]
    lines.append("---")
    lines.append(f"유즈케이스_ID: {uc.id}")
    lines.append(f"액터: {', '.join(actor_names) if actor_names else '-'}")
    if uc.description:
        # frontmatter values must not contain bare newlines — collapse to one line
        desc_one = " ".join(uc.description.split())
        lines.append(f"설명: {desc_one}")
    lines.append(f"프로세스_정의_대상: {uc.process_target or '-'}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Usecase: {uc.id} — {uc.name}")
    lines.append("")

    # ---- Flowchart (linear PR sequence) ----
    proc_chain = [pid for pid in uc.related_processes if pid in ents.processes]
    if proc_chain:
        lines.append("## Flowchart")
        lines.append("")
        lines.append("> 단순 직렬 흐름. 분기·게이트웨이는 `00_INDEX.md` BPMN 다이어그램 참조.")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph LR")
        lines.append("    Start((시작))")
        prev = "Start"
        for pid in proc_chain:
            proc = ents.processes[pid]
            node = _bpmn_id(pid)
            label = f"{proc.name}<br/>{pid}".replace('"', "'")
            lines.append(f"    {node}[{label}]")
            lines.append(f"    {prev} --> {node}")
            prev = node
        lines.append("    End((종료))")
        lines.append(f"    {prev} --> End")
        lines.append("```")
        lines.append("")

    # ---- Process / Function / Policy Group nesting ----
    def _yaml_block(pairs: list[tuple[str, Any]]) -> list[str]:
        out = ["```yaml"]
        for k, v in pairs:
            if isinstance(v, list):
                if v:
                    out.append(f"{k}: [{', '.join(v)}]")
                else:
                    out.append(f"{k}: []")
            else:
                vs = str(v or "").replace("\n", " ").strip()
                out.append(f"{k}: {vs}")
        out.append("```")
        return out

    def _meta_table(rows: list[tuple[str, str]]) -> list[str]:
        out = ["| 항목 | 내용 |", "| --- | --- |"]
        for k, v in rows:
            vshort = (v or "-").replace("\n", " ").strip() or "-"
            out.append(f"| {k} | {vshort} |")
        return out

    for proc_id in proc_chain:
        proc = ents.processes[proc_id]
        referenced_ids.add(proc.id)
        anchor = f"process-{proc.id}"
        lines.append(f"## Process: {proc.id} — {proc.name} {{#{anchor}}}")
        lines.append("")
        lines.extend(_yaml_block([
            ("프로세스_ID", proc.id),
            ("프로세스명", proc.name),
            ("설명", proc.description),
            ("관련_기능", proc.related_function_ids),
        ]))
        lines.append("")
        actors_pretty = ", ".join(
            ents.actors[aid].name if aid in ents.actors else aid
            for aid in proc.actor_ids
        ) or "-"
        lines.extend(_meta_table([
            ("액터", actors_pretty),
            ("진입 조건", proc.entry_condition),
            ("종료 조건", proc.exit_condition),
            ("선행 프로세스", proc.preceding_process),
            ("후행 프로세스", proc.following_process),
        ]))
        lines.append("")

        if not proc.related_function_ids:
            lines.append("_관련 기능 없음_")
            lines.append("")
            continue

        for fn_id in proc.related_function_ids:
            referenced_ids.add(fn_id)
            fn = ents.functions.get(fn_id)
            lines.append(f"### Function: {fn_id}")
            lines.append("")
            if fn is None:
                lines.append("_(기능 정의 누락 — entities.yaml에 정의되지 않음)_")
                lines.append("")
                continue
            # PG list for this function — narrow (function-detail) preferred,
            # fall back to process-level PG union when function detail unknown.
            fn_pgs = list(fn.related_policy_group_ids) or list(proc.related_policy_group_ids)
            lines.extend(_yaml_block([
                ("기능_ID", fn.id),
                ("기능명", fn.name),
                ("설명", fn.description),
                ("관련_정책_그룹", fn_pgs),
            ]))
            lines.append("")
            lines.extend(_meta_table([
                ("입력 정보", fn.input_info),
                ("세부 기능 구성", fn.details),
                ("출력 정보", fn.output_info),
                ("처리 흐름", fn.processing_flow),
                ("실패/예외 케이스", fn.failure_cases),
            ]))
            lines.append("")

            for pg_id in fn_pgs:
                referenced_ids.add(pg_id)
                pg = ents.policy_groups.get(pg_id)
                lines.append(f"#### Policy Group: {pg_id}")
                lines.append("")
                if pg is None:
                    lines.append("_(정책 그룹 정의 누락)_")
                    lines.append("")
                    continue
                lines.extend(_yaml_block([
                    ("정책_ID", pg.id),
                    ("정책명", pg.name),
                    ("설명", pg.description),
                ]))
                lines.append("")
                items = [
                    pi for pi in ents.policy_items.values()
                    if pi.policy_group_id == pg_id
                ]
                if items:
                    lines.append("| Policy Item ID | 정책 항목명 | 정책 항목 |")
                    lines.append("| --- | --- | --- |")
                    for pi in items:
                        referenced_ids.add(pi.id)
                        content = _summarize(pi.content, 300)
                        lines.append(f"| `{pi.id}` | {pi.name} | {content} |")
                else:
                    lines.append("_(정책 항목 미정)_")
                lines.append("")

    # ---- 관련 상태 전이 (이 UC와 묶인) ----
    related_transitions = [tr for tr in ents.transitions if tr.usecase_id == uc.id]
    if related_transitions:
        lines.append("## 관련 상태 전이")
        lines.append("")
        lines.append("| 현재 상태 | 이벤트 | 다음 상태 | 처리 |")
        lines.append("|---|---|---|---|")
        for tr in related_transitions:
            referenced_ids.add(tr.from_state)
            referenced_ids.add(tr.to_state)
            cur_name = ents.states[tr.from_state].name if tr.from_state in ents.states else ""
            nxt_name = ents.states[tr.to_state].name if tr.to_state in ents.states else ""
            cur = f"`{tr.from_state}`" + (f" ({cur_name})" if cur_name else "")
            nxt = f"`{tr.to_state}`" + (f" ({nxt_name})" if nxt_name else "")
            handling = _summarize(tr.handling, 200)
            lines.append(f"| {cur} | {tr.event} | {nxt} | {handling} |")
        lines.append("")

    if not proc_chain:
        # UC defined but no processes — surface for AI consumers so they don't
        # silently treat the empty file as "no work needed".
        lines.append("> 이 유즈케이스는 정책서 본문에 프로세스가 정의되지 않았습니다. "
                     "entities.yaml 및 mapping.csv 참조.")
        lines.append("")

    # ---- cross-refs footer ----
    lines.append("---")
    lines.append("")
    lines.append("## Cross-refs (this UC)")
    lines.append("")
    lines.append("- 정의된 ID: " + ", ".join(f"`{i}`" for i in sorted(referenced_ids)))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# mapping.csv
# ---------------------------------------------------------------------------

def build_mapping_rows(ents: Entities) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for uc in ents.usecases.values():
        for proc_id in uc.related_processes:
            proc = ents.processes.get(proc_id)
            if not proc:
                rows.append({
                    "usecase_id": uc.id, "usecase_name": uc.name,
                    "process_id": proc_id, "process_name": "",
                    "function_id": "", "function_name": "", "function_actor": "",
                    "policy_group_id": "", "policy_group_name": "",
                    "policy_item_id": "", "policy_item_name": "",
                })
                continue
            fn_ids = proc.related_function_ids or [""]
            pg_ids = proc.related_policy_group_ids or [""]
            for fn_id in fn_ids:
                fn = ents.functions.get(fn_id) if fn_id else None
                actor_ref = ",".join(fn.actor_ids) if fn else ""
                for pg_id in pg_ids:
                    pg = ents.policy_groups.get(pg_id) if pg_id else None
                    items = [pi for pi in ents.policy_items.values() if pi.policy_group_id == pg_id] if pg_id else []
                    if not items:
                        rows.append({
                            "usecase_id": uc.id, "usecase_name": uc.name,
                            "process_id": proc.id, "process_name": proc.name,
                            "function_id": fn_id, "function_name": (fn.name if fn else ""),
                            "function_actor": actor_ref,
                            "policy_group_id": pg_id, "policy_group_name": (pg.name if pg else ""),
                            "policy_item_id": "", "policy_item_name": "",
                        })
                    for pi in items:
                        rows.append({
                            "usecase_id": uc.id, "usecase_name": uc.name,
                            "process_id": proc.id, "process_name": proc.name,
                            "function_id": fn_id, "function_name": (fn.name if fn else ""),
                            "function_actor": actor_ref,
                            "policy_group_id": pg_id, "policy_group_name": (pg.name if pg else ""),
                            "policy_item_id": pi.id, "policy_item_name": pi.name,
                        })
    return rows


def write_mapping_csv(rows: list[dict[str, str]], path: Path) -> None:
    cols = [
        "usecase_id", "usecase_name",
        "process_id", "process_name",
        "function_id", "function_name", "function_actor",
        "policy_group_id", "policy_group_name",
        "policy_item_id", "policy_item_name",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


# ---------------------------------------------------------------------------
# warnings.md
# ---------------------------------------------------------------------------

def build_warnings_md(w: dict[str, list[str]],
                      diagrams: list[Diagram] | None = None) -> str:
    lines = ["# warnings.md — 자동 검증 리포트", ""]
    diagram_note_count = sum(len(d.notes) for d in (diagrams or []))
    total = sum(len(v) for v in w.values()) + diagram_note_count
    lines.append(f"총 {total}건의 경고가 검출되었습니다." if total else "검출된 경고가 없습니다. ✅")
    lines.append("")

    sections = [
        ("broken_refs", "Broken cross-refs (참조된 ID가 정의되지 않음)"),
        ("orphan_entities", "Orphan entities (정의되었지만 어디서도 참조되지 않음)"),
        ("n_n_inconsistent", "N:N 양방향 불일치"),
        ("id_format_violations", "ID 형식 위반 (알려진 접두사 외)"),
        ("suspected_missing_policies", "누락 의심 정책"),
        ("silent_failure_suspect", "Silent failure 의심 (입력 신호 vs 산출물 비율)"),
        ("unknown_id_prefixes", "Unknown ID prefix (PREFIX_TO_TYPE 미등록)"),
    ]
    for key, title in sections:
        items = w.get(key, [])
        lines.append(f"## {title} ({len(items)}건)")
        lines.append("")
        if not items:
            lines.append("_없음_")
        else:
            for it in items:
                lines.append(f"- {it}")
        lines.append("")

    # diagrams
    lines.append(f"## Diagrams (다이어그램 추출 검증) ({diagram_note_count}건)")
    lines.append("")
    if not diagrams:
        lines.append("_입력 HTML에 다이어그램이 없습니다._")
    else:
        for i, d in enumerate(diagrams, 1):
            lines.append(f"### Diagram {i} — {d.type} (`{d.section}`)")
            lines.append("")
            if d.notes:
                for n in d.notes:
                    lines.append(f"- {n}")
            else:
                lines.append("- _경고 없음_")
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# README.md (recipient-facing usage guide)
# ---------------------------------------------------------------------------

def build_readme_md(ents: Entities) -> str:
    """A short, recipient-facing guide for design/dev teams who receive this
    artifact set. Explains what each file is, when to use it, and the known
    conversion characteristics so they don't get tripped up by them."""
    topic = ents.meta.topic or "(주제 미상)"
    version = ents.meta.version or "(버전 미상)"
    stats = (
        f"액터 {len(ents.actors)} · 유즈케이스 {len(ents.usecases)} · "
        f"상태 {len(ents.states)} · 상태 전이 {len(ents.transitions)} · "
        f"프로세스 {len(ents.processes)} · 기능 {len(ents.functions)} · "
        f"정책 그룹 {len(ents.policy_groups)} · 정책 항목 {len(ents.policy_items)} · "
        f"용어 {len(ents.terms)}"
    )
    body = f"""# 산출물 활용 가이드 — {topic} ({version})

이 폴더는 NC 정책서 HTML을 AI 에이전트 친화 포맷으로 자동 변환한 결과입니다.
LLM 호출 없는 결정적 변환이므로, 같은 입력은 항상 같은 산출물을 생성합니다.

**통계**: {stats}

---

## 산출물 구성

| 파일 | 용도 | 권장 활용 시점 |
|---|---|---|
| `00_INDEX.md` | 진입 가이드 · ID hierarchy 트리 · 다이어그램 3종 mermaid | **가장 먼저** — 전체 그림과 라우팅 |
| `usecase_<UC>.md` × N | UC 1개당 1파일. Process > Function > Policy Group > Policy Item 4단 구조 | AI 목업 input, 화면/컴포넌트 단위 설계 |
| `entities.yaml` | 모든 엔티티 + 양방향 cross_refs + hierarchy (영문 키, 평탄 구조) | 머신 처리, 스크립트 자동화 |
| `mapping.csv` | UC × PR × FN × PG × PI 평탄 N:N 매트릭스 | Excel pivot, 영향도 분석 |
| `warnings.md` | 자동 검증 결과 + 다이어그램 추출 주의사항 | 신뢰도 평가 |
| `diagrams/*.svg` | UC / State / BPMN 원본 SVG fallback | 다이어그램 시각 검토 |

---

## 활용 시나리오

### 1. AI 코드/목업 생성 input
Claude Code · Cursor · Copilot 등에 `usecase_<UC>.md` 를 컨텍스트로 넣으면 그 UC의 모든 Process / Function / Policy를 한 파일에서 grep · Read 가능합니다.

### 2. ID 추적
폴더 전체 grep으로 ID 1개를 추적:
```bash
grep -r "PR-MBR-CS-001-01" .
```

### 3. Excel pivot
`mapping.csv`를 Excel/Sheets로 import 후 pivot table로 UC ↔ PR ↔ FN ↔ PG ↔ PI의 N:N 영향도 분석.

### 4. 스크립트 자동화
`entities.yaml`을 Python yaml로 로드해 cross_refs 활용한 자동 검증·문서 생성.

---

## ID 체계

```
UC (Use Case)        US-{{domain}}-{{area}}-{{nnn}}
 └ PR (Process)      PR-{{domain}}-{{area}}-{{nnn}}-{{nn}}
    └ FN (Function)  FN-{{domain}}-{{category}}-{{nnn}}
       └ PG (Policy Group)   PG-{{domain}}-{{topic}}-{{nnn}}
          └ PI (Policy Item) POL-{{domain}}-{{topic}}-{{nnn}}-{{nn}}
```

- `entities.yaml#hierarchy` — UC → PR → FN 트리
- `entities.yaml#cross_refs` — 양방향 매핑 (function_to_processes, process_to_functions, process_to_policy_groups, policy_group_to_items, usecase_to_processes)

---

## 알려진 변환 특성 (사전 안내)

원본 HTML의 작성 방식상 다음 특성을 알고 활용하면 됩니다:

- **PR ↔ FN 매핑은 광역(union)으로 surface**: 원본 HTML의 "5장 가. 기능 목록" 표와 "4장 다. 프로세스 상세" 셀 두 곳에 PR-FN 매핑이 있고 두 곳이 다를 수 있습니다. 변환기는 데이터 보존을 위해 두 source를 union 처리합니다. **좁은 매핑만 필요하면** 원본 HTML "5장 가. 기능 목록"의 PR-단위 표를 참조하세요.

- **상태 전이의 UC 매핑이 부재할 수 있음**: 원본 상태 전이표에 UC ID 컬럼이 없으면 `entities.yaml#transitions[].usecase_id`가 빈 값으로 남습니다. UC 단위 추적이 필요하면 `entities.yaml#transitions[]` 전체를 보고 매핑하세요.

- **UC 다이어그램 보강 노드**: SVG 좌표 휴리스틱이 못 잡은 UC는 entities 기반으로 mermaid 본문에 보강됩니다. 정확한 actor↔UC 관계는 `warnings.md`의 `entities_based_supplement` 노트와 `diagrams/uc_*.svg` 원본을 함께 확인.

- **BPMN 누락 task**: 원본 BPMN에 그려져 있지 않으나 `entities.processes`에 정의된 PR은 `warnings.md`의 `bpmn_task_missing_from_mermaid` 노트에 명시됩니다. mapping.csv · entities.yaml로 보완.

- **PolicyItem 본문 "- " prefix · "세부 기능 구성" 공백 join**: 원본 HTML 텍스트가 거의 그대로 들어옵니다 (의미 손실 없음, 가독성만 cosmetic).

- **LLM 호출 없음**: 100% stdlib 기반 결정적 변환. 같은 HTML 입력은 항상 같은 산출물을 생성합니다.

---

## 빠른 시작

```bash
# UC 1개 컨텍스트로 AI 에이전트에게 전달
cat usecase_US-MBR-CS-001.md

# ID 전체 추적
grep -rn "FN-MBR-COM-001" .

# entities.yaml 스크립트 처리
python -c "
import yaml
d = yaml.safe_load(open('entities.yaml'))
for fn in d['functions']:
    print(fn['id'], fn['name'], fn['related_policy_group_ids'])
"

# mapping.csv 처리
python -c "
import csv
rows = list(csv.DictReader(open('mapping.csv')))
print(f'{{len(rows)}} mapping rows')
"
```

---

## 피드백

활용 중 발견한 문제·개선 제안은 변환기 담당자에게 전달해주세요.
"""
    return body


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _slugify(s: str) -> str:
    # Pull the topic and version into a folder-safe slug.
    s = s.replace(" ", "_")
    s = re.sub(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ_.-]", "", s)
    return s or "policy"


def build_dev_format(input_html: Path, output_dir: Path | None = None) -> Path:
    html_text = input_html.read_text(encoding="utf-8")
    tables, policy_detail_items, title_h1 = parse_html(input_html)
    ents = extract_entities(tables, policy_detail_items, input_html, title_h1=title_h1)
    cross = normalize_cross_refs(ents)
    hierarchy = build_hierarchy(ents)
    warnings = collect_warnings(ents, cross)
    diagrams = build_diagrams(html_text, ents)
    # P0+P2: 입력 신호 대비 산출물이 비정상으로 적으면 warnings.md에 명시.
    # diagrams 빌드 결과를 함께 봐야 하므로 base warnings 뒤에 호출.
    append_silent_failure_warnings(
        warnings, ents, tables, policy_detail_items, html_text, diagrams
    )

    # decide output dir
    if output_dir is None:
        # infer topic+version from filename: NC_{topic}_정책서_{label}_v{ver}.html
        stem = input_html.stem
        slug_base = _slugify(stem)
        output_dir = input_html.parent.parent / "output" / "exports" / slug_base
        # if the input file lives in output/, this places exports under output/exports/
        if "output" in [p.name for p in input_html.parents]:
            base = next(p for p in input_html.parents if p.name == "output")
            output_dir = base / "exports" / slug_base
    output_dir.mkdir(parents=True, exist_ok=True)

    # save SVG fallback files (diagrams/<type>_<n>.svg) and stamp Diagram.svg_file
    if diagrams:
        diagrams_dir = output_dir / "diagrams"
        diagrams_dir.mkdir(exist_ok=True)
        type_counter: dict[str, int] = {}
        for d in diagrams:
            type_counter[d.type] = type_counter.get(d.type, 0) + 1
            filename = f"{d.type}_{type_counter[d.type]}.svg"
            (diagrams_dir / filename).write_text(d.svg_xml, encoding="utf-8")
            d.svg_file = f"diagrams/{filename}"

    # write artifacts
    (output_dir / "README.md").write_text(build_readme_md(ents), encoding="utf-8")
    (output_dir / "00_INDEX.md").write_text(build_index_md(ents, hierarchy, diagrams), encoding="utf-8")
    for uc in ents.usecases.values():
        (output_dir / f"usecase_{uc.id}.md").write_text(build_usecase_md(uc, ents), encoding="utf-8")
    write_mapping_csv(build_mapping_rows(ents), output_dir / "mapping.csv")
    (output_dir / "entities.yaml").write_text(serialize_yaml(ents, cross, hierarchy, diagrams), encoding="utf-8")
    (output_dir / "warnings.md").write_text(build_warnings_md(warnings, diagrams), encoding="utf-8")

    return output_dir


# ---------------------------------------------------------------------------
# Diagram extraction (SVG → Mermaid heuristic)
# ---------------------------------------------------------------------------
#
# ncstudio renders 3 diagram types as inline SVG inside <div class="diagram-wrap">:
#   (1) UC diagram        — class="uc", "actor-text", "conn" + sysbox
#   (2) State transition  — class="state|state-major|state-alert", "flow|flow-dash"
#   (3) BPMN flow chart   — class="pool|pool-head", "task|task-key|task-warn",
#                           "gateway", "event-start|event-end-*", "flow"
#
# Mermaid text is preferred for Claude Code context (≈100× token compression,
# direct graph semantics, grep-friendly). SVG is kept as fallback in diagrams/.

@dataclass
class SvgNode:
    kind: str = ""               # 'rect' | 'ellipse' | 'circle' | 'polygon' | 'line' | 'path' | 'text'
    cls: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    points: list[tuple[float, float]] = field(default_factory=list)
    path_d: str = ""
    text: str = ""


@dataclass
class SvgGraph:
    nodes: list[SvgNode] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0


@dataclass
class RawDiagram:
    section: str = ""            # nearest preceding heading (e.g. "다. 유즈케이스 다이어그램")
    svg_xml: str = ""            # full <svg>...</svg>


@dataclass
class Diagram:
    type: str = "unknown"        # 'uc' | 'state' | 'bpmn' | 'unknown'
    section: str = ""
    mermaid: str = ""
    svg_xml: str = ""
    svg_file: str = ""           # relative path of saved svg fallback
    referenced_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _f(v: str | None) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_points(s: str) -> list[tuple[float, float]]:
    """Parse SVG points attribute: 'x1,y1 x2,y2 ...' or 'x1 y1 x2 y2 ...'."""
    parts = re.split(r"[\s,]+", (s or "").strip())
    nums: list[float] = []
    for p in parts:
        if not p:
            continue
        try:
            nums.append(float(p))
        except ValueError:
            continue
    return list(zip(nums[0::2], nums[1::2]))


def _parse_path_endpoints(d: str) -> list[tuple[float, float]]:
    """Extract first and last (x, y) from an SVG path 'd' attribute.

    Supports M, L, C, Q, T, S and lowercase variants — but we treat all
    numbers as absolute coordinates for endpoint matching. This is enough
    for ncstudio diagrams (no relative paths in observed samples).
    """
    if not d:
        return []
    tokens = re.findall(r"[MLCQTSAHVZmlcqtsahvz]|-?\d+(?:\.\d+)?", d)
    coords: list[tuple[float, float]] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            i += 1
            continue
        try:
            x = float(t)
            y = float(tokens[i + 1])
            coords.append((x, y))
            i += 2
        except (ValueError, IndexError):
            i += 1
    if not coords:
        return []
    return [coords[0], coords[-1]]


class SvgParser(HTMLParser):
    """Lightweight SVG walker — collects shape and text nodes with coords/classes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[SvgNode] = []
        self.width = 0.0
        self.height = 0.0
        self._current_text: SvgNode | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "svg":
            self.width = _f(a.get("width"))
            self.height = _f(a.get("height"))
            return
        if tag in ("rect", "ellipse", "circle", "polygon", "line", "path"):
            node = SvgNode(kind=tag, cls=cls)
            if tag == "rect":
                node.x = _f(a.get("x"))
                node.y = _f(a.get("y"))
                node.w = _f(a.get("width"))
                node.h = _f(a.get("height"))
            elif tag == "ellipse":
                node.cx = _f(a.get("cx"))
                node.cy = _f(a.get("cy"))
                node.rx = _f(a.get("rx"))
                node.ry = _f(a.get("ry"))
            elif tag == "circle":
                node.cx = _f(a.get("cx"))
                node.cy = _f(a.get("cy"))
                node.rx = _f(a.get("r"))
                node.ry = _f(a.get("r"))
            elif tag == "polygon":
                node.points = _parse_points(a.get("points") or "")
            elif tag == "line":
                node.points = [(_f(a.get("x1")), _f(a.get("y1"))),
                               (_f(a.get("x2")), _f(a.get("y2")))]
            elif tag == "path":
                node.path_d = a.get("d") or ""
                node.points = _parse_path_endpoints(node.path_d)
            self.nodes.append(node)
            return
        if tag == "text":
            node = SvgNode(kind="text", cls=cls)
            node.x = _f(a.get("x"))
            node.y = _f(a.get("y"))
            self.nodes.append(node)
            self._current_text = node
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "text" and self._current_text is not None:
            self._current_text.text = "".join(self._buf).strip()
            self._current_text = None
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._current_text is not None:
            self._buf.append(data)


_DIAGRAM_WRAP_RE = re.compile(
    # Allow multi-class (e.g. class="diagram-wrap state-transition-diagram") by
    # matching `diagram-wrap` as a whole word inside the class attribute.
    # 정책서마다 추가 변형 클래스(state-transition-diagram, bpmn-diagram 등)를
    # 함께 쓰는 경우가 있어 단일 클래스 매칭만 하면 다이어그램 추출이 0건이 된다.
    r'<div [^>]*class="[^"]*\bdiagram-wrap\b[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_HEADING_RE = re.compile(r'<h([34])[^>]*>([^<]+)</h\1>', re.DOTALL)


def extract_diagrams(html_text: str) -> list[RawDiagram]:
    """Find each <div class="diagram-wrap"> region and its nearest preceding H3/H4."""
    results: list[RawDiagram] = []
    for m in _DIAGRAM_WRAP_RE.finditer(html_text):
        block = m.group(1)
        prefix = html_text[: m.start()]
        headings = list(_HEADING_RE.finditer(prefix))
        section = headings[-1].group(2).strip() if headings else ""
        section = re.sub(r"\s+", " ", section)
        svg_match = re.search(r"<svg\b.*?</svg>", block, re.DOTALL | re.IGNORECASE)
        svg_xml = svg_match.group(0) if svg_match else ""
        if svg_xml:
            results.append(RawDiagram(section=section, svg_xml=svg_xml))
    return results


def classify_diagram(section: str, graph: SvgGraph) -> str:
    s = section or ""
    if "유즈케이스 다이어그램" in s or "유스케이스 다이어그램" in s:
        return "uc"
    if "상태 전이" in s or "상태전이" in s:
        return "state"
    if "업무 흐름도" in s or "BPMN" in s.upper():
        return "bpmn"
    # fallback by class signatures
    classes = {c for n in graph.nodes for c in n.cls}
    if "pool" in classes or "pool-head" in classes:
        return "bpmn"
    if any(c in classes for c in ("state", "state-major", "state-alert")):
        return "state"
    if "uc" in classes:
        return "uc"
    return "unknown"


def _nearest_node(
    point: tuple[float, float],
    candidates: list[tuple[Any, float, float]],
    max_dist: float = 80.0,
) -> Any:
    """Return key of the nearest candidate within max_dist, else None."""
    px, py = point
    best, best_d = None, max_dist
    for key, x, y in candidates:
        d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        if d < best_d:
            best, best_d = key, d
    return best


def _slugify_id(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_가-힣]", "_", s or "")
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "X"


def svg_to_mermaid_state(graph: SvgGraph, ents: Entities) -> tuple[str, list[str], list[str]]:
    """Convert a state-transition SVG to a Mermaid stateDiagram-v2."""
    nodes = graph.nodes
    texts = [n for n in nodes if n.kind == "text"]
    state_rects = [
        n for n in nodes
        if n.kind == "rect"
        and any(c in ("state", "state-major", "state-alert") for c in n.cls)
    ]
    states: list[tuple[str, str, float, float]] = []  # (code, name, cx, cy)
    for r in state_rects:
        cx, cy = r.x + r.w / 2, r.y + r.h / 2
        inside = [
            t for t in texts
            if r.x - 5 <= t.x <= r.x + r.w + 5
            and r.y - 5 <= t.y <= r.y + r.h + 15
        ]
        name = next((t.text for t in inside if "state-text" in t.cls), "")
        code = next((t.text for t in inside if "state-sub" in t.cls), "")
        if not (name or code):
            continue
        states.append((code or name, name or code, cx, cy))
    candidates = [(code, cx, cy) for code, _, cx, cy in states]
    flows = [
        n for n in nodes
        if n.kind in ("line", "path")
        and any(c.startswith("flow") for c in n.cls)
    ]
    flow_labels = [t for t in texts if "flow-label" in t.cls]
    edges: list[tuple[str, str, str, bool]] = []
    for f in flows:
        if len(f.points) < 2:
            continue
        start, end = f.points[0], f.points[-1]
        a = _nearest_node(start, candidates, max_dist=120)
        b = _nearest_node(end, candidates, max_dist=120)
        if a is None or b is None or a == b:
            continue
        # collect labels close to the path's bounding box midpoint
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        label_parts = [
            lab.text for lab in flow_labels
            if abs(lab.x - mx) < 80 and abs(lab.y - my) < 40 and lab.text
        ]
        label = " ".join(label_parts).strip()
        dashed = "flow-dash" in f.cls
        edges.append((a, b, label, dashed))
    # emit
    out = ["stateDiagram-v2"]
    referenced: list[str] = []
    for code, name, _, _ in states:
        if code == name:
            out.append(f"    {code}")
        else:
            out.append(f"    {code} : {name}")
        referenced.append(code)
    seen_edges: set[tuple[str, str, str]] = set()
    for a, b, label, dashed in edges:
        suffix = ""
        if dashed and label:
            suffix = f" : {label} (오류 흐름)"
        elif dashed:
            suffix = " : (오류 흐름)"
        elif label:
            suffix = f" : {label}"
        key = (a, b, suffix)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        out.append(f"    {a} --> {b}{suffix}")
    notes: list[str] = []
    unmapped = [c for c in referenced if c not in ents.states]
    if unmapped:
        notes.append(f"unmapped_state_codes: {sorted(set(unmapped))}")
    return "\n".join(out), sorted(set(referenced)), notes


def _bpmn_id(raw: str) -> str:
    """Make a mermaid-safe node id from a raw ID like 'PR-MBR-CS-001-01' → 'PR_MBR_CS_001_01'."""
    return re.sub(r"[^A-Za-z0-9]", "_", raw).strip("_") or "N"


def _bpmn_shape(kind: str, label: str) -> str:
    safe = label.replace('"', "'")
    if kind in ("start", "end"):
        return f'(("{safe}"))'
    if kind == "gw":
        return "{" + safe + "}"
    # task — use [label]; embed <br/> as-is (mermaid renders it)
    return f"[{safe}]"


def svg_to_mermaid_bpmn(graph: SvgGraph, ents: Entities) -> tuple[str, list[str], list[str]]:
    """Convert a BPMN-style swimlane SVG to Mermaid flowchart with subgraph per pool."""
    nodes = graph.nodes
    texts = [n for n in nodes if n.kind == "text"]
    pool_heads = [n for n in nodes if n.kind == "rect" and "pool-head" in n.cls]
    pools = [n for n in nodes if n.kind == "rect" and "pool" in n.cls and "pool-head" not in n.cls]
    # Build pool_data: (uc_id, title, host_x, host_y, host_w, host_h)
    pool_data: list[tuple[str, str, float, float, float, float]] = []
    for ph in pool_heads:
        host = next((p for p in pools if abs(p.y - ph.y) < 5), None) or ph
        title_t = next(
            (t for t in texts
             if "pool-title" in t.cls
             and ph.x <= t.x <= ph.x + ph.w
             and ph.y <= t.y <= ph.y + ph.h),
            None,
        )
        sub_t = next(
            (t for t in texts
             if "pool-sub" in t.cls
             and ph.x <= t.x <= ph.x + ph.w
             and ph.y <= t.y <= ph.y + ph.h),
            None,
        )
        title = title_t.text if title_t else ""
        uc_id = (sub_t.text or "").strip() if sub_t else ""
        if not uc_id:
            uc_id = f"POOL_{len(pool_data) + 1}"
        pool_data.append((uc_id, title, host.x, host.y, host.w, host.h))

    def owner_of(cx: float, cy: float) -> str | None:
        for uc_id, _, px, py, pw, ph in pool_data:
            if px <= cx <= px + pw and py <= cy <= py + ph:
                return uc_id
        return None

    # Tasks
    task_rects = [
        n for n in nodes
        if n.kind == "rect"
        and any(c in ("task", "task-key", "task-warn") for c in n.cls)
    ]
    tasks: list[tuple[str, str, str, float, float, str | None]] = []  # (mid, label, pr_id, cx, cy, owner)
    for r in task_rects:
        cx, cy = r.x + r.w / 2, r.y + r.h / 2
        inside = [
            t for t in texts
            if r.x - 5 <= t.x <= r.x + r.w + 5
            and r.y - 5 <= t.y <= r.y + r.h + 5
        ]
        name = next((t.text for t in inside if "task-text" in t.cls), "")
        pr_id = next(
            (t.text for t in inside
             if "task-id" in t.cls and t.text.startswith("PR-")),
            "",
        )
        label = f"{name}<br/>{pr_id}" if pr_id else (name or "task")
        mid = _bpmn_id(pr_id) if pr_id else _bpmn_id(f"T_{len(tasks) + 1}")
        tasks.append((mid, label, pr_id, cx, cy, owner_of(cx, cy)))
    # Gateways
    gateway_polys = [n for n in nodes if n.kind == "polygon" and "gateway" in n.cls]
    gateways: list[tuple[str, str, float, float, str | None]] = []  # (mid, label, cx, cy, owner)
    for g in gateway_polys:
        if not g.points:
            continue
        xs = [p[0] for p in g.points]
        ys = [p[1] for p in g.points]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        label = ""
        for t in texts:
            if "label" not in t.cls:
                continue
            if abs(t.x - cx) < 50 and 0 < t.y - cy < 70 and t.text:
                if t.text in ("예", "아니오") or t.text == "X":
                    continue
                if "?" in t.text or "가능" in t.text or "진행" in t.text:
                    label = t.text
                    break
        mid = _bpmn_id(f"G_{len(gateways) + 1}")
        gateways.append((mid, label or "분기", cx, cy, owner_of(cx, cy)))
    # Start / End events
    starts: list[tuple[str, float, float, str | None]] = []
    ends: list[tuple[str, float, float, str | None]] = []
    for c in [n for n in nodes if n.kind == "circle" and "event-start" in n.cls]:
        starts.append((_bpmn_id(f"S_{len(starts) + 1}"), c.cx, c.cy, owner_of(c.cx, c.cy)))
    for c in [n for n in nodes if n.kind == "circle" and "event-end-outer" in n.cls]:
        ends.append((_bpmn_id(f"E_{len(ends) + 1}"), c.cx, c.cy, owner_of(c.cx, c.cy)))
    # Candidate list for flow matching
    candidates: list[tuple[str, str, str, float, float, str | None]] = []  # (mid, label, kind, cx, cy, owner)
    for mid, label, _, cx, cy, owner in tasks:
        candidates.append((mid, label, "task", cx, cy, owner))
    for mid, label, cx, cy, owner in gateways:
        candidates.append((mid, label, "gw", cx, cy, owner))
    for mid, cx, cy, owner in starts:
        candidates.append((mid, "시작", "start", cx, cy, owner))
    for mid, cx, cy, owner in ends:
        candidates.append((mid, "종료", "end", cx, cy, owner))
    # Flows
    flow_paths = [
        n for n in nodes
        if n.kind in ("path", "line") and "flow" in n.cls
    ]
    label_texts = [t for t in texts if "label" in t.cls and t.text]
    edges: list[tuple[str, str, str, str | None]] = []  # (from, to, label, owner)
    for fp in flow_paths:
        pts = fp.points
        if len(pts) < 2:
            continue
        start, end = pts[0], pts[-1]
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        owner = owner_of(mx, my)
        same_pool = [(mid, cx, cy) for (mid, _, _, cx, cy, o) in candidates if o == owner]
        if not same_pool:
            continue
        a = _nearest_node(start, same_pool, max_dist=70)
        b = _nearest_node(end, same_pool, max_dist=70)
        if a is None or b is None or a == b:
            continue
        # find label near start (예/아니오 typically near gateway)
        label = ""
        for lt in label_texts:
            if lt.text in ("X",):
                continue
            if abs(lt.x - start[0]) < 50 and abs(lt.y - start[1]) < 40:
                if lt.text in ("예", "아니오") or "아니오" in lt.text:
                    label = lt.text
                    break
        edges.append((a, b, label, owner))
    # Emit mermaid
    out = ["flowchart LR"]
    used: set[str] = set()
    for uc_id, title, _, _, _, _ in pool_data:
        safe_title = title.replace('"', "'")
        out.append(f'    subgraph {uc_id}["{uc_id}: {safe_title}"]')
        out.append("    direction LR")
        for mid, label, kind, _, _, owner in candidates:
            if owner != uc_id or mid in used:
                continue
            used.add(mid)
            out.append(f"        {mid}{_bpmn_shape(kind, label)}")
        out.append("    end")
    # nodes without an owner pool — emit at top level
    for mid, label, kind, _, _, owner in candidates:
        if owner is None and mid not in used:
            used.add(mid)
            out.append(f"    {mid}{_bpmn_shape(kind, label)}")
    seen_edges: set[tuple[str, str, str]] = set()
    for a, b, label, _ in edges:
        key = (a, b, label)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        arrow = f" -->|{label}| " if label else " --> "
        out.append(f"    {a}{arrow}{b}")
    # references and notes
    referenced = sorted({pr for _, _, pr, _, _, _ in tasks if pr})
    referenced += sorted({uc for uc, _, _, _, _, _ in pool_data if uc.startswith("US-")})
    notes: list[str] = []
    unmapped_pr = [p for p in referenced if p.startswith("PR-") and p not in ents.processes]
    if unmapped_pr:
        notes.append(f"unmapped_processes: {sorted(set(unmapped_pr))}")
    unmapped_uc = [u for u in referenced if u.startswith("US-") and u not in ents.usecases]
    if unmapped_uc:
        notes.append(f"unmapped_usecases: {sorted(set(unmapped_uc))}")
    # PR IDs defined in entities for this BPMN's UC scope but absent from the
    # mermaid output. Two possible causes — both surfaced for AI consumers:
    #   (a) SVG had a task rect but coord-based matching failed (rare),
    #   (b) policy author omitted the task from the BPMN drawing entirely.
    # Either way, the AI should fall back to entities.yaml/mapping.csv for
    # the missing PR's relationships.
    mermaid_pr_ids = {pr for _, _, pr, _, _, _ in tasks if pr}
    bpmn_uc_scope = {uc for uc, _, _, _, _, _ in pool_data if uc.startswith("US-")}
    scope_pr_ids = {
        proc.id for proc in ents.processes.values()
        if proc.usecase_id in bpmn_uc_scope
    }
    missing_from_mermaid = sorted(scope_pr_ids - mermaid_pr_ids)
    if missing_from_mermaid:
        notes.append(
            f"bpmn_task_missing_from_mermaid: {missing_from_mermaid} "
            "(entities.processes에는 정의됐으나 원본 BPMN SVG에 task 노드로 그려져 있지 않음 — "
            "mapping.csv / SVG fallback / entities.yaml 참조)"
        )
    return "\n".join(out), referenced, notes


def svg_to_mermaid_uc(graph: SvgGraph, ents: Entities) -> tuple[str, list[str], list[str]]:
    """Convert a UC diagram SVG to Mermaid graph (best-effort).

    UC diagrams encode actor↔UC and UC↔UC relations as <line class="conn"/>.
    Coordinate-based matching has lower accuracy than state/BPMN — flagged
    in notes so reviewers know to validate manually.

    Node IDs:
      - mapped UCs use their canonical ID (e.g. US_MBR_CS_001) for grep continuity
      - unmapped UCs and actors use index-based fallback IDs (UC_1, ACT_1, …)
        to avoid Hangul-slug collisions that would collapse multiple nodes.
    """
    nodes = graph.nodes
    texts = [n for n in nodes if n.kind == "text"]
    # UC nodes
    uc_ellipses = [n for n in nodes if n.kind == "ellipse" and "uc" in n.cls]
    uc_id_by_name = {uc.name: uc.id for uc in ents.usecases.values()}
    ucs: list[tuple[str, str, float, float]] = []  # (mid, name, cx, cy)
    referenced: list[str] = []
    uc_fallback_seq = 0
    for e in uc_ellipses:
        name = next(
            (t.text for t in texts
             if "uc-text" in t.cls
             and abs(t.x - e.cx) < 35 and abs(t.y - e.cy) < 18),
            "",
        )
        if not name:
            continue
        mapped = uc_id_by_name.get(name, "")
        if mapped:
            referenced.append(mapped)
            mid = _bpmn_id(mapped)
        else:
            uc_fallback_seq += 1
            mid = f"UC_{uc_fallback_seq}"
        ucs.append((mid, name, e.cx, e.cy))
    # Actor nodes — index-based ID, label retains original (often Hangul) name
    actor_texts = [t for t in texts if "actor-text" in t.cls]
    actors: list[tuple[str, str, float, float]] = []
    for idx, t in enumerate(actor_texts, 1):
        if not t.text:
            continue
        mid = f"ACT_{idx}"
        actors.append((mid, t.text, t.x, t.y))
    # Edges
    conn_lines = [
        n for n in nodes
        if n.kind in ("line", "path") and "conn" in n.cls
    ]
    cand_uc = [(mid, cx, cy) for mid, _, cx, cy in ucs]
    cand_actor = [(mid, x, y) for mid, _, x, y in actors]
    all_cand = cand_uc + cand_actor
    include_edges: list[tuple[str, str]] = []
    actor_edges: list[tuple[str, str]] = []
    for line in conn_lines:
        if len(line.points) < 2:
            continue
        a = _nearest_node(line.points[0], all_cand, max_dist=140)
        b = _nearest_node(line.points[1], all_cand, max_dist=140)
        if a is None or b is None or a == b:
            continue
        a_is_uc = any(uc_id == a for uc_id, _, _ in cand_uc)
        b_is_uc = any(uc_id == b for uc_id, _, _ in cand_uc)
        if a_is_uc and b_is_uc:
            include_edges.append((a, b))
        else:
            actor_edges.append((a, b))
    # Emit
    out = ["graph LR"]
    safe_added: set[str] = set()
    for mid, name, _, _ in actors:
        if mid in safe_added:
            continue
        safe_added.add(mid)
        safe = name.replace('"', "'")
        out.append(f'    {mid}(["{safe}"])')
    for mid, name, _, _ in ucs:
        if mid in safe_added:
            continue
        safe_added.add(mid)
        safe = name.replace('"', "'")
        out.append(f'    {mid}(("{safe}"))')
    seen_ae: set[tuple[str, str]] = set()
    for a, b in actor_edges:
        key = tuple(sorted((a, b)))
        if key in seen_ae:
            continue
        seen_ae.add(key)
        out.append(f"    {a} --- {b}")
    seen_ie: set[tuple[str, str]] = set()
    for a, b in include_edges:
        if (a, b) in seen_ie:
            continue
        seen_ie.add((a, b))
        out.append(f"    {a} -.include.-> {b}")
    # Augment: UCs defined in entities but absent from the SVG-extracted set
    # are appended as isolated nodes so AI consumers see the full UC inventory.
    # Edges are not synthesized (intent unknown without source diagram); SVG
    # fallback and entities.yaml carry the relations.
    defined_uc_ids = set(ents.usecases.keys())
    supplemented: list[str] = []
    for uid in sorted(defined_uc_ids - set(referenced)):
        uc = ents.usecases.get(uid)
        if uc is None:
            continue
        mid = _bpmn_id(uid)
        if mid in safe_added:
            continue
        safe_added.add(mid)
        safe = (uc.name or uid).replace('"', "'")
        out.append(f'    {mid}(("{safe}"))')
        referenced.append(uid)
        supplemented.append(uid)

    notes = ["uc_diagram_low_confidence: 좌표 휴리스틱 추출 (정확도 보장 X). 의미 검증 필요."]
    unmapped_uc_names = [name for _, name, _, _ in ucs if name not in uc_id_by_name]
    if unmapped_uc_names:
        notes.append(f"unmapped_uc_names: {sorted(set(unmapped_uc_names))}")
    if supplemented:
        notes.append(
            f"entities_based_supplement: {supplemented} "
            "(원본 SVG에 그려져 있지 않아 entities.usecases 기반으로 보완. "
            "actor↔UC edge는 의미 추측을 피해 생략 — entities.yaml/SVG fallback 참조)"
        )
    return "\n".join(out), sorted(set(referenced)), notes


def build_diagrams(html_text: str, ents: Entities) -> list[Diagram]:
    """Top-level: extract → classify → convert each diagram in the HTML."""
    raw_list = extract_diagrams(html_text)
    out: list[Diagram] = []
    for raw in raw_list:
        parser = SvgParser()
        parser.feed(raw.svg_xml)
        graph = SvgGraph(nodes=parser.nodes, width=parser.width, height=parser.height)
        dtype = classify_diagram(raw.section, graph)
        if dtype == "state":
            mermaid, refs, notes = svg_to_mermaid_state(graph, ents)
        elif dtype == "bpmn":
            mermaid, refs, notes = svg_to_mermaid_bpmn(graph, ents)
        elif dtype == "uc":
            mermaid, refs, notes = svg_to_mermaid_uc(graph, ents)
        else:
            mermaid = ""
            refs = []
            notes = [f"unknown_diagram_type: section={raw.section!r}"]
        out.append(Diagram(
            type=dtype,
            section=raw.section,
            mermaid=mermaid,
            svg_xml=raw.svg_xml,
            referenced_ids=refs,
            notes=notes,
        ))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dev_format",
        description="Convert policy HTML to dev/design team friendly artifacts (no LLM).",
    )
    parser.add_argument("--input", required=True, help="Path to policy HTML file")
    parser.add_argument("--output", default=None, help="Output directory (default: output/exports/<slug>/)")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = Path(args.output).expanduser().resolve() if args.output else None
    result_dir = build_dev_format(input_path, output_dir)
    print(f"OK: wrote artifacts to {result_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
