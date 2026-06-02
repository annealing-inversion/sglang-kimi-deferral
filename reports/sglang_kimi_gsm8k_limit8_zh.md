# SGLang Kimi Linear GSM8K limit=8 评测报告

日期：2026-06-02

## 结论

本次只完成 GSM8K `limit=8`，未继续跑 `limit=32` 或其他测试。

当前配置能端到端跑通，但性能远低于官方 PR 中的吞吐数据。主要原因不是 CUDA 12.9 runtime 本身，而是运行条件不同：

- 官方命令是 `--tp 4`，高概率是 4 卡全 GPU 权重常驻。
- 官方 benchmark 是 `--parallel 1319`，大量请求并发，能充分利用 SGLang batching。
- 当前环境只有 2 x A100 40GB，bf16 权重无法全 GPU 常驻，被迫走 CPU offload。
- 当前 eval 脚本是串行 1 请求，`#running-req: 1`，没有形成有效 batch。
- 当前为了绕过 V2 offload 的 graph/compile 问题，关闭了 CUDA graph 和 piecewise CUDA graph。
- 当前 CPU offload 每步都要搬运 MoE expert 权重，decode 阶段服务端日志显示约 `0.5 token/s`。

因此，官方 `2755 token/s` 和当前 `0.522 token/s` 不是同一硬件/placement/batching 条件下的结果，不能直接对比。

## 运行配置

- Docker 镜像：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 容器内 SGLang：`0.5.12.post1`
- CUDA runtime：12.9.1
- GPU：2 x NVIDIA A100-SXM4-40GB
- 模型：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`
- dtype：`bfloat16`
- TP：`--tp-size 2`
- attention backend：`--linear-attn-backend triton`
- CPU offload：
  - `--offload-group-size 1`
  - `--offload-num-in-group 1`
  - `--offload-mode cpu`
- CUDA graph：
  - `--disable-cuda-graph`
  - `--disable-piecewise-cuda-graph`
- token/cache 限制：
  - `--max-total-tokens 32768`
  - `--max-running-requests 8`
  - `--mem-fraction-static 0.20`

服务端日志：

- `logs/kimi_linear_sglang_server_docker_v2offload_no_graph_patch.log`

## 评测命令

```bash
python3 benchmark/gsm8k/kimi_sglang_eval.py \
  --arrow /host_hf_datasets/openai___gsm8k/main/0.0.0/740312add88f781978c0658806c59bc2815b9866/gsm8k-test.arrow \
  --limit 8 \
  --max-new-tokens 256 \
  --output outputs/gsm8k/kimi_sglang_limit8.jsonl
