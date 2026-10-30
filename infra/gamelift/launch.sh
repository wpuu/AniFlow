#!/bin/bash
set -euo pipefail
exec > "${HOME}/aniflow-h3-launch.log" 2>&1
source_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
runtime_root="${HOME}/aniflow-h3-runtime"
mkdir -p "$runtime_root"
cd "$source_root"
sha256sum -c runtime.sha256
tar -xf runtime.tar -C "$runtime_root"
while IFS= read -r model; do
    mkdir -p "$runtime_root/ComfyUI/models/$(dirname "$model")"
    ln -sf "$source_root/ComfyUI/models/$model" "$runtime_root/ComfyUI/models/$model"
done < model-paths.txt
exec "$runtime_root/python/bin/python3.12" -B "$runtime_root/runtime.py"
