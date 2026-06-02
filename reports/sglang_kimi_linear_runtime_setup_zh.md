# SGLang Kimi Linear 运行配置与失败路径记录

日期：2026-06-02

## 结论

当前在 2 张 A100-SXM4-40GB 上，`Kimi-Linear-48B-A3B-Instruct` 不能以纯 GPU bf16 方式完整加载。已经跑通的路径是：

- 使用官方稳定 Docker 镜像：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 使用本地 checkpoint：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`
- 使用 tensor parallel：`--tp-size 2`
- 使用 bf16：`--dtype bfloat16`
- 使用 Kimi Linear 的 triton linear attention：`--linear-attn-backend triton`
- 使用 SGLang V2 CPU offload，把 Kimi MoE expert 权重放到 CPU：
  - `--offload-group-size 1`
  - `--offload-num-in-group 1`
  - `--offload-mode cpu`
- 关闭 CUDA graph：
  - `--disable-cuda-graph`
  - `--disable-piecewise-cuda-graph`

这一路径已经通过：

- `/health`
- `/model_info`
- OpenAI-compatible `/v1/completions`
- 一个短 prompt smoke test

## 版本与环境

- SGLang 源码快照：`22043b917bd2e37a427ad334d78b59cd7e3a8079`
- 本地分支：`research/kimi-linear-gsm8k`
- Docker 镜像：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 容器内 SGLang：`0.5.12.post1`
- 容器内 PyTorch：`2.11.0+cu129`
- CUDA runtime：12.9.1
- GPU：2 x NVIDIA A100-SXM4-40GB
- 模型路径：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`

## Kimi Linear 支持位置

- 模型实现：`python/sglang/srt/models/kimi_linear.py`
- 配置实现：`python/sglang/srt/configs/kimi_linear.py`
- KDA/linear attention backend：`python/sglang/srt/layers/attention/linear/kda_backend.py`
- 文档索引：`docs/supported_models/text_generation/generative_models.md`

相关官方 PR：`https://github.com/sgl-project/sglang/pull/12469`

PR 中已合入 Kimi Linear 官方支持，并给出了 `trust_remote_code`、TP 和 GSM8K benchmark 示例；该示例不是 2 x A100 40GB 的 CPU offload 配方。

## 当前可运行启动命令

```bash
sg docker -c 'docker run --rm --gpus all --ipc=host --network=host --shm-size 64g \
  --name sglang-kimi-zyx \
  --user "$(id -u):$(id -g)" \
  -e CUDA_VISIBLE_DEVICES=0,1 \
  -e HOME=/workspace/sglang-kimi-deferral \
  -e PYTHONUSERBASE=/workspace/sglang-kimi-deferral/.cache/pyuser \
  -e HF_HOME=/workspace/sglang-kimi-deferral/.cache/huggingface \
  -e TORCHINDUCTOR_CACHE_DIR=/workspace/sglang-kimi-deferral/.cache/torchinductor \
  -v /etc/passwd:/etc/passwd:ro \
  -v /etc/group:/etc/group:ro \
  -v /data/zyx/sglang-kimi-deferral/python/sglang/srt/models/kimi_linear.py:/sgl-workspace/sglang/python/sglang/srt/models/kimi_linear.py:ro \
  -v /data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct:/models/Kimi-Linear-48B-A3B-Instruct:ro \
  -v /data/zyx/sglang-kimi-deferral:/workspace/sglang-kimi-deferral \
  lmsysorg/sglang:v0.5.12.post1-cu129-runtime \
  bash -lc '"'"'python3 -m sglang.launch_server \
    --model-path /models/Kimi-Linear-48B-A3B-Instruct \
    --tp-size 2 \
    --trust-remote-code \
    --dtype bfloat16 \
    --offload-group-size 1 \
    --offload-num-in-group 1 \
    --offload-mode cpu \
    --host 0.0.0.0 \
    --port 30000 \
    --mem-fraction-static 0.20 \
    --max-total-tokens 32768 \
    --max-running-requests 8 \
    --linear-attn-backend triton \
    --disable-cuda-graph \
    --disable-piecewise-cuda-graph \
    2>&1 | tee /workspace/sglang-kimi-deferral/logs/kimi_linear_sglang_server_docker_v2offload_no_graph_patch.log'"'"''
```

