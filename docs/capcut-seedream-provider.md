# CapCut / Seedream image-provider plan

## Decision

AniFlow must not hard-code Agnes Image as the only source for character references and A/B/C keyframes.

The preferred architecture is:

```text
Storyboard / Character prompts
        |
        v
ImageProvider
   |----------- AgnesImageProvider
   |
   `----------- CapCutSeedreamProvider (browser-agent adapter)
                        |
                        v
                 CapCut normal Web UI
                        |
                 4 image candidates
                        |
              persist to public media
                        |
              select best candidate
                        |
                        v
                 one public URL
        |
        v
existing Video / QA pipeline
```

`src/aniflow/image_provider.py` is the provider-neutral interface. Existing Agnes behavior remains the default.

## Why CapCut is a first-class candidate

CapCut's official AI Image workflow supports text-to-image, reference-image input, multiple image models, aspect-ratio selection and multiple generated results. Seedream 4.x documentation also describes multi-reference fusion and consistency-oriented generation.

The exact model label must be configurable rather than compiled into AniFlow. The owner's CapCut installation/account may expose labels such as Seedream 4.3 or 4.0s while CapCut's public Web pages can expose newer labels such as Seedream 4.5/5.0.

## Browser-agent contract

The adapter should automate only the normal signed-in CapCut Web UI.

1. User signs in manually once.
2. Persist the authorized browser session locally; never commit session files/cookies.
3. Open CapCut AI Design / AI Image.
4. Select the configured model label.
5. Select the requested aspect ratio (AniFlow V0.1 defaults to 9:16).
6. Download AniFlow public reference URLs to a temporary local directory when references are supplied.
7. Upload the reference images through the normal CapCut file input.
8. Fill the prompt exactly as produced by AniFlow.
9. Start generation through the visible Generate/Send control.
10. Wait for the UI to expose completed candidates.
11. Download candidate images through the normal UI/download action.
12. Upload downloaded files into AniFlow public media storage (R2/S3-compatible store).
13. Delete temporary local files.
14. Return persistent public candidate URLs.

The adapter must fail closed if the model selector, prompt box, upload input, result area or download control cannot be identified. It must not guess coordinates and continue blindly.

## Candidate selection

CapCut commonly returns several images per generation. AniFlow should use that as an advantage rather than arbitrarily selecting the first result.

For each requested keyframe:

1. ask CapCut for its normal candidate set;
2. persist all candidates temporarily;
3. use `agnes-2.5-flash` vision judging to compare:
   - character identity;
   - anatomy/geometry;
   - requested style/material;
   - reference-image fidelity;
   - scene continuity with the previous keyframe;
   - composition suitability as a video first/last frame;
4. return the best candidate as the provider's single `generate()` result;
5. delete rejected temporary candidates after scoring unless benchmark retention is explicitly enabled.

This keeps the rest of AniFlow provider-neutral while still exploiting CapCut's multi-output workflow.

## Reference-image strategy

For character creation and story keyframes, reference roles stay the same regardless of provider:

- identity anchor -> locks geometry/identity;
- style front/three-quarter/side -> locks material and style;
- previous story keyframe -> locks camera/environment continuity.

CapCut/Seedream can receive these references through its normal upload UI. No CapCut-internal URL should be treated as durable storage; generated assets must be copied into AniFlow media storage before Video generation.

## Session and safety boundaries

- No automated account creation.
- No CAPTCHA or anti-bot bypass.
- No private/undocumented CapCut API reverse engineering in the V0.1 provider.
- No committed cookies, auth state or CapCut credentials.
- Browser session state is local-only and gitignored.
- When login expires, stop and request normal user sign-in instead of attempting bypasses.

## Implementation stages

### Stage A — now

- provider-neutral image interface;
- Agnes provider adapter remains default;
- keyframe pipeline accepts any provider;
- model label treated as runtime configuration.

### Stage B — first CapCut integration

- browser-agent script with manual first login;
- prompt + ratio + model selection;
- optional reference uploads;
- candidate download and R2 persistence;
- return one selected public URL.

### Stage C — production hardening

- semantic selector fallbacks;
- screenshots on UI mismatch;
- per-step timeouts and retry only safe/idempotent steps;
- candidate-level vision scoring;
- CapCut/Agnes comparative benchmark recorded by provider/model.

## Non-goal

Do not replace Agnes Video with CapCut video generation in this step. CapCut/Seedream is being introduced as an image/keyframe provider first; the existing Agnes Video V2.0 / Agnes Video 2.5 Flash comparison remains independent.
