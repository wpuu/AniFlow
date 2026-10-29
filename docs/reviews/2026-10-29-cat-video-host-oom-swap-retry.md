# Real cat video: host-memory failure and approved swap retry

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
