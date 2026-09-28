from __future__ import annotations

import pytest

from aniflow.factpack import (
    FactPack,
    RiskLevel,
    Severity,
    Source,
    audit_script,
    extract_measurements,
    gate,
    validate_pack,
)

PAPER = Source(
    title="How Cats Lap: Water Uptake by Felis catus",
    url="https://www.science.org/doi/10.1126/science.1195421",
    publisher="Science (AAAS)",
    year=2010,
    peer_reviewed=True,
)
REUTERS = Source(
    title="Cat's delicate lapping defies gravity: study",
    url="https://www.reuters.com/article/us-cats-tongue/",
    publisher="Reuters",
    year=2010,
)


def make_pack(**over) -> FactPack:
    base = dict(
        episode_id="MYCL-001",
        core_claim="猫不是用舌头把水舀起来，而是靠惯性把水柱拉进嘴里。",
        locked_facts=[
            "家猫舔水频率为每秒 3.5 次（论文实测均值，误差 0.4 次）。",
            "舌尖最大速度为 78 厘米每秒。",
            "每舔一次摄入约 0.14 毫升液体。",
        ],
        source_a=PAPER,
        source_b=REUTERS,
        qualifiers=["数据来自 10 只成年家猫的实测均值，个体存在差异。"],
        forbidden_claims=["猫用舌头把水舀进嘴里", "猫靠吸力喝水"],
        risk_level=RiskLevel.LOW,
    )
    base.update(over)
    return FactPack(**base)


# ── 量词抽取 ────────────────────────────────────────────────────────


def test_extracts_arabic_and_chinese_numbers_alike():
    """脚本会写「每秒四次」，Fact Pack 会写「3.5 次」，两边必须能比。"""
    assert ("4", "次") in extract_measurements("每秒四次")
    assert ("4", "次") in extract_measurements("每秒 4 次")
    assert ("3.5", "次") in extract_measurements("每秒 3.5 次")


def test_longer_unit_wins_over_shorter_one():
    """「78 厘米」不能被读成「78 米」，否则校验形同虚设。"""
    got = extract_measurements("舌尖速度 78 厘米每秒")
    assert ("78", "厘米") in got
    assert ("78", "米") not in got


def test_both_ends_of_a_range_are_captured():
    got = extract_measurements("大约每秒三到四次")
    assert ("3", "次") in got and ("4", "次") in got


def test_bare_counters_are_not_treated_as_claims():
    """「一只猫」「两个碗」不是数据。全抓会把报告淹掉，人就不看了。"""
    assert extract_measurements("一只猫走过来，喝了两口水") == set()


def test_percent_signs_are_normalised():
    assert ("30", "%") in extract_measurements("提升 30％")
    assert ("30", "%") in extract_measurements("提升 30%")


def test_four_and_four_point_zero_are_the_same_number():
    assert extract_measurements("4.0 秒") == extract_measurements("4 秒")


# ── Fact Pack 自身 ──────────────────────────────────────────────────


def test_two_sources_from_the_same_site_are_not_independent():
    twin = PAPER.model_copy(update={"url": "https://www.science.org/content/article/cats"})
    issues = validate_pack(make_pack(source_b=twin))
    assert any(i.code == "P001" and i.severity is Severity.BLOCK for i in issues)


def test_mit_news_reporting_on_mit_research_is_flagged():
    """最容易蒙混过关的一种：机构自己报道自己的成果，看着像第二个信源。"""
    mit_paper = PAPER.model_copy(update={"publisher": "MIT"})
    mit_news = Source(title="The surprising physics of cats' drinking",
                      url="https://news.mit.edu/2010/cat-lapping-1112",
                      publisher="MIT", year=2010)
    issues = validate_pack(make_pack(source_a=mit_paper, source_b=mit_news))
    assert any(i.code == "P002" and i.severity is Severity.BLOCK for i in issues)


def test_no_peer_review_warns_but_does_not_block_low_risk():
    plain = PAPER.model_copy(update={"peer_reviewed": False})
    issues = validate_pack(make_pack(source_a=plain))
    p003 = [i for i in issues if i.code == "P003"]
    assert p003 and p003[0].severity is Severity.WARN


def test_no_peer_review_blocks_high_risk():
    plain = PAPER.model_copy(update={"peer_reviewed": False})
    issues = validate_pack(make_pack(source_a=plain, risk_level=RiskLevel.HIGH))
    p003 = [i for i in issues if i.code == "P003"]
    assert p003 and p003[0].severity is Severity.BLOCK


