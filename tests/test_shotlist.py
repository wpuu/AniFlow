from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aniflow.factpack import FactPack, Severity
from aniflow.shotlist import (
    FrameSpec,
    Shot,
    ShotList,
    check_episode,
    parse_text,
    render_worksheet,
    validate_shotlist,
)

REPO = Path(__file__).resolve().parents[1]


def frame(state: str = "sitting") -> FrameSpec:
    return FrameSpec(composition="medium", subject_state=state, environment="kitchen")


def shot(shot_id="1", seconds=6, **over) -> Shot:
    base = dict(shot_id=shot_id, seconds=seconds, motion="slow blink",
                first_frame=frame(), last_frame=frame("head tilted"))
    base.update(over)
    return Shot(**base)


def make_list(shots=None, **over) -> ShotList:
    base = dict(episode_id="T-001", title="测试", character="felt cat",
                shots=shots or [shot()])
    base.update(over)
    return ShotList(**base)


# ── 单镜头约束 ──────────────────────────────────────────────────────


@pytest.mark.parametrize("seconds", [3, 13, 0])
def test_duration_outside_the_engine_limits_is_rejected(seconds):
    """4~12 秒是引擎的硬边界，不是建议值。"""
    with pytest.raises(ValidationError):
        shot(seconds=seconds)


def test_a_shot_must_say_where_its_first_frame_comes_from():
    with pytest.raises(ValidationError):
        Shot(shot_id="1", seconds=6, motion="x")


def test_a_shot_cannot_both_inherit_and_describe_its_first_frame():
    """两个来源同时给，就说不清该用哪张图了。"""
    with pytest.raises(ValidationError):
        Shot(shot_id="1", seconds=6, motion="x",
             first_frame=frame(), first_frame_from_previous=True)


def test_spoken_length_ignores_punctuation():
    a = shot(narration="猫喝水不是舀").spoken_seconds
    b = shot(narration="猫、喝、水，不是——舀！").spoken_seconds
    assert a == b


# ── 镜头表整体 ──────────────────────────────────────────────────────


def test_narration_longer_than_the_shot_is_a_blocker():
    """音画对不上是发布级缺陷。宁可现在拦，不要剪辑时才发现。"""
    long_line = "猫的舌头根本不伸进水里只有舌头背面碰一下水面然后高速往回抽水被惯性拽着跟上来"
    issues = validate_shotlist(make_list([shot(seconds=4, narration=long_line)]))
    assert any(i.code == "L003" and i.severity is Severity.BLOCK for i in issues)


def test_lots_of_dead_air_only_warns():
    issues = validate_shotlist(make_list([shot(seconds=12, narration="很短")]))
    codes = {(i.code, i.severity) for i in issues}
    assert ("L004", Severity.WARN) in codes


def test_the_first_shot_cannot_inherit_from_nothing():
    issues = validate_shotlist(make_list([
        shot("1", first_frame=None, first_frame_from_previous=True),
    ]))
    assert any(i.code == "L002" and i.severity is Severity.BLOCK for i in issues)


def test_inheriting_from_a_shot_with_no_last_frame_breaks_the_chain():
    """角色一致性全靠这条链。断了就是每镜各画各的，角色必然走形。"""
    issues = validate_shotlist(make_list([
        shot("1", last_frame=None),
        shot("2", first_frame=None, first_frame_from_previous=True),
    ]))
    assert any(i.code == "L005" and i.severity is Severity.BLOCK for i in issues)


def test_duplicate_shot_ids_are_blocked():
    issues = validate_shotlist(make_list([shot("1"), shot("1")]))
    assert any(i.code == "L001" for i in issues)


def test_the_inherited_frame_resolves_back_up_the_chain():
    sl = make_list([
        shot("1", last_frame=frame("looking down")),
        shot("2", first_frame=None, first_frame_from_previous=True, last_frame=None),
        shot("3", first_frame=None, first_frame_from_previous=True),
    ])
    assert sl.resolved_first_frame(1).subject_state == "looking down"
    # 第 2 镜没有尾帧，第 3 镜要继续往上找
    assert sl.resolved_first_frame(2).subject_state == "looking down"


def test_character_is_injected_once_not_copied_into_every_shot():
    """角色描述抄进每个镜头必然抄漏，那是这个项目最贵的一致性。"""
    sl = make_list()
    prompt = sl.shots[0].first_frame.image_prompt(sl.character, sl.style)
    assert "felt cat" in prompt and "sitting" in prompt


# ── 从浏览器里粘进来 ────────────────────────────────────────────────

