"""P0-010: at most ONE live Agnes Video 2.5 Flash create request.

Default: print a sanitized plan; NO credentials read, NO network, NO files.
--execute requires an explicit billing acknowledgement and exactly one API key
in ANIFLOW_SINGLE_SHOT_API_KEY, set only in a trusted local environment.
A durable attempt record is created BEFORE posting, preventing silent duplicates.
--resume polls an existing video_id without ever creating another video.

Only first shot of the audited MYCL-001 shotlist, text mode, 5s, 720P, 9:16.
No bulk Key rotation, automatic retry, paid mode change, public upload or publish.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from lock_upstream_creative_checkpoint import ContractError, lock_contract

MODEL = "agnes-video-2.5-flash"
DOMAINS = {
    "global": "https://apihub.agnes-ai.com",
    "china": "https://api.agnes-ai.cn",
    "fallback": "https://apihub.agnes-ai.cn",
}
MAX_VIDEO_BYTES = 200 * 1024 * 1024
MAX_POLLS = 90
VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_.-]{4,180}\Z")


class ShotError(RuntimeError):
    """Fail-closed, redacted user-visible error."""


def _write_json(path: Path, data: dict, *, replace: bool = False) -> None:
    """Atomic same-directory JSON write; no dumping HTTP responses or secrets."""
    temp = path.parent / (path.name + ".pending")
    if temp.exists() or temp.is_symlink():
        raise ShotError("A pending evidence file already exists")
    raw = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    try:
        with temp.open("xb") as stream:
            stream.write(raw)
        if not replace and (path.exists() or path.is_symlink()):
            raise ShotError("Evidence record exists; use --resume, not --execute")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def prepare_plan(shotlist: Path, factpack: Path, *, domain: str = "global") -> dict:
    if domain not in DOMAINS:
        raise ShotError("Unknown Agnes API domain")
    try:
        contract = lock_contract(shotlist, factpack)
    except (ContractError, OSError) as exc:
        raise ShotError(f"Source contract rejected ({type(exc).__name__})") from None
    if contract["episode_id"] != "MYCL-001" or contract["scene_count"] != 8:
        raise ShotError("P0-010 only permits the frozen first episode MYCL-001")
    if contract["scene_durations"][0] != 5:
        raise ShotError("P0-010 requires exactly five seconds for shot 1")
    prompt = contract["scene_prompts"][0]
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ShotError("Invalid locked shot prompt")
    request = {
        "model": MODEL, "prompt": prompt,
        "seconds": "5", "mode": "text", "size": "720P",
        "aspect_ratio": "9:16", "n": 1,
    }
    digest = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "episode_id": "MYCL-001",
        "shot_id": "1",
        "seconds": 5,
        "model": MODEL,
        "mode": "text",
        "resolution": "720P",
        "aspect_ratio": "9:16",
        "keyframe_reference_used": False,
        "domain": domain,
        "request_sha256": digest,
        "shotlist_sha256": contract["shotlist_sha256"],
        "factpack_sha256": contract["factpack_sha256"],
        "_request": request,
    }


def public_plan(plan: dict) -> dict:
    return {**{k: v for k, v in plan.items() if not k.startswith("_")},
            "result": "PLAN_ONLY_NO_REQUESTS", "submissions": 0,
            "price_checked_at_runtime": False,
            "human_visual_review_required": True}


def _single_key(environ: dict[str, str]) -> str:
    key = environ.get("ANIFLOW_SINGLE_SHOT_API_KEY", "").strip()
    if not key or "," in key or "\n" in key or "\r" in key or len(key) > 4096:
        raise ShotError("Exactly one secure environment API Key is required")
    return key


def _codespace_workspace_base() -> Path:
    """GitHub's persisted volume; distinct from disposable container home."""
    return Path("/workspaces")


def _codespace_private_root() -> Path | None:
    """Protect output and once-only evidence against Codespaces rebuilds."""
    if os.environ.get("CODESPACES", "").lower() != "true":
        return None
    workspaces = _codespace_workspace_base()
    if not workspaces.is_dir() or workspaces.is_symlink():
        raise ShotError("Codespaces persistent /workspaces volume is unavailable")
    private = workspaces / ".aniflow-private"
    if private.is_symlink():
        raise ShotError("Codespaces private persistent folder must not be a symlink")
    if private.exists() and not private.is_dir():
        raise ShotError("Codespaces private persistent folder is not a directory")
    return private


