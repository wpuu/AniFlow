# Real cat video: swap fixed the immediate OOM, but the quality/budget test did not pass

**Final outcome: no real video was produced.** The approved retry reached genuine GPU sampling, but the first two high-noise steps were separated by 653.803 seconds. The remaining original-quality work could not fit the bounded runtime. Compute was stopped early; the instance, deployed environment and model disk were retained.

The first real Wan2.2 I2V-A14B cat request was submitted exactly once. It entered ComfyUI execution, but the Linux kernel killed the ComfyUI process for host-memory exhaustion while loading/staging the text encoder. No MP4 was produced. This is not a successful video test.

## Evidence and retained state

- Actual service result: `oom-kill`, main process exit status 9; kernel OOM evidence retained privately.
- Sampled device-memory peak: 11,720,982,528 bytes. Sampled host-memory use peak: 15,429,001,216 bytes. These are sampled observations, not allocator high-water measurements.
- Instance reached `stopped` at 2026-10-29 10:33:00 UTC (18:33 Beijing). The model disk and deployed environment were retained.
- The failed request was reconciled to `failed` using the kernel/service evidence; no replacement POST was made. The local interface preserves that failure.
- After actual stopped-state confirmation, the old backup execution was cancelled and the old primary rule disabled. A future start requires newly verified protection.

## Owner-approved retry

The owner explicitly approved one retry with 64 GiB of swap on the existing encrypted 180 GB root volume. No volume expansion, new instance, quota increase, account-plan upgrade, model download, precision change, or quality reduction is authorized by this retry.

Physical RAM remains about 15 GiB and GPU memory remains unchanged. Swap supplies disk-backed host memory; it may make loading/inference substantially slower and does not guarantee completion.

The helper requires at least 68 GiB of free root-disk space, verifies a current-boot future deadline, allocates exactly 64 GiB, checks the active swap and physical RAM, and appends only its own startup entry. Unknown files, conflicting entries and insufficient space cause a safe failure. Actual swap creation has not yet occurred at this checkpoint.

The unchanged workflow uses FP16 weights, native 800×1376, 121 model frames at 24 fps, and 20 steps. The final output target remains a 5-second 9:16 MP4. The same owner-supplied cat image and approved motion are retained privately.

## Budget and protection gates

Fresh account/credit/price reads confirmed the existing plan remains PAID/ACTIVE, the five task credits remain active, and Ohio Linux shared g6.xlarge is $0.8048/hour. This does not constitute an account-plan change.

The combined conservative service envelope, including the previous failed attempt and disk retention through the known credit expiry, is $2.80110. The existing 30% tax/error risk reserve plus $0.15 allowance is $0.99033. This reserve is not a verified tax rate or a final invoice guarantee. The net cash cap remains $1; credit eligibility and guard checks must pass again before a single start.

Fresh primary and independent backup proofs are required before starting. The proposed main stop is 45 minutes after arming, with an independent emergency deadline 10 minutes later. An early successful or definitively failed attempt will be stopped promptly. Preserved disks must not be deleted without the owner's specified cleanup time.

Local helper verification: 13 swap tests and four private controller interception tests passed. These tests do not prove GPU inference or a generated video.

All credentials, account identifiers, raw AWS receipts, source-image paths and browser authorization data remain outside this public report.

## Real retry checkpoint — 2026-10-29 11:08 UTC

The new primary and independent backup proofs passed against the actually stopped retained instance. Fresh future protection was then armed for 11:48:09 UTC stop and 11:58:09 UTC emergency fallback. Only one Start request was issued; a separate EC2 read confirmed `running`.

The 64 GiB swap setup completed through real SSM. Its receipt reports 68,719,472,640 effective swap bytes on the existing root disk, with physical RAM unchanged at 16,109,846,528 bytes. Fresh cached runtime evidence confirmed four retained model files and live CUDA/ComfyUI. The readiness gate matched the swap evidence and runtime evidence to the same current boot.