SAMPLE = """
## 镜头 1 | 6秒
旁白：猫喝水不是舀。
首帧：构图=特写; 角色=舌尖伸向水面; 环境=陶瓷碗
尾帧：构图=特写; 角色=舌背碰到水面; 环境=水面出现凹陷
运动：舌头向下伸出并回卷
运镜：微微推近

## 镜头 2 | 5秒
旁白：水被惯性带上来。
首帧：承接上一镜
尾帧：构图=特写; 角色=水柱立起; 环境=同上
运动：水柱随舌头升起
"""


def test_a_script_pasted_from_the_browser_becomes_a_shot_list():
    """剧本在 GLM 5.3 的浏览器里写，复制出来就得能用，不能要求走 API。"""
    sl = parse_text(SAMPLE, episode_id="T-002", title="测试", character="felt cat")
    assert [s.shot_id for s in sl.shots] == ["1", "2"]
    assert sl.shots[0].seconds == 6
    assert sl.shots[0].first_frame.subject_state == "舌尖伸向水面"
    assert sl.shots[1].first_frame_from_previous is True
    assert sl.total_seconds == 11
    assert not [i for i in validate_shotlist(sl) if i.severity is Severity.BLOCK]


def test_unstructured_frame_text_is_accepted_as_is():
    """编剧不该为了迁就解析器去背格式。"""
    text = "## 镜头 1 | 5秒\n首帧：一只毛毡猫坐在碗边\n运动：眨眼\n"
    sl = parse_text(text, episode_id="T", title="t", character="c")
    assert sl.shots[0].first_frame.subject_state == "一只毛毡猫坐在碗边"


def test_lines_the_parser_does_not_understand_are_ignored():
    text = SAMPLE + "\n这里是编剧写给自己的备注，不该让解析炸掉。\n随便写点什么\n"
    assert len(parse_text(text, episode_id="T", title="t", character="c").shots) == 2


def test_text_with_no_shot_headers_fails_loudly():
    with pytest.raises(ValueError, match="镜头"):
        parse_text("就是一段普通的话", episode_id="T", title="t", character="c")


# ── 真实的第一集 ────────────────────────────────────────────────────


def load_episode() -> tuple[ShotList, FactPack]:
    sl = ShotList.model_validate_json(
        (REPO / "content/shotlists/MYCL-001-cat-lapping.json").read_text(encoding="utf-8"))
    raw = json.loads(
        (REPO / "content/factpacks/MYCL-001-cat-lapping.json").read_text(encoding="utf-8"))
    raw.pop("_notes", None)
    return sl, FactPack.model_validate(raw)


def test_the_real_first_episode_is_clean():
    """第一集必须能过自己的闸门，否则这两层就都是摆设。"""
    sl, pack = load_episode()
    report = check_episode(sl, pack)
    assert report.publishable, report.render()


def test_the_real_first_episode_stays_inside_the_engine_limits():
    sl, _ = load_episode()
    assert all(4 <= s.seconds <= 12 for s in sl.shots)
    assert 30 <= sl.total_seconds <= 90


def test_the_real_first_episode_keeps_its_character_chain():
    """能承接的地方都承接了，角色才不会一镜一个样。"""
    sl, _ = load_episode()
    inherited = [s for s in sl.shots if s.first_frame_from_previous]
    assert len(inherited) >= 4


def test_the_worksheet_tells_a_human_exactly_what_to_paste():
    sl, _ = load_episode()
    sheet = render_worksheet(sl)
    assert "直接用上一镜的尾帧图" in sheet
    assert "needle-felted American Shorthair" in sheet
    assert sheet.count("── 镜头") == len(sl.shots)


def test_a_cutaway_can_replace_the_main_character():
    """对比镜头里出现的是狗。不让换就会生成猫狗合体。"""
    sl = make_list([shot("1", character_override="felt golden retriever")])
    sheet = render_worksheet(sl)
    assert "felt golden retriever" in sheet
    assert "felt cat" not in sheet


def test_an_empty_override_drops_the_character_entirely():
    """纯空镜不需要任何角色描述。"""
    sl = make_list([shot("1", character_override="")])
    assert "felt cat" not in render_worksheet(sl)


def test_the_prompt_does_not_repeat_itself():
    """风格和角色都写了 wool fiber texture，重复只会稀释权重。"""
    f = FrameSpec(composition="medium", subject_state="sitting", environment="kitchen")
    prompt = f.image_prompt("felt cat, visible wool fiber texture",
                            "needle-felt miniature, visible wool fiber texture")
    assert prompt.count("visible wool fiber texture") == 1


def test_the_dog_cutaway_in_the_real_episode_is_not_a_cat():
    sl, _ = load_episode()
    dog = next(s for s in sl.shots if "dog" in s.motion)
    assert dog.character_override and "retriever" in dog.character_override