def _output_dir(path: Path, *, create: bool) -> Path:
    target = Path(path).expanduser()
    if target.exists() and target.is_symlink():
        raise ShotError("Output directory must not be a symbolic link")
    target = target.resolve(strict=False)
    root = Path(__file__).resolve().parents[1]
    if target == root or root in target.parents:
        raise ShotError("Use an external output directory; never put videos in this Git repo")
    persistent = _codespace_private_root()
    if persistent is not None:
        # GitHub Codespaces clears /home during a container rebuild; its
        # /workspaces volume survives both restarts and rebuilds. Refuse
        # disposable storage *before* making a potentially billable POST.
        if persistent not in target.parents:
            raise ShotError(
                "In Codespaces use /workspaces/.aniflow-private/<new-folder>; "
                "home-directory videos are erased on container rebuild"
            )
    if target.parent.is_symlink() or not target.parent.is_dir():
        raise ShotError("Output parent directory must exist and not be a symlink")
    if create:
        try:
            target.mkdir(exist_ok=False)
        except FileExistsError:
            raise ShotError("Output directory already exists; use --resume") from None
    elif not target.is_dir():
        raise ShotError("Existing output directory not found")
    return target



def _once_root() -> Path:
    """One-submission ledger, in Codespaces' rebuild-persistent volume."""
    private = _codespace_private_root()
    if private is not None:
        return private / "single-attempt-ledger"
    return Path.home() / ".local" / "state" / "aniflow-single-shot"


def _reserve_one_submission(plan: dict, outdir: Path) -> Path:
    """Reserve this fixed first-shot intent before any HTTP POST.

    An exclusive file is deliberately retained after timeout or rejection:
    creating a different output directory must not silently cause a second
    potentially billable task in the same Codespace/user home. Do not store
    API keys, signed CDN URLs or full user paths.
    """
    root = _once_root().expanduser()
    if root.is_symlink():
        raise ShotError("Single-submission guard location is a symlink")
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise ShotError("Unable to create the single-submission guard directory") from None
    if not root.is_dir() or root.is_symlink():
        raise ShotError("Single-submission guard directory is not safe")
    guard = root / "MYCL-001-shot-1.once.json"
    if guard.is_symlink():
        raise ShotError("Single-submission guard already exists")
    record = {
        "intent": "MYCL-001-shot-1",
        "request_sha256": plan["request_sha256"],
        "domain": plan["domain"],
        "output_folder": outdir.name,
        "reserved_at_unix": int(time.time()),
        "policy": "one submission per persistent workspace across output folders",
        "contains_api_key": False,
    }
    try:
        # Exclusive-create works across concurrently running Python processes.
        with guard.open("xb") as stream:
            stream.write(json.dumps(record, ensure_ascii=False).encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise ShotError(
            "P0-010 already reserved in this persistent workspace: inspect the previous "
            "attempt and provider history; never resubmit by changing output directories"
        ) from None
    except OSError:
        # An ambiguous or partially written guard must remain; don't re-POST.
        raise ShotError("Unable to durably reserve one submission; no POST attempted") from None
    return guard



def _safe_code(body: object) -> str:
    if isinstance(body, dict):
        code = body.get("code")
        if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,45}", code):
            return code
    return "unclassified"


def _save_attempt(path: Path, plan: dict, *, status: str, video_id: str | None = None,
                  http_status: int | None = None, code: str | None = None) -> dict:
    item = {
        "episode_id": plan["episode_id"], "shot_id": plan["shot_id"],
        "model": plan["model"], "domain": plan["domain"],
        "request_sha256": plan["request_sha256"],
        "shotlist_sha256": plan["shotlist_sha256"],
        "factpack_sha256": plan["factpack_sha256"],
        "status": status, "video_id": video_id,
        "http_status": http_status, "error_code": code,
        "submissions_attempted": 1, "created_at_unix": int(time.time()),
        "contains_api_key": False,
    }
    _write_json(path, item, replace=(status != "SUBMISSION_ATTEMPT_UNCONFIRMED"))
    return item


