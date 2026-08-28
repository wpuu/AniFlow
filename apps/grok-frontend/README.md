# Grok frontend import area

This directory is reserved for the owner's existing private Grok 4.6 generated frontend.

When importing it later:

1. Unzip/copy the entire generated app into this directory as-is.
2. Preserve its original file/folder structure for the first review.
3. Do not move files into AniFlow backend directories before review.
4. Do not commit real Agnes API keys, tokens, `.env` secrets, build caches, or `node_modules`.
5. The first integration pass will audit framework/runtime, API calls, key exposure, reusable UI components, and the minimum adapter needed to connect AniFlow.

Frontend integration is intentionally out of scope for the current V0.1 backend validation.