```

实际是在 Docker 容器中运行，并设置：

```bash
NO_PROXY=127.0.0.1,localhost
no_proxy=127.0.0.1,localhost
```

原因：本机环境存在 HTTP proxy；如果不绕过 `127.0.0.1:30000`，OpenAI-compatible API 请求会被错误转发到代理并返回 502。

## 输出文件

- 每题人工审核 JSONL：`outputs/gsm8k/kimi_sglang_limit8.jsonl`
- 汇总 JSON：`outputs/gsm8k/kimi_sglang_limit8.summary.json`

## 汇总指标

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 8 |
| strict exact_match | 0.000 |
| flexible exact_match | 0.375 |
| strict correct | 0 / 8 |
| flexible correct | 3 / 8 |
| wall time | 1349.323 s |
| requests/s | 0.00593 |
| prompt tokens | 468 |
| completion tokens | 705 |
| total tokens | 1173 |
| output throughput | 0.522 token/s |
| 平均单题 latency | 168.665 s |

## 逐题结果

| idx | gold | strict extracted | flexible extracted | strict | flexible | latency s | prompt toks | completion toks |
| ---: | ---: | --- | ---: | --- | --- | ---: | ---: | ---: |
| 0 | 18 | null | 18 | false | true | 40.112 | 66 | 21 |
| 1 | 3 | null | 3 | false | true | 55.019 | 30 | 28 |
| 2 | 70000 | null | 120000 | false | false | 23.058 | 53 | 11 |
| 3 | 540 | null | 180 | false | false | 77.726 | 38 | 40 |
| 4 | 20 | null | 20 | false | true | 15.267 | 111 | 7 |
| 5 | 64 | null | 104 | false | false | 164.834 | 56 | 86 |
| 6 | 260 | null | 20 | false | false | 486.663 | 45 | 256 |
| 7 | 160 | null | 200 | false | false | 486.640 | 69 | 256 |

## 观测到的性能特征

服务端日志显示，本次评测全程基本是单请求串行：

```text
#running-req: 1
cuda graph: False
gen throughput (token/s): 0.50-0.53
```

运行时 GPU 显存观测：

```text
GPU0: about 8186 MiB / 40960 MiB
GPU1: about 8186 MiB / 40960 MiB
```

GPU utilization 在请求运行时可到 100%，但显存占用很低。这符合 CPU offload 场景：模型大部分 expert 权重不常驻 GPU，瓶颈变成 CPU/GPU 搬运和逐 token onload，而不是 GPU 显存容量。

## 为什么比官方吞吐低

官方 PR 给出的命令：

```bash
python3 -m sglang.launch_server \
  --model moonshotai/Kimi-Linear-48B-A3B-Instruct \
  --tp 4 \
  --trust-remote

python3 benchmark/gsm8k/bench_sglang.py \
  --num-questions 1319 \
  --parallel 1319
```

官方结果：

```text
Accuracy: 0.895
Invalid: 0.000
Latency: 46.696 s
Output throughput: 2755.147 token/s
```

与当前实验差异：

| 项目 | 官方 PR | 当前实验 |
| --- | --- | --- |
| TP | 4 | 2 |
| 权重 placement | 预计全 GPU 常驻 | CPU offload |
| 并发 | 1319 | 1 |
| CUDA graph | 未显式关闭 | 已关闭 |
| 评测脚本 | SGLang 官方 benchmark，高并发 | 自定义逐题串行，保留每题输出 |
| 输出吞吐 | 2755.147 token/s | 0.522 token/s |

最大差异是 CPU offload 和并发。即使模型能跑，当前配置也不是吞吐优化配置。

## 加速方向

后续应优先按下面顺序处理，而不是继续扩大 GSM8K：

1. 尽量获得 4 张 40GB 或更大显存 GPU，复现官方 `--tp 4 --trust-remote` 的全 GPU 路径。
2. 如果仍只有 2 张 A100 40GB，确认是否能用更低精度或官方支持的量化权重让模型全 GPU 常驻；不要手写模型结构转换。
3. 在不改变 placement 的情况下，改评测脚本支持并发请求，至少让 SGLang scheduler 看到多个 pending/running requests；当前串行请求无法体现 server throughput。
4. 重新尝试打开 CUDA graph/piecewise CUDA graph，但必须先解决 V2 offload 触发的 torch compile stream/sympy 报错。
5. 检查是否存在官方 MoE kernel config 缺失导致的性能损失；日志提示 A100 对应 fused MoE config 不存在，当前使用默认配置。
6. 优化 prompt/template 和 stop 条件，减少模型复读打满 `max_new_tokens=256` 的情况；本次有两题打满 256 tokens，显著拉低吞吐和正确率。

## 当前不建议做的事

- 不建议继续用 V1 `--cpu-offload-gb` 路径；它已经遇到 tied weights、topk correction bias device mismatch 和 onload OOM。
- 不建议为了兼容本地 Python 环境去降级/转译 SGLang；官方 cu129 runtime 已经能运行。
- 不建议直接把当前串行 limit=8 的 throughput 与官方高并发 full benchmark 对齐比较。

## 下一步

先暂停继续测试，集中解决吞吐问题。最有价值的下一步是判断能否让权重全 GPU 常驻；如果做不到，再单独做并发评测脚本和 CUDA graph/offload 性能排查。