def _read_attempt(path: Path, plan: dict) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 16_384:
        raise ShotError("Existing attempt record missing or invalid")
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ShotError("Existing attempt record is unreadable") from None
    if not isinstance(saved, dict) or saved.get("request_sha256") != plan["request_sha256"]:
        raise ShotError("Attempt record does not match locked shot request")
    if saved.get("domain") != plan["domain"] or saved.get("submissions_attempted") != 1:
        raise ShotError("Attempt record source or submission count is inconsistent")
    video_id = saved.get("video_id")
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        raise ShotError("Cannot resume without previously recorded video_id")
    return saved


def _public_https_url(url: object) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ShotError("Completed task returned no safe video URL")
    try:
        u = urlsplit(url)
    except ValueError:
        raise ShotError("Completed task returned malformed video URL") from None
    try:
        port = u.port
    except ValueError:
        raise ShotError("Malformed video URL port") from None
    if u.scheme != "https" or not u.hostname or u.username or u.password or port not in (None, 443):
        raise ShotError("Video download must be a public HTTPS URL without credentials")
    hostname = u.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith((".local", ".internal", ".localhost")):
        raise ShotError("Private video download host rejected")
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # Public DNS names are provider-controlled; no localhost/IP literal is allowed.
        if "." not in hostname or not re.fullmatch(r"[a-z0-9.-]{4,240}", hostname):
            raise ShotError("Invalid video CDN hostname") from None
    else:
        if not addr.is_global:
            raise ShotError("Private video IP rejected")
    return url


def _download_video(client: httpx.Client, url: str, outdir: Path) -> tuple[Path, str, int]:
    """Stream at most 200 MiB to a new private file; no bearer on CDN GET."""
    _public_https_url(url)
    target = outdir / "MYCL-001-shot-1.mp4"
    temp = outdir / "MYCL-001-shot-1.part"
    if target.exists() or target.is_symlink() or temp.exists():
        raise ShotError("Existing video or partial download; refuse overwrite")
    sha = hashlib.sha256()
    total = 0
    try:
        with (
            client.stream("GET", url, headers={"Accept": "video/mp4"}) as response,
            temp.open("xb") as stream,
        ):
            if response.status_code != 200:
                raise ShotError(f"CDN download failed (HTTP {response.status_code})")
            mime = response.headers.get("content-type", "").lower()
            if mime and not mime.startswith(("video/", "application/octet-stream")):
                raise ShotError("CDN returned a non-video content type")
            for block in response.iter_bytes(chunk_size=1024 * 1024):
                total += len(block)
                if total > MAX_VIDEO_BYTES:
                    raise ShotError("Downloaded video exceeds 200 MiB safety limit")
                sha.update(block)
                stream.write(block)
        if total < 1024:
            raise ShotError("Downloaded video is unexpectedly small")
        os.link(temp, target)  # atomic no-overwrite link on same volume
        return target, sha.hexdigest(), total
    except FileExistsError:
        raise ShotError("Output video appeared during download") from None
    except httpx.HTTPError as exc:
        raise ShotError(f"CDN download failed ({type(exc).__name__})") from None
    finally:
        temp.unlink(missing_ok=True)


def _inspect_clip(path: Path) -> dict:
    from inspect_video_output import ProbeError, inspect_file

    try:
        report = inspect_file(
            path, min_seconds=4, max_seconds=6,
            require_audio=False, min_short_side=720,
        )
    except (ProbeError, ValueError, OSError) as exc:
        return {"result": "BLOCKED", "blockers": [f"Media inspection failed ({type(exc).__name__})"]}

    # A broad 4..6 second metadata window is NOT enough for a locked
    # five-second narration/shot timeline. Reject even a valid 4s portrait MP4.
    # The provider's published Flash 720P/9:16 geometry is 720x1280.
    blockers = report.setdefault("blockers", [])
    seconds = report.get("duration_seconds")
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or abs(seconds - 5) > 0.5:
        blockers.append("Actual duration differs from locked 5-second shot (>0.5 s)")
    if report.get("display_dimensions") != [720, 1280]:
        blockers.append("Displayed frame must be 720x1280 for Flash 720P/9:16")
    if blockers:
        report["result"] = "BLOCKED"
    report["requested_seconds"] = 5
    report["allowed_duration_deviation_seconds"] = 0.5
    return report


