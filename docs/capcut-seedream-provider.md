# CapCut / Seedream image-provider plan

## Decision

AniFlow must not hard-code Agnes Image as the only source for character references and A/B/C keyframes.

Current architecture:

```text
Storyboard / Character prompts
        |
        v
ImageProvider
   |----------- AgnesImageProvider
   |
   `----------- CapCutSeedreamProvider
                        |
                 subprocess JSON contract
                        |
                 browser Agent adapter
                        |
                 CapCut normal Web UI
                        |
                 downloaded image(s)
                        |
              persist to public media
                        |
                        v
                 one public URL
        |
        v
existing Video / QA pipeline
```

`src/aniflow/image_provider.py` is the provider-neutral interface. It is already used by character identity/reference generation and story A/B/C keyframe generation, so those pipelines are no longer structurally tied to Agnes Image.

## Model-name policy

Do not compile one Seedream version into AniFlow.

CapCut changes the models exposed by account, region and product version. The exact model label is runtime data. AniFlow therefore supports:

- optional default: `CAPCUT_SEEDREAM_MODEL`;
- page-level model field stored in browser localStorage;
- per-request model override sent from the frontend to the local Bridge.

Only `CAPCUT_RUNNER_COMMAND` must be configured for the browser Agent. A missing default model must not disable CapCut if the user has entered a model in the page.

## Implemented local Bridge contract

The loopback Bridge exposes:

- `GET /api/health`
  - media readiness;
  - frontend readiness;
  - CapCut Runner readiness;
  - optional default CapCut model.
- `POST /api/media/upload`
  - PNG/JPEG/WEBP only;
  - maximum 20 MiB;
  - persists local browser images into AniFlow's R2/S3-compatible public media store.
- `POST /api/images/generate`
  - `provider=agnes|capcut`;
  - prompt;
  - reference URLs;
  - ratio;
  - model override for CapCut;
  - request-scoped Agnes API key when Agnes Image is selected.

The Bridge serves the built single-file frontend at `http://127.0.0.1:8765/`. Standard use is same-origin; it does not enable broad `Origin: null` access for arbitrary local HTML files.

## CapCut Runner protocol

`src/aniflow/capcut/provider.py` defines the external browser-automation process contract.

`CAPCUT_RUNNER_COMMAND` may be a command string, or preferably on Windows a JSON string array such as:

```text
["python","scripts/capcut_agent_adapter.py"]
```

AniFlow appends:

```text
--request <request.json> --response <response.json>
```

The request contains:

```json
{
  "prompt": "...",
  "model": "exact model label from the page",
  "ratio": "9:16",
  "reference_paths": ["C:/.../reference-0.png"],
  "output_dir": "C:/.../output"
}
```

The adapter must write either:

```json
{"output_path":"C:/.../result.png"}
```

or:

```json
{"output_paths":["C:/.../1.png","C:/.../2.png"]}
```

The provider currently accepts the first returned output as the provider result and uploads it to AniFlow media storage. Multi-candidate scoring remains a later hardening step; it must not be described as already implemented.

Reference images are downloaded from AniFlow public URLs and restored to real `.png`, `.jpg` or `.webp` extensions before the browser adapter sees them. Temporary files are removed after use.

## Logged-in UI discovery gate

The final browser adapter must be based on the owner's real logged-in CapCut page rather than guessed selectors.

AniFlow now includes:

```text
scripts/capcut_agent_probe.py
```

The probe uses an `agent-browser` session and writes private runtime artifacts only under the gitignored:

```text
data/runtime/capcut/
```

Suggested sequence on the real Windows machine:

```text
python scripts/capcut_agent_probe.py open
```

Log in normally and navigate to the actual AI Design / image-generation workspace, then:

```text
python scripts/capcut_agent_probe.py capture
```

The capture stores:

- current URL;
- page title;
- interactive-element snapshot;
- body text;
- authenticated browser state.

`browser-state.json` may contain session credentials/cookies and must remain local/private. `data/runtime/` is gitignored.

After the probe, the final adapter should be written against the real semantic controls found in `snapshot.txt`. It must fail closed if a required control cannot be identified.

## Browser-agent target behavior

After the probe confirms the real UI, the final adapter should:

1. load/reuse the authorized local browser session;
2. open the real CapCut AI Design/image workspace;
3. select the request's exact model label;
4. select the requested aspect ratio;
5. upload any request reference images through the normal file control;
6. fill the prompt exactly as received;
7. start generation through the visible control;
8. wait for completion using page state, not fixed blind sleeps where avoidable;
9. download completed output(s) through normal UI behavior;
10. write the JSON response expected by `CapCutSeedreamProvider`.

No coordinate-only automation should be used as the primary control strategy.

## Candidate selection — pending hardening

CapCut may return several images per generation. AniFlow should eventually exploit this rather than arbitrarily selecting the first result.

Planned later behavior:

1. retain all returned candidates temporarily;
2. use `agnes-2.5-flash` vision judging to compare character identity, anatomy, style/material, reference fidelity, scene continuity and suitability as a video keyframe;
3. return the best candidate;
4. delete rejected temporary candidates unless benchmark retention is enabled.

This is **not yet implemented** in the CapCut provider.

## Reference-image strategy

For character creation and story keyframes, reference roles stay the same regardless of provider:

- identity anchor -> locks geometry/identity;
- style front/three-quarter/side -> locks material and style;
- previous story keyframe -> locks camera/environment continuity.

CapCut/Seedream can receive these references through its normal upload UI. No CapCut-internal URL should be treated as durable storage; generated assets must be copied into AniFlow media storage before Video generation.

## Session and safety boundaries

- No automated account creation.
- No CAPTCHA or anti-bot bypass.
- No private/undocumented CapCut API reverse engineering in V0.1.
- No committed cookies, auth state or CapCut credentials.
- Browser session state is local-only and gitignored.
- When login expires, stop and use normal user sign-in instead of attempting bypasses.

## Current status

Implemented:

- provider-neutral image interface;
- Agnes image provider;
- CapCut subprocess provider contract;
- Windows-safe Runner command parsing;
- reference download with valid image extensions;
- local Bridge media upload and provider generation endpoints;
- frontend Agnes/CapCut provider selector;
- page-saved CapCut model label;
- up to three reference images in the private frontend;
- generated-image handoff to video first/last-frame inputs;
- logged-in CapCut UI discovery probe;
- tests for Bridge and subprocess contract committed to the repository.

Not yet proven/completed:

- real logged-in CapCut UI snapshot from the owner's machine;
- final UI control adapter;
- real CapCut generation through AniFlow;
- multi-candidate visual ranking;
- production stability against future CapCut UI changes.

Do not replace Agnes Video with CapCut video generation in this step. CapCut/Seedream is being introduced as an image/keyframe provider first; the Agnes Video V2.0 / Agnes Video 2.5 Flash comparison remains independent.
