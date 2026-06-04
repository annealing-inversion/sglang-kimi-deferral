#!/usr/bin/env bash
set -euo pipefail

echo "== nvidia-smi =="
nvidia-smi

echo
echo "== python packages =="
python3 - <<'PY'
import sys

import torch
import transformers
import triton

try:
    import sglang
    sglang_version = getattr(sglang, "__version__", None)
except Exception as exc:
    sglang_version = f"IMPORT_ERROR: {exc!r}"

print("python", sys.version)
print("torch", torch.__version__)
print("torch cuda", torch.version.cuda)
print("cuda available", torch.cuda.is_available())
print("gpu count", torch.cuda.device_count())
if torch.cuda.is_available():
    for i in range(torch.cuda.device_count()):
        print(f"gpu {i}", torch.cuda.get_device_name(i))
print("sglang", sglang_version)
print("transformers", transformers.__version__)
print("triton", triton.__version__)
PY

echo
echo "== selected pip packages =="
python3 -m pip show sglang sglang-kernel flashinfer-python flashinfer-cubin cuda-python | \
  sed -n '1,180p' || true