The new-boot queue and history were both actually empty. The prior failed export state was preserved under a separate failed-cycle directory. New monitor/export/save observers started successfully, and the private encrypted S3 save probe passed before submission.

The local real Bridge reported `REAL_WAN`, ready, GPU connected, and `simulation=false`. One new approved real job was posted; its prompt ID is `3d2a9624-91cc-4f9c-8a69-08ac12f06c7b`. It was observed running at 11:07:23 UTC. A separate browser read confirmed the frontend shows the new real task and the Wan model ready.

At 11:08 UTC there is still no completed or verified video. Early sampled GPU use reached 12,232,687,616 bytes and host-memory use 13,674,889,216 bytes. These are progress observations, not a successful-video claim or final peaks. The request must only be recovered by its existing identity; no automatic POST retry is permitted.

## Final real outcome — 2026-10-29

The same prompt produced actual progress events for node 12: step 1/10 at 11:19:43.347 UTC and step 2/10 at 11:30:37.150 UTC. This is two observed steps in the first phase of the configured 20-step workflow, not completion of either phase or a rendered video.

Before early stopping, an actual read showed the exact request still running, its ComfyUI history empty, and zero MP4s on the node. The ComfyUI service was active and there was no new current-boot host-OOM record. Swap use was about 1.6 GB. Thus this retry was interrupted for insufficient original-quality budget/runtime, not a claimed second OOM or a model execution error.

A single Stop request was acknowledged at 11:32:44 UTC. A subsequent EC2 read confirmed `stopped` at **11:39:11 UTC / 19:39:11 Beijing**. Only after that actual terminal state was the new independent backup cancelled and the primary rule disabled. No instance or disk was terminated or deleted.

The final sampled device-memory peak was 21,504,196,608 bytes and sampled host-memory use peak was 15,966,044,160 bytes. These remain sampled lower bounds, not exact allocator peaks. Full inference duration and video encoding time are unavailable because the workflow did not finish.

The Start-to-Stopping compute estimate with a 10-second buffer is about **$0.38 before credits**, excluding the separately budgeted storage and auxiliary services. Replacing the unused runtime envelope with this early-stop estimate leaves a conservative combined service envelope of about $2.44 and the same tax/error reserve method at about $0.883. These are estimates, not a finalized invoice or a verified tax rate. Original preflight eligibility was verified; the final cash charge for this specific attempt has not yet been invoiced.

The retained 180 GB gp3 disk and provisioned 375 MiB/s throughput continue to have an estimated $24.40/month service cost. Stopping compute does not remove that storage cost. No owner-selected cleanup time has been received; the disk remains retained. Credit expiry remains 2026-10-30 11:29:56 Beijing, and future invoice treatment must not be inferred merely from the expiry date.

The local real Bridge now preserves the exact request as an externally verified budget interruption, with its original database backed up. Its offline readiness gate blocks further generation, and the owned old tunnel was closed. No new POST was made during reconciliation.

The [sanitized outcome JSON](2026-10-29-cat-swap-retry-outcome.json) records the observed times, progress events, sampled peaks, bounded estimates and retained-resource state. This configuration has **not** passed the original-quality 5-second video acceptance test and must not be presented as a successful reusable video recipe. A future attempt needs a new budget/protection review and measured step throughput; old deadlines, authorization material and submission identities must never be replayed.

Final independent browser verification confirmed the real frontend is offline, with zero running jobs, zero completed jobs and one preserved externally interrupted request. No generation or retry button was used during verification. A Chinese offline HTML report and a sanitized source package were saved to a new owner-approved G-drive report directory. All package files were re-read and SHA-verified, and the source ZIP passed CRC verification; it includes the existing frontend, Bridge, guard helpers and startup scripts. It contains no original source photo, credentials, private AWS receipts or model weights and is not a full environment/model backup. The [sanitized package receipt](2026-10-29-cat-swap-local-package.json) records its files and hashes.
