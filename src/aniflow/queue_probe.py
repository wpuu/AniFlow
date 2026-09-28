"""Agnes video queue probe.

Answers one question that decides AniFlow's whole capacity model:

    Is the free video queue shared across the whole platform,
    or is it enforced per account?

If it is per-account, the owner's 9 independent Agnes accounts multiply video
throughput by 9 and the multi-key gacha strategy is the core advantage.
If it is global, extra accounts do nothing for video (they still help text and
image), and the production plan has to be rebuilt around scarce queue slots.

Method
------
Fire one video-create request from EVERY key at the same instant, repeatedly.

    - A round that returns a MIX of accepted and queue_full at the same instant
      proves the limit is per-account. This is the only definitive signal.
    - Rounds that are uniformly rejected cannot distinguish the two cases: the
      platform may be globally saturated, or every account may be individually
      saturated at once.
    - Rounds that are uniformly accepted just mean there was spare capacity.

Deliberately uses `mode: "text"`, which needs no `first_frame` and therefore no
public media layer. The probe runs with nothing configured but API keys.

A won slot is carried through to completion so the run also answers the second
open question: does Agnes video output contain a native audio track?
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
        """The definitive per-account signal."""
        return bool(self.accepted) and any(a.is_queue_full for a in self.rejected)


# --- verdicts -------------------------------------------------------------

PER_ACCOUNT = "per_account"
INCONCLUSIVE_SATURATED = "inconclusive_saturated"
CAPACITY_AVAILABLE = "capacity_available"
NO_KEYS = "no_keys"


def decide(rounds: list[Round]) -> str:
    if not rounds:
        return NO_KEYS
    if any(r.is_mixed for r in rounds):
        return PER_ACCOUNT
    if any(r.accepted for r in rounds):
        return CAPACITY_AVAILABLE
    return INCONCLUSIVE_SATURATED


VERDICT_TEXT = {
    PER_ACCOUNT: (
        "队列按【账户】隔离  ✅",
        "同一瞬间有账户被拒、有账户成功 —— 这只可能是按账户限制。\n"
        "  → 你的 9 个账户对视频【有效】，多 Key 抽卡策略成立，产能可叠加。",
    ),
    CAPACITY_AVAILABLE: (
        "队列当前有空位（未能区分模型）  ⚠️",
        "所有账户都成功了，说明此刻不缺容量，但无法区分是按账户还是全平台共享。\n"
        "  → 请在队列繁忙时段再跑一次，那时才能看出差别。",
    ),
    INCONCLUSIVE_SATURATED: (
        "全部被拒，无法区分  ⚠️",
        "所有账户同时被拒。可能是全平台共享队列满了，\n"
        "  也可能是每个账户各自都满了 —— 这两种情况此刻长得一样。\n"
        "  → 建议用 --watch 持续挂机，等出现【部分成功】的那一刻即可定论。",
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
    """True/False if determinable, None if unknown.

    Prefers ffprobe. Falls back to scanning the MP4 for a handler box declaring
    the 'soun' media type, which needs no external tooling.
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
            )
            return "audio" in out.stdout
        except Exception:  # noqa: BLE001
            pass
    try:
        head = path.read_bytes()[:2_000_000]
    except OSError:
        return None
    if b"soun" in head:
        return True
    if b"vide" in head:
        return False  # video handler found, no audio handler
    return None


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