def _poll_existing(client: httpx.Client, key: str, plan: dict, evidence_path: Path,
                   *, interval: float = 10.0, max_polls: int = MAX_POLLS,
                   sleep_fn=time.sleep) -> dict:
    evidence = _read_attempt(evidence_path, plan)
    if not 1 <= max_polls <= MAX_POLLS or not 0 <= interval <= 30:
        raise ShotError("Polling budget must be bounded")
    video_id = evidence["video_id"]
    domain = DOMAINS[plan["domain"]]
    url = domain + "/agnesapi"
    status = "unknown"
    for n in range(max_polls):
        try:
            response = client.get(url, headers={"Authorization": "Bearer " + key},
                                  params={"video_id": video_id, "model_name": MODEL})
        except httpx.HTTPError as exc:
            raise ShotError(f"Polling failed ({type(exc).__name__}); resume without new POST") from None
        if response.status_code != 200:
            raise ShotError(f"Polling failed HTTP {response.status_code}; resume without new POST")
        try:
            data = response.json()
        except ValueError:
            raise ShotError("Polling returned invalid JSON; resume without new POST") from None
        if not isinstance(data, dict):
            raise ShotError("Polling returned invalid task shape")
        status = data.get("status")
        if status == "failed":
            evidence["status"] = "FAILED_UPSTREAM"
            evidence["error_code"] = _safe_code(data.get("error"))
            _write_json(evidence_path, evidence, replace=True)
            return {"result": "FAILED_UPSTREAM", "video_id": video_id, "submissions": 0,
                    "error_code": evidence["error_code"]}
        if status == "completed":
            # Save no URL / signed CDN query to the audit record.
            download_url = _public_https_url(data.get("url"))
            movie, sha, size = _download_video(client, download_url, evidence_path.parent)
            report = _inspect_clip(movie)
            evidence["status"] = "MEDIA_REQUIRES_HUMAN_REVIEW" if report["result"] != "BLOCKED" else "MEDIA_QA_BLOCKED"
            evidence["mp4_sha256"] = sha
            evidence["mp4_bytes"] = size
            evidence["media_check"] = report["result"]
            evidence["media_blockers"] = report.get("blockers", [])
            evidence["actual_duration_seconds"] = report.get("duration_seconds")
            evidence["display_dimensions"] = report.get("display_dimensions")
            evidence["display_rotation_degrees"] = report.get("rotation_degrees")
            _write_json(evidence_path, evidence, replace=True)
            return {"result": evidence["status"], "video_id": video_id, "submissions": 0,
                    "output_filename": movie.name, "mp4_sha256": sha, "size_bytes": size,
                    "media_check": report["result"], "blockers": report.get("blockers", []),
                    "actual_duration_seconds": report.get("duration_seconds"),
                    "display_dimensions": report.get("display_dimensions"),
                    "display_rotation_degrees": report.get("rotation_degrees"),
                    "pixel_orientation_verified": False,
                    "manual_viewing_required": True, "published": False}
        if status not in ("queued", "pending", "processing", "running"):
            raise ShotError("Unknown Agnes task status; resume existing video_id manually")
        if n + 1 < max_polls:
            sleep_fn(interval)
    return {"result": "EXISTING_TASK_STILL_PENDING", "video_id": video_id,
            "submissions": 0, "polls": max_polls, "new_task_created": False}


