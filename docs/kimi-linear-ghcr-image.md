# Kimi Linear SGLang GHCR Image

This image is intended for validating `moonshotai/Kimi-Linear-48B-A3B-Instruct`
on large-memory GPUs, especially Blackwell RTX PRO 6000 class machines, without
CPU offload.

## Build

```bash
docker build \
  -f docker/kimi-linear-cu13.Dockerfile \
  -t ghcr.io/OWNER/sglang-kimi-cu13:latest \
  .
```

Use the SGLang CUDA 13 development image instead of the stable CUDA 13 image if
needed:

```bash
docker build \
  --build-arg SGLANG_BASE_IMAGE=lmsysorg/sglang:dev-cu13 \
  -f docker/kimi-linear-cu13.Dockerfile \
  -t ghcr.io/OWNER/sglang-kimi-cu13:dev-cu13 \
  .
```

## Push

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u OWNER --password-stdin
docker push ghcr.io/OWNER/sglang-kimi-cu13:latest
```

The GitHub token needs `write:packages`. If the platform cannot pull private
images, make the GHCR package public or configure registry credentials in the
platform.

## Runtime Check

Inside the cloud container:

```bash
kimi-linear-env-check
```

Verify that:

- `torch.cuda.is_available()` is true.
- both RTX PRO 6000 GPUs are visible.
- SGLang imports successfully.
- the image uses a CUDA 13 capable stack.

## Launch Kimi Linear

Prefer a mounted/persistent model directory instead of baking model weights into
the image.

```bash
python3 -m sglang.launch_server \
  --model-path /models/Kimi-Linear-48B-A3B-Instruct \
  --tp 2 \
  --trust-remote-code
```

Or download from Hugging Face at launch time:

```bash
python3 -m sglang.launch_server \
  --model moonshotai/Kimi-Linear-48B-A3B-Instruct \
  --tp 2 \
  --trust-remote
```

Do not add CPU offload or local patched `kimi_linear.py` when validating the
official full-GPU path.

## GSM8K Smoke Test

```bash
python3 benchmark/gsm8k/bench_sglang.py \
  --num-questions 8 \
  --start-index 280 \
  --parallel 8 \
  --num-shots 5
```

If the full-GPU path is healthy, outputs should not repeatedly continue with
lowercase `question:` until `max_new_tokens`.