def test_high_risk_without_scope_limits_is_blocked():
    issues = validate_pack(make_pack(risk_level=RiskLevel.HIGH, qualifiers=[]))
    assert any(i.code == "P004" and i.severity is Severity.BLOCK for i in issues)


def test_a_pack_needs_at_least_one_locked_fact():
    with pytest.raises(Exception):
        make_pack(locked_facts=[])


# ── 脚本审查 ────────────────────────────────────────────────────────


def test_forbidden_claim_blocks_publication():
    report = audit_script(make_pack(), "雪所长说：其实猫用舌头把水舀进嘴里，就这么简单。")
    assert not report.publishable
    assert any(i.code == "S001" for i in report.blockers)


def test_the_new_york_times_rounding_error_is_caught():
    """真实案例：论文写 78 厘米每秒，NYT 和 ABC 都报道成「1 米每秒」。

    这个数字后来被无数二手科普沿用。脚本一旦写 1 米每秒就必须拦下来。
    """
    report = audit_script(make_pack(), "它的舌头能达到 1 米每秒。")
    assert not report.publishable
    blocker = next(i for i in report.blockers if i.code == "S002")
    assert "1米" in blocker.evidence
    assert "78" in blocker.message  # 要告诉编剧正确的数是多少


def test_the_chinese_popsci_drift_is_caught():
    """中文科普普遍写 0.1 毫升，论文实测是 0.14 毫升。"""
    report = audit_script(make_pack(), "每舔一次大概喝进去 0.1 毫升。")
    assert any(i.code == "S002" and "0.1毫升" in i.evidence for i in report.blockers)


def test_a_number_written_in_chinese_is_checked_too():
    """「每秒四次」是流传最广的说法，论文实测是 3.5 次。"""
    report = audit_script(make_pack(), "猫每秒能舔四次。")
    assert not report.publishable
    assert any(i.code == "S002" for i in report.blockers)


def test_a_faithful_script_passes():
    script = (
        "雪所长：猫喝水不是舀，是骗。舌尖碰一下水面就往回抽，"
        "水被惯性带成一根柱子，赶在重力把它拽回去之前，嘴一合。"
        "每秒 3.5 次，舌尖 78 厘米每秒，一次 0.14 毫升。"
        "别说，竟然喵有此理！"
    )
    report = audit_script(make_pack(), script)
    assert report.publishable, report.render()


def test_a_different_unit_of_the_same_quantity_still_gets_a_reference():
    """包里记的是厘米、脚本写公里时，也该把包里那条长度摆出来给编剧看。"""
    blocker = next(i for i in audit_script(make_pack(), "这事发生在 3 公里外。").blockers
                   if i.code == "S002")
    assert "3公里" in blocker.evidence
    assert "78厘米" in blocker.message


def test_an_unrelated_unit_gets_no_made_up_reference():
    """包里没有任何百分比，就不该硬塞一个数字当参考。"""
    blocker = next(i for i in audit_script(make_pack(), "效率提升了 30%。").blockers
                   if i.code == "S002")
    assert "30%" in blocker.evidence
    assert "只有" not in blocker.message


def test_high_risk_script_must_carry_the_scope_limit():
    pack = make_pack(risk_level=RiskLevel.HIGH)
    bad = audit_script(pack, "每秒 3.5 次。")
    assert any(i.code == "S003" for i in bad.blockers)

    good = audit_script(pack, "每秒 3.5 次。数据来自 10 只成年家猫的实测均值，个体存在差异。")
    assert not any(i.code == "S003" for i in good.blockers)


# ── 总闸 ────────────────────────────────────────────────────────────


def test_gate_reports_pack_problems_and_script_problems_together():
    twin = PAPER.model_copy(update={"url": "https://www.science.org/news/cats"})
    report = gate(make_pack(source_b=twin), "猫靠吸力喝水。")
    codes = {i.code for i in report.blockers}
    assert "P001" in codes and "S001" in codes
    assert not report.publishable


def test_render_says_plainly_whether_it_can_ship():
    assert "禁止发布" in gate(make_pack(), "猫靠吸力喝水。").render()
    assert "可以发布" in gate(make_pack(), "舌尖 78 厘米每秒。").render()