本机访问 `127.0.0.1:30000` 时必须绕过 HTTP proxy，否则请求会被发到代理，出现 502：

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
```

## 当前保留的最小代码改动

### Kimi Linear V2 offload 接入

文件：`python/sglang/srt/models/kimi_linear.py`

给 `make_layers(...)` 增加 `offloader_kwargs`，按 DeepSeek 类似路径只 offload `KimiMoE` 中的 `FusedMoE` expert 权重：

- `w13_weight`
- `w2_weight`
- 如果存在 blockscale tensor，也纳入白名单

这使得 `--offload-group-size/--offload-num-in-group/--offload-mode cpu` 能作用于 Kimi Linear 的 MoE expert，而不是只加载后仍把主要权重留在 GPU。

V1 offload 调试期间尝试过 `offloader.py` 临时 workaround，但该路径最终仍 OOM，不作为当前可运行方案，也不保留进当前代码基线。

## 当前运行时内存状态

服务端日志中的关键记录：

- load weight elapsed：约 112 秒
- 模型类型：`KimiLinearForCausalLM`
- weight load 后 GPU mem usage：约 2.39GB/TP rank
- Mamba cache：
  - conv_state：约 0.01GB
  - ssm_state：约 0.18GB
- KV cache：
  - `max_total_tokens=32768`
  - KV size：约 0.25GB
- 启动后 available GPU memory：约 35.70GB
- GSM8K 请求运行中观测 GPU：
  - GPU0：约 8186MiB，utilization 100%
  - GPU1：约 8186MiB，utilization 100%

这说明 V2 experts-only CPU offload 后显存占用很低，但吞吐受 CPU/GPU 权重搬运影响明显。

## 可用 smoke test 结果

请求：

```text
Question: What is 2 + 3? Answer:
```

响应状态：HTTP 200

模型输出片段：

```text
5
```

usage：

```json
{"prompt_tokens":12,"completion_tokens":32,"total_tokens":44}
```

## 尝试失败的配置与问题

### 1. 纯 GPU bf16，TP=2

代表配置：

```bash
--tp-size 2
--dtype bfloat16
--trust-remote-code
--mem-fraction-static 0.20
```

结果：失败。

问题：模型 safetensors 总量约 91.5GiB，2 x A100 40GB 无法容纳完整 bf16 权重。即使把 `mem_fraction_static` 调低，模型构建阶段仍然 CUDA OOM。

### 2. V1 CPU offload：`--cpu-offload-gb 80`

代表配置：

```bash
--cpu-offload-gb 80
--tp-size 2
--dtype bfloat16
--mem-fraction-static 0.75
```

结果：失败。

问题一：CUDA graph capture 阶段报 tied weights 错误：

```text
functional_call got multiple values for keys ['self_attn.A_log', 'self_attn.attn.A_log'], which are tied.
```

加 `--disable-cuda-graph` 后，首次 forward 仍会触发同类问题，因此需要在 V1 offloader 中设置 `tie_weights=False`。

问题二：修补 tied weights 后，MoE topk 报 correction bias device mismatch。原因是 `topk_config.correction_bias` 没随 offloaded module state 一起搬到 GPU。

问题三：继续修补 correction bias 后，仍然在首次 forward/onload 时 OOM。不同参数下均遇到类似问题：

- `--cpu-offload-gb 20`：onload 约 1.12GiB 时 OOM
- `--cpu-offload-gb 40 --mem-fraction-static 0.55`：onload 约 1.12GiB 时 OOM
- `--cpu-offload-gb 80 --mem-fraction-static 0.55`：onload 约 576MiB 时 OOM
- `--cpu-offload-gb 80 --mem-fraction-static 0.20 --max-total-tokens 32768 --max-running-requests 8`：仍在 onload 约 576MiB 时 OOM

判断：V1 `--cpu-offload-gb` 对 Kimi Linear 这类模型的 offload/onload 粒度过粗，在 2 x 40GB 上不是当前合适路径。

### 3. V2 CPU offload 但未关闭 piecewise CUDA graph

代表配置：

```bash
--offload-group-size 1
--offload-num-in-group 1
--offload-mode cpu
--disable-cuda-graph
```

结果：失败。

问题：piecewise CUDA graph/torch compile 路径报错：

```text
AssertionError: cannot extract sympy expressions from <torch.cuda.Stream ...>
```

解决：额外增加：

```bash
--disable-piecewise-cuda-graph
```

### 4. 本地 Python venv 路径

结果：不作为当前方案。

问题：本地环境里 torch、CUDA、`sglang-kernel` ABI 版本组合不稳定；服务器是 CUDA 12.9，官方 cu129 runtime 镜像更直接，且与 SGLang 发布版本匹配。

### 5. Docker 镜像选择

尝试方向：

- 查找官方 A100 + CUDA 12.9 可用 runtime 镜像
- 拉取稳定版 `lmsysorg/sglang:v0.5.12.post1-cu129-runtime`

结果：成功。

未继续拉 nightly：按要求，稳定镜像拉取完成后直接测试，不再拉 nightly。

## 当前 blocker

- 可运行路径依赖本地最小 patch：Kimi Linear 需要显式接入 V2 offloader 的 `offloader_kwargs`。
- 性能很慢：当前 CPU offload 运行 GSM8K 单请求可达几十秒级。
- 本地代理环境会影响 `127.0.0.1:30000` 请求，必须设置 `NO_PROXY/no_proxy` 或在评测脚本中禁用 proxy。
- Docker 镜像占用根分区空间较大；后续不要额外拉大镜像，输出和缓存应继续放在 `/data/zyx/sglang-kimi-deferral`。

## 下一步建议

1. 先用当前可运行配置完成 GSM8K `limit=8`，记录 accuracy、throughput、latency 和每题输出。
2. 如果 `limit=8` 稳定完成，再跑 `limit=32`。
3. 第二份报告单独记录 GSM8K 指标和人工审核输出路径。
4. output deferral 后续应基于当前 V2 CPU offload 路径迁移，避免依赖 V1 `--cpu-offload-gb` 路径。