def run_live(plan: dict, output: Path, *, execute: bool, resume: bool, confirmed_price: bool,
             environ: dict[str, str], client: httpx.Client | None = None,
             poll_interval: float = 10.0, max_polls: int = MAX_POLLS,
             sleep_fn=time.sleep) -> dict:
    """Execution is opt-in; --resume never POSTS; no automatic retries anywhere."""
    if not execute and not resume:
        return public_plan(plan)
    if execute and resume:
        raise ShotError("--execute and --resume cannot be used together")
    if not confirmed_price:
        raise ShotError("Review current Agnes billing and explicitly acknowledge it before live calls")
    key = _single_key(environ)
    if not shutil.which("ffprobe"):
        raise ShotError("Install ffprobe before submitting a paid-or-free video task")
    outdir = _output_dir(output, create=execute)
    evidence_path = outdir / "MYCL-001-shot-1.attempt.json"

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=httpx.Timeout(30.0, connect=12.0),
                              follow_redirects=False)
    try:
        if resume:
            return _poll_existing(client, key, plan, evidence_path,
                                  interval=poll_interval, max_polls=max_polls,
                                  sleep_fn=sleep_fn)
        # Guard across *different* output directories as well as repeated
        # invocations in the same directory. This guard persists even if HTTP
        # replies are lost or the request is rejected.
        _reserve_one_submission(plan, outdir)
        # Durable marker BEFORE calling create: any lost response remains
        # ambiguous and MUST NOT be submitted again automatically.
        _save_attempt(evidence_path, plan, status="SUBMISSION_ATTEMPT_UNCONFIRMED")
        try:
            response = client.post(
                DOMAINS[plan["domain"]] + "/v1/videos",
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=plan["_request"],
            )
        except httpx.HTTPError as exc:
            raise ShotError(f"SUBMISSION_AMBIGUOUS ({type(exc).__name__}); DO NOT RETRY AUTOMATICALLY") from None
        if response.status_code not in (200, 201, 202):
            try:
                body = response.json()
            except ValueError:
                body = {}
            _save_attempt(evidence_path, plan, status="REJECTED_NO_VIDEO_ID",
                          http_status=response.status_code, code=_safe_code(body))
            return {"result": "REJECTED_NO_VIDEO_ID", "http_status": response.status_code,
                    "error_code": _safe_code(body), "submissions": 1,
                    "automatic_retry": False}
        try:
            data = response.json()
        except ValueError:
            raise ShotError("SUBMISSION_AMBIGUOUS (malformed response); DO NOT RETRY") from None
        video_id = data.get("video_id") if isinstance(data, dict) else None
        if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
            raise ShotError("SUBMISSION_AMBIGUOUS (missing video_id); DO NOT RETRY")
        _save_attempt(evidence_path, plan, status="ACCEPTED_SINGLE_VIDEO",
                      video_id=video_id, http_status=response.status_code)
        result = _poll_existing(client, key, plan, evidence_path,
                                interval=poll_interval, max_polls=max_polls,
                                sleep_fn=sleep_fn)
        result["submissions"] = 1
        return result
    finally:
        if owns_client:
            client.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shotlist", type=Path, default=Path("content/shotlists/MYCL-001-cat-lapping.json"))
    ap.add_argument("--factpack", type=Path, default=Path("content/factpacks/MYCL-001-cat-lapping.json"))
    ap.add_argument("--domain", choices=tuple(DOMAINS), default="global")
    ap.add_argument("--output-dir", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Explicitly create ONE live video task")
    mode.add_argument("--resume", action="store_true", help="Poll the existing task; no POST")
    ap.add_argument("--i-reviewed-current-charges", dest="confirmed_price", action="store_true")
    args = ap.parse_args(argv)
    try:
        plan = prepare_plan(args.shotlist, args.factpack, domain=args.domain)
        if (args.execute or args.resume) and args.output_dir is None:
            raise ShotError("Live use requires an explicit external --output-dir")
        result = run_live(plan, args.output_dir or Path.cwd(), execute=args.execute,
                          resume=args.resume, confirmed_price=args.confirmed_price,
                          environ=os.environ)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["result"] not in ("REJECTED_NO_VIDEO_ID", "FAILED_UPSTREAM", "MEDIA_QA_BLOCKED") else 2
    except (ShotError, OSError) as exc:
        # Exceptions never include API responses, credentials or signed media URLs.
        print(json.dumps({"result": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
