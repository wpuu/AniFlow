"""Legacy multi-key video queue observation, NOT proof of quota isolation.

A mixture of accepted and queue-full responses is compatible with both global
and per-account capacity: a shared global queue may have only one free slot.
Do not infer 9x throughput or business economics from this signal.
This helper can generate real billable video tasks; the CLI is gated.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

QUEUE_FULL = "video_queue_full"
PROBE_PROMPT = (
    "Stop-motion needle-felt animation test. A small felted cat figure on a "
    "kitchen counter blinks once and tilts its head. Slow camera push-in."
)


@dataclass(slots=True)
class Attempt:
    account_label: str
    accepted: bool
    video_id: str | None = None
    code: str | None = None
    http_status: int | None = None
    detail: str | None = None

    @property
    def is_queue_full(self) -> bool:
        return self.code == QUEUE_FULL or self.http_status == 503


@dataclass(slots=True)
class Round:
    index: int
    started_at: float
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def accepted(self) -> list[Attempt]:
        return [a for a in self.attempts if a.accepted]

    @property
    def rejected(self) -> list[Attempt]:
        return [a for a in self.attempts if not a.accepted]

    @property
    def is_mixed(self) -> bool:
        """A mixed observation, not evidence of per-account quota isolation."""
        return bool(self.accepted) and any(a.is_queue_full for a in self.rejected)


# --- verdicts -------------------------------------------------------------

PER_ACCOUNT = "per_account"  # Retained for historical compatibility; never inferred.
MIXED_OBSERVED = "mixed_observed_inconclusive"
INCONCLUSIVE_SATURATED = "inconclusive_saturated"
CAPACITY_AVAILABLE = "capacity_available"
NO_KEYS = "no_keys"


def decide(rounds: list[Round]) -> str:
    if not rounds:
        return NO_KEYS
    if any(r.is_mixed for r in rounds):
        return MIXED_OBSERVED
    if any(r.accepted for r in rounds):
        return CAPACITY_AVAILABLE
    return INCONCLUSIVE_SATURATED


VERDICT_TEXT = {
    MIXED_OBSERVED: (
        "观察到部分入队、部分队列满——【无法判断】限额模型",
        "共享队列剩余少量名额时也会出现混合结果；不能证明按账户隔离，" +
        "更不能据此推断 9 倍产能。应以实际可交付视频/时长/成本衡量。",
    ),
    CAPACITY_AVAILABLE: (
        "队列当前有空位（未能区分模型）  ⚠️",
        "所有账户都成功了，说明此刻不缺容量，但无法区分是按账户还是全平台共享。\n" +
        "  → 不应为了辨别队列模型而反复付费创建视频。",
    ),
    INCONCLUSIVE_SATURATED: (
        "全部被拒，无法区分  ⚠️",
        "所有账户同时被拒。可能是全平台共享队列满了，\n" +
        "  也可能是每个账户各自都满了 —— 这两种情况此刻长得一样。\n" +
        "  → 停止无上限重试；单镜头生产验收优先。",
    ),
    NO_KEYS: ("没有可用的 API Key  ❌", "请在 .env 里配置 AGNES_API_KEYS（英文逗号分隔）。"),
}


# --- probing --------------------------------------------------------------


async def _fire_one(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    label: str,
    model: str,
    seconds: int,
    aspect_ratio: str,
) -> Attempt:
    payload = {
        "model": model,
        "prompt": PROBE_PROMPT,
        "seconds": str(seconds),
        "mode": "text",  # no media needed -> no R2 required
        "size": "720P",
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }
    try:
        resp = await client.post(
            f"{base_url}/videos",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    except Exception as exc:  # noqa: BLE001
        return Attempt(label, False, detail=f"{type(exc).__name__}: {exc}")

    try:
        body = resp.json()
    except ValueError:
        return Attempt(label, False, http_status=resp.status_code, detail=resp.text[:160])

    if not isinstance(body, dict):
        return Attempt(label, False, http_status=resp.status_code, detail=str(body)[:160])

    video_id = body.get("video_id")
    if isinstance(video_id, str) and video_id:
        return Attempt(label, True, video_id=video_id, http_status=resp.status_code)

    return Attempt(
        label,
        False,
        code=body.get("code"),
        http_status=resp.status_code,
        detail=str(body.get("message") or "")[:160],
    )


async def run_round(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    keys: list[str],
    model: str,
    seconds: int,
    aspect_ratio: str,
    index: int,
) -> Round:
    """All keys fire at the same instant - simultaneity is the whole point."""
    rnd = Round(index=index, started_at=time.time())
    rnd.attempts = list(
        await asyncio.gather(
            *(
                _fire_one(
                    client,
                    base_url=base_url,
                    api_key=k,
                    label=f"account-{i + 1}",
                    model=model,
                    seconds=seconds,
                    aspect_ratio=aspect_ratio,
                )
                for i, k in enumerate(keys)
            )
        )
    )
    return rnd


# --- audio detection ------------------------------------------------------


def has_audio_track(path: Path) -> bool | None:
    """Return True/False only when the format permits a determination.

    ffprobe's *exit code* matters: a corrupt MP4 reports failure and empty
    stdout, which previously returned False instead of falling back to
    the bounded MP4 handler scan (or None if still undecidable).
    """
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            out = None
        if out is not None and out.returncode == 0:
            return any(line.strip() == "audio" for line in out.stdout.splitlines())

    # ffprobe unavailable/failed: scan *only* the first 2 MiB without reading
    # the full output video into memory. This is a heuristic, not a proof.
    try:
        with path.open("rb") as f:
            head = f.read(2_000_000)
    except OSError:
        return None

    found_video = False
    offset = 0
    while True:
        index = head.find(b"hdlr", offset)
        if index < 0:
            break
        # ISO BMFF HandlerReferenceBox: 'hdlr' (4 bytes), version+flags (4),
        # pre_defined (4), then handler_type (4).
        handler_type = head[index + 12 : index + 16]
        if handler_type == b"soun":
            return True
        if handler_type == b"vide":
            found_video = True
        offset = index + 4
    return False if found_video else None


async def resolve_and_download(
    client: httpx.AsyncClient,
    *,
    api_root: str,
    api_key: str,
    video_id: str,
    model: str,
    out_dir: Path,
    poll_seconds: float = 2.0,
    timeout_seconds: float = 900.0,
) -> dict:
    """Poll a won slot to completion, then download and inspect it."""
    started = time.monotonic()
    while True:
        resp = await client.get(
            f"{api_root}/agnesapi",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"video_id": video_id, "model_name": model},
        )
        body = resp.json() if resp.content else {}
        status = str(body.get("status") or "unknown")
        if status == "completed":
            # Official contract: top-level `url`.
            url = body.get("url")
            if not url:
                return {"ok": False, "reason": "completed but no top-level url", "raw": body}
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / f"{video_id}.mp4"
            media = await client.get(url, timeout=httpx.Timeout(300.0))
            dest.write_bytes(media.content)
            return {
                "ok": True,
                "video_id": video_id,
                "url": url,
                "path": str(dest),
                "bytes": dest.stat().st_size,
                "seconds": body.get("seconds"),
                "size": body.get("size"),
                "has_audio": has_audio_track(dest),
            }
        if status == "failed":
            return {"ok": False, "reason": f"failed: {body.get('error')}", "raw": body}
        if time.monotonic() - started > timeout_seconds:
            return {"ok": False, "reason": "poll timeout", "video_id": video_id}
        await asyncio.sleep(poll_seconds)
