"""镜头表：脚本与视频引擎之间的中间层。

三件事决定了它长这样。

**一、不绑任何 API。** 文本和剧本走 GLM 5.3 的浏览器多账号，不是 API。所以
镜头表必须能从一段纯文本导进来（:func:`parse_text`），而不是只能由某个
SDK 生成。换视频供应商、换编剧模型，这一层都不用动。

**二、镜头长度可变。** 早期那套「3 张关键帧、2 段各 5 秒」是照着旧模型定的，
现在单段支持 4–12 秒，硬凑成 5 秒只会让画面节奏迁就工具。这里按旁白的实际
长度定时长，不够就报出来。

**三、角色一致性只能在图片层解决。** 首尾帧与参考图在 API 上互斥，不能既锁
首尾帧又传角色参考图。唯一可靠的办法是把上一镜的尾帧图当作下一镜的首帧图，
让角色形象顺着链条传下去 —— 所以这里有 ``first_frame_from_previous``，
而不是每镜各自描述一遍角色然后祈祷它们长得像。
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

from aniflow.factpack import AuditReport, FactPack, Issue, Severity, gate

# Agnes 单段视频的硬边界
MIN_SECONDS = 4
MAX_SECONDS = 12

# 中文旁白的舒适语速。偏慢取值：宁可画面等旁白，也别让旁白追画面。
CHARS_PER_SECOND = 4.5


class FrameSpec(BaseModel):
    """一张关键帧要画成什么样。"""

    composition: str
    subject_state: str
    environment: str

    def image_prompt(self, character: str, style: str) -> str:
        """拼成可直接投给图片模型的提示词。

        角色描述由镜头表统一注入，不写在每个镜头里 —— 抄来抄去必然抄漏，
        而角色一致性是这个项目最贵的东西。
        """
        seen: set[str] = set()
        out: list[str] = []
        for part in (style, character, self.subject_state,
                     self.composition, self.environment):
            for piece in (x.strip() for x in part.split(",")):
                key = piece.lower()
                if piece and key not in seen:
                    seen.add(key)
                    out.append(piece)
        return ", ".join(out)


class Shot(BaseModel):
    shot_id: str
    seconds: int = Field(ge=MIN_SECONDS, le=MAX_SECONDS)
    narration: str = ""
    motion: str
    camera: str = ""
    first_frame: FrameSpec | None = None
    first_frame_from_previous: bool = False
    last_frame: FrameSpec | None = None
    # 空镜或换主角的镜头（比如插一个狗的对比镜头）必须能把主角描述换掉，
    # 否则会生成猫狗合体。给空字符串表示这一镜不要任何角色描述。
    character_override: str | None = None

    @model_validator(mode="after")
    def _frame_source_is_unambiguous(self) -> Shot:
        if self.first_frame_from_previous and self.first_frame is not None:
            raise ValueError(
                f"{self.shot_id}: 既说了承接上一镜尾帧，又自己描述了首帧，二选一"
            )
        if not self.first_frame_from_previous and self.first_frame is None:
            raise ValueError(f"{self.shot_id}: 没有首帧，也没说承接上一镜")
        return self

    @property
    def spoken_seconds(self) -> float:
        """旁白念完需要多久。标点不计入。"""
        body = re.sub(r"[\s，。、；：！？—…「」『』（）\"'·,.!?;:()]", "", self.narration)
        return round(len(body) / CHARS_PER_SECOND, 1)


class ShotList(BaseModel):
    episode_id: str
    title: str
    character: str
    style: str = "handmade needle-felt stop-motion miniature, visible wool fiber texture, soft studio light"
    aspect_ratio: str = "9:16"
    shots: list[Shot] = Field(min_length=1)

    @property
    def total_seconds(self) -> int:
        return sum(s.seconds for s in self.shots)

    @property
    def narration(self) -> str:
        return "\n".join(s.narration for s in self.shots if s.narration.strip())

    def resolved_first_frame(self, index: int) -> FrameSpec | None:
        """顺着承接链往回找这一镜真正的首帧。"""
        shot = self.shots[index]
        if not shot.first_frame_from_previous:
            return shot.first_frame
        if index == 0:
            return None
        prev = self.shots[index - 1]
        return prev.last_frame or self.resolved_first_frame(index - 1)


def validate_shotlist(sl: ShotList) -> list[Issue]:
    issues: list[Issue] = []

    seen: set[str] = set()
    for shot in sl.shots:
        if shot.shot_id in seen:
            issues.append(Issue(severity=Severity.BLOCK, code="L001",
                                message="镜头编号重复", evidence=shot.shot_id))
        seen.add(shot.shot_id)

    if sl.shots[0].first_frame_from_previous:
        issues.append(Issue(severity=Severity.BLOCK, code="L002",
                            message="第一个镜头没有上一镜可以承接",
                            evidence=sl.shots[0].shot_id))

    for i, shot in enumerate(sl.shots):
        # 旁白塞不进镜头时长 —— 音画对不上是发布级缺陷，不是小毛病
        need = shot.spoken_seconds
        if need > shot.seconds:
            issues.append(Issue(
                severity=Severity.BLOCK, code="L003",
                message=f"旁白念完要 {need} 秒，镜头只有 {shot.seconds} 秒",
                evidence=shot.shot_id,
            ))
        elif need and shot.seconds - need > 4:
            issues.append(Issue(
                severity=Severity.WARN, code="L004",
                message=f"旁白 {need} 秒，镜头 {shot.seconds} 秒，留白偏多",
                evidence=shot.shot_id,
            ))

        if shot.first_frame_from_previous and i > 0:
            if sl.shots[i - 1].last_frame is None:
                issues.append(Issue(
                    severity=Severity.BLOCK, code="L005",
                    message="承接的上一镜没有尾帧，角色一致性链会在这里断开",
                    evidence=shot.shot_id,
                ))

        if shot.last_frame is None and i < len(sl.shots) - 1:
            if sl.shots[i + 1].first_frame_from_previous:
                continue  # 上面 L005 已经报过
            issues.append(Issue(
                severity=Severity.WARN, code="L006",
                message="没有尾帧，这一镜的落点交给模型自由发挥",
                evidence=shot.shot_id,
            ))

    return issues


def check_episode(sl: ShotList, pack: FactPack) -> AuditReport:
    """镜头表 + 事实包一起过。旁白里的数字同样要有出处。"""
    report = gate(pack, sl.narration)
    report.issues = validate_shotlist(sl) + report.issues
    return report


# ── 从外部文本导入 ──────────────────────────────────────────────────
#
# 剧本在浏览器里写（GLM 5.3 多账号），复制出来就是一段纯文本。这里接住它。

_HEAD = re.compile(r"^#+\s*(?:镜头|shot)\s*([\w.-]+)\s*[|｜]\s*(\d+)\s*秒", re.I)
_FIELDS = {
    "旁白": "narration", "narration": "narration",
    "运动": "motion", "motion": "motion",
    "运镜": "camera", "camera": "camera",
    "首帧": "first", "last_frame": "last",
    "尾帧": "last",
}
_FRAME_KEYS = {"构图": "composition", "角色": "subject_state", "环境": "environment"}


def _frame_from(raw: str) -> FrameSpec | None:
    if not raw.strip():
        return None
    if raw.strip() in ("承接上一镜", "同上", "承接"):
        return None
    parts = {v: "" for v in _FRAME_KEYS.values()}
    matched = False
    for chunk in re.split(r"[;；]", raw):
        pieces = re.split(r"[=:：]", chunk, maxsplit=1)
        if len(pieces) == 2:
            key, val = pieces
            slot = _FRAME_KEYS.get(key.strip())
            if slot:
                parts[slot] = val.strip()
                matched = True
    if not matched:
        # 没有分字段就整句当角色状态，别硬要求编剧记格式
        return FrameSpec(composition="", subject_state=raw.strip(), environment="")
    return FrameSpec(**parts)


def parse_text(text: str, *, episode_id: str, title: str, character: str,
               style: str | None = None) -> ShotList:
    """把浏览器里写好的分镜文本解析成镜头表。

    容错优先：编剧不该为了迁就解析器去背格式。认不出来的行直接忽略。
    """
    shots: list[Shot] = []
    cur: dict | None = None

    def flush() -> None:
        if not cur:
            return
        first_raw = cur.pop("first", "")
        inherit = first_raw.strip() in ("承接上一镜", "同上", "承接")
        shots.append(Shot(
            shot_id=cur["shot_id"], seconds=cur["seconds"],
            narration=cur.get("narration", "").strip(),
            motion=cur.get("motion", "").strip(),
            camera=cur.get("camera", "").strip(),
            first_frame=None if inherit else _frame_from(first_raw),
            first_frame_from_previous=inherit,
            last_frame=_frame_from(cur.pop("last", "")),
        ))

    for line in text.splitlines():
        head = _HEAD.match(line.strip())
        if head:
            flush()
            cur = {"shot_id": head.group(1), "seconds": int(head.group(2))}
            continue
        if cur is None or not line.strip():
            continue
        m = re.match(r"^\s*([^:：]{1,8})\s*[:：]\s*(.+)$", line)
        if m:
            slot = _FIELDS.get(m.group(1).strip())
            if slot:
                cur[slot] = m.group(2).strip()
    flush()

    if not shots:
        raise ValueError("没解析出任何镜头。每个镜头要有一行像「## 镜头 1 | 6秒」的标题。")

    kwargs = dict(episode_id=episode_id, title=title, character=character, shots=shots)
    if style:
        kwargs["style"] = style
    return ShotList(**kwargs)


# ── 导出成可以直接粘的东西 ──────────────────────────────────────────


def render_worksheet(sl: ShotList) -> str:
    """打印成人可以照着往网页界面里粘的工单。"""
    out = [
        f"《{sl.title}》  {sl.episode_id}",
        f"共 {len(sl.shots)} 个镜头，{sl.total_seconds} 秒，画幅 {sl.aspect_ratio}",
        "=" * 64,
        "每个镜头：先按首帧/尾帧提示词生成两张图，再用这两张图做首尾帧生成视频。",
        "",
    ]
    for i, shot in enumerate(sl.shots):
        out.append(f"── 镜头 {shot.shot_id}  {shot.seconds} 秒 " + "─" * 30)
        if shot.narration:
            out.append(f"  旁白（{shot.spoken_seconds} 秒）：{shot.narration}")
        who = sl.character if shot.character_override is None else shot.character_override
        first = sl.resolved_first_frame(i)
        if shot.first_frame_from_previous:
            out.append("  首帧图：直接用上一镜的尾帧图，不要重新生成")
            out.append("          （角色一致性靠这条链维持，重新生成就断了）")
        elif first:
            out.append(f"  首帧提示词：{first.image_prompt(who, sl.style)}")
        if shot.last_frame:
            out.append(f"  尾帧提示词：{shot.last_frame.image_prompt(who, sl.style)}")
        else:
            out.append("  尾帧：不锁，交给模型")
        cam = f"，{shot.camera}" if shot.camera else ""
        out.append(f"  视频提示词：{shot.motion}{cam}")
        out.append("")
    return "\n".join(out)
