"""事实防火墙。

原则：搞笑可以离谱，事实不能瞎说；生成成功 != 可以发布。

这一层存在的理由，用一个真实例子说明最快。2010 年 Science 那篇猫舔水的论文
实测舌尖最大速度是 78 cm/s，《纽约时报》和 ABC 报道时写成了「1 米/秒」；论文
测得每次饮水 0.14 毫升，中文科普普遍传成「0.1 毫升」。两处都不是有人在撒谎，
只是转述时四舍五入了一下，然后这个数字就永远这样传下去了。

所以这里真正做事的不是那些结构校验，而是 :func:`audit_script`
里的量词比对：脚本里每一个「数字 + 计量单位」都必须能在 Fact Pack 里找到出处，
找不到就拦。AI 编剧最擅长的就是顺口写出一个听起来很精确的数字。
"""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Severity(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"


class Source(BaseModel):
    title: str
    url: str
    publisher: str
    year: int
    peer_reviewed: bool = False

    @property
    def domain(self) -> str:
        host = (urlparse(self.url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host


class Issue(BaseModel):
    severity: Severity
    code: str
    message: str
    evidence: str = ""

    def __str__(self) -> str:
        tail = f"  ← {self.evidence}" if self.evidence else ""
        return f"[{self.severity.value}] {self.code} {self.message}{tail}"


class FactPack(BaseModel):
    """一条正式科普内容的事实契约。"""

    episode_id: str
    core_claim: str
    locked_facts: list[str] = Field(min_length=1)
    source_a: Source
    source_b: Source
    qualifiers: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW

    @property
    def factual_text(self) -> str:
        """允许出现在脚本里的数字，必须能在这段文本中找到出处。"""
        return "\n".join([self.core_claim, *self.locked_facts, *self.qualifiers])


# ── 量词抽取 ────────────────────────────────────────────────────────
#
# 只认「数字 + 计量单位」。不认光秃秃的数字，否则「一只猫」「第二天」会把
# 报告刷满噪声，人就不看了，这道闸门也就白设了。

_UNITS = [
    "毫秒", "秒", "分钟", "小时", "天", "周", "个月", "年",
    "次", "倍", "成",
    "纳米", "微米", "毫米", "厘米", "公里", "千米", "米",
    "毫升", "升", "毫克", "克", "千克", "公斤", "吨",
    "摄氏度", "度", "赫兹", "%", "％",
]
# 长单位优先，否则「厘米」会被「米」先吃掉
_UNIT_RE = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# 同一物理量的不同单位归为一族。脚本写「1 米每秒」而 Fact Pack 记的是
# 「78 厘米每秒」时，光说「没有出处」帮不到编剧 —— 得把同类的正确数值摆出来。
_UNIT_FAMILY = {
    **{u: "长度" for u in ("纳米", "微米", "毫米", "厘米", "米", "公里", "千米")},
    **{u: "体积" for u in ("毫升", "升")},
    **{u: "质量" for u in ("毫克", "克", "千克", "公斤", "吨")},
    **{u: "时间" for u in ("毫秒", "秒", "分钟", "小时", "天", "周", "个月", "年")},
    **{u: "温度" for u in ("度", "摄氏度")},
}


def _cn_to_int(token: str) -> str | None:
    """把 100 以内的中文数字转成阿拉伯数字。脚本里会写「每秒四次」而不是「每秒4次」。"""
    if not token:
        return None
    if token == "十":
        return "10"
    if "十" in token:
        head, _, tail = token.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        if head and head not in _CN_DIGITS:
            return None
        if tail and tail not in _CN_DIGITS:
            return None
        return str(tens * 10 + ones)
    if all(c in _CN_DIGITS for c in token) and len(token) == 1:
        return str(_CN_DIGITS[token])
    return None


_NUM = r"\d+(?:\.\d+)?"
_CN_NUM = r"[零〇一两二三四五六七八九十]+"
# 「3 到 4 次」「三四次」这类范围，两个端点都要能对上出处
_PATTERN = re.compile(
    rf"({_NUM}|{_CN_NUM})\s*(?:[-~～]|到|至)?\s*({_NUM}|{_CN_NUM})?\s*({_UNIT_RE})"
)


def _normalise(value: str) -> str | None:
    if re.fullmatch(_NUM, value):
        # 4 与 4.0 视为同一个数
        return str(float(value)).rstrip("0").rstrip(".") or "0"
    return _cn_to_int(value)


def extract_measurements(text: str) -> set[tuple[str, str]]:
    """抽出文本里所有 (数值, 单位) 对，中文数字已归一为阿拉伯数字。"""
    found: set[tuple[str, str]] = set()
    for first, second, unit in _PATTERN.findall(text):
        unit = "%" if unit in ("%", "％") else unit
        for raw in (first, second):
            if not raw:
                continue
            norm = _normalise(raw)
            if norm is not None:
                found.add((norm, unit))
    return found


# ── 校验 ────────────────────────────────────────────────────────────


def validate_pack(pack: FactPack) -> list[Issue]:
    """检查 Fact Pack 自身是否成立，与脚本无关。"""
    issues: list[Issue] = []
    a, b = pack.source_a, pack.source_b

    if a.domain and a.domain == b.domain:
        issues.append(Issue(
            severity=Severity.BLOCK, code="P001",
            message="两个信源是同一个网站，不算互相独立",
            evidence=a.domain,
        ))
    elif a.publisher.strip().lower() == b.publisher.strip().lower():
        issues.append(Issue(
            severity=Severity.BLOCK, code="P002",
            message="两个信源是同一个发布方，不算互相独立",
            evidence=a.publisher,
        ))

    if not (a.peer_reviewed or b.peer_reviewed):
        sev = Severity.BLOCK if pack.risk_level is RiskLevel.HIGH else Severity.WARN
        issues.append(Issue(
            severity=sev, code="P003",
            message="没有任何一个信源是同行评议的",
        ))

    if pack.risk_level is RiskLevel.HIGH and not pack.qualifiers:
        issues.append(Issue(
            severity=Severity.BLOCK, code="P004",
            message="高风险选题必须写明适用范围与限制条件",
        ))

    for fact in pack.locked_facts:
        if not extract_measurements(fact) and len(fact.strip()) < 8:
            issues.append(Issue(
                severity=Severity.WARN, code="P005",
                message="锁定事实太短，起不到约束作用",
                evidence=fact,
            ))

    return issues


class AuditReport(BaseModel):
    episode_id: str
    issues: list[Issue] = Field(default_factory=list)

    @property
    def blockers(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.BLOCK]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is Severity.WARN]

    @property
    def publishable(self) -> bool:
        """生成成功不等于可以发布。这里说了才算。"""
        return not self.blockers

    def render(self) -> str:
        head = "可以发布" if self.publishable else "禁止发布"
        lines = [f"【{head}】{self.episode_id}"]
        if not self.issues:
            lines.append("  没有发现问题。")
        for issue in self.blockers + self.warnings:
            lines.append(f"  {issue}")
        return "\n".join(lines)


def audit_script(pack: FactPack, script: str) -> AuditReport:
    """把脚本放到 Fact Pack 前面过一遍。"""
    issues: list[Issue] = []

    for phrase in pack.forbidden_claims:
        needle = phrase.strip()
        if needle and needle in script:
            issues.append(Issue(
                severity=Severity.BLOCK, code="S001",
                message="出现了明令禁止的说法",
                evidence=needle,
            ))

    allowed = extract_measurements(pack.factual_text)
    for value, unit in sorted(extract_measurements(script)):
        if (value, unit) in allowed:
            continue
        # 同单位优先；没有就退到同一物理量，好歹告诉编剧正确的数是多少
        same_unit = sorted(f"{v}{u}" for v, u in allowed if u == unit)
        family = _UNIT_FAMILY.get(unit)
        same_family = sorted(
            f"{v}{u}" for v, u in allowed
            if u != unit and family and _UNIT_FAMILY.get(u) == family
        )
        if same_unit:
            hint = f"，Fact Pack 里只有 {'/'.join(same_unit)}"
        elif same_family:
            hint = f"，Fact Pack 里同类只有 {'/'.join(same_family)}"
        else:
            hint = ""
        issues.append(Issue(
            severity=Severity.BLOCK, code="S002",
            message=f"脚本里的「{value}{unit}」在 Fact Pack 里没有出处{hint}",
            evidence=f"{value}{unit}",
        ))

    if pack.risk_level is RiskLevel.HIGH:
        if not any(q.strip() and q.strip() in script for q in pack.qualifiers):
            issues.append(Issue(
                severity=Severity.BLOCK, code="S003",
                message="高风险选题的脚本里必须带上适用范围说明",
            ))

    return AuditReport(episode_id=pack.episode_id, issues=issues)


def gate(pack: FactPack, script: str) -> AuditReport:
    """发布前的唯一入口：Fact Pack 自身 + 脚本，一起过。"""
    report = audit_script(pack, script)
    report.issues = validate_pack(pack) + report.issues
    return report
