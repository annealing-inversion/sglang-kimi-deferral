# SGLang Kimi Linear GSM8K 5-shot Stop 测试报告

## 基本信息

- 日期：2026-06-03
- 仓库 commit：`494eb7b`
- Docker 镜像：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 模型路径：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`
- SGLang Kimi Linear 实现：`python/sglang/srt/models/kimi_linear.py`
- 数据文件：`outputs/gsm8k/gsm8k_test.jsonl`
- 评测脚本：`benchmark/gsm8k/kimi_sglang_eval.py`

## Server 配置

```bash
python3 -m sglang.launch_server \
  --model-path /models/Kimi-Linear-48B-A3B-Instruct \
  --tp-size 2 \
  --trust-remote-code \
  --dtype bfloat16 \
  --offload-group-size 4 \
  --offload-num-in-group 3 \
  --offload-mode cpu \
  --host 0.0.0.0 \
  --port 30000 \
  --mem-fraction-static 0.60 \
  --max-total-tokens 8192 \
  --max-running-requests 4 \
  --linear-attn-backend triton \
  --disable-cuda-graph \
  --disable-piecewise-cuda-graph
```

- 使用 CPU offload：是，V2 offload，`offload_group_size=4`、`offload_num_in_group=3`、`offload_mode=cpu`
- CUDA graph：关闭。打开 CUDA graph 和最小 `--cuda-graph-max-bs 1` 都在 capture 阶段因 offloader 跨 stream event 失败。
- GPU 显存：运行中约 `19842 MiB / 40960 MiB` 每卡。
- GPU 利用率：评测期间两卡多数时间为 `100%`。
- server 日志：`logs/kimi_linear_sglang_server_docker_v2offload_g4n3_m060_t8192_run32.log`

## 评测配置

两组都使用同一配置：

```bash
python3 benchmark/gsm8k/kimi_sglang_eval.py \
  --data-path outputs/gsm8k/gsm8k_test.jsonl \
  --limit 32 \
  --parallel 4 \
  --num-shots 5 \
  --max-new-tokens 512 \
  --extract-mode number \
  --stop Question \
  --stop question \
  --stop Question: \
  --stop question: \
  --stop Assistant: \
  --stop assistant: \
  --stop "<|separator|>"
```

说明：这次使用自定义逐题记录脚本，而不是官方 `benchmark/gsm8k/bench_sglang.py` frontend。原因是官方脚本只有在全部 `run_batch` 结束后才写 raw result；中途观察和分段测试时不方便保留每题 prompt/output。prompt 格式、5-shot 示例和 stop string 沿用前面调试出的稳定配置。

## 结果

| 范围 | 样本数 | Strict EM | Flexible EM | Wall time | Requests/s | Completion toks/s | Completion tokens | Hit max | 串到下一题 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `idx=68..99` | 32 | 26/32 = 0.8125 | 26/32 = 0.8125 | 1056.96s | 0.0303 | 2.491 | 2633 | 0 | 0 |
| `idx=100..131` | 32 | 21/32 = 0.65625 | 21/32 = 0.65625 | 975.59s | 0.0328 | 2.549 | 2487 | 0 | 0 |
| 合并 | 64 | 47/64 = 0.734375 | 47/64 = 0.734375 | 2032.55s | 0.0315 | 2.519 | 5120 | 0 | 0 |

逐题输出文件：

- `outputs/gsm8k/kimi_sglang_5shot_stop_idx68_limit32_p4_mt512.jsonl`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx100_limit32_p4_mt512.jsonl`

summary 文件：

- `outputs/gsm8k/kimi_sglang_5shot_stop_idx68_limit32_p4_mt512.summary.json`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx100_limit32_p4_mt512.summary.json`

stdout 文件：

- `outputs/gsm8k/kimi_sglang_5shot_stop_idx68_limit32_p4_mt512_stdout.log`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx100_limit32_p4_mt512_stdout.log`

## 输出质量观察

- 两组所有样本 `finish_reason` 都是 `stop`。
- `hit_max_tokens=0`，没有样本打满 `max_new_tokens=512`。
- `looks_like_next_question=0`，没有检测到串到下一题。
- 第一组平均 completion tokens 为 `82.28`，最大 `155`。
- 第二组平均 completion tokens 为 `77.72`，最大 `159`。

错误样本：

- `idx=68..99`：错 6 题，错误 idx 为 `73, 75, 87, 91, 98, 99`。
- `idx=100..131`：错 11 题，错误 idx 为 `100, 101, 107, 114, 115, 118, 119, 120, 124, 126, 129`。

## 性能结论

- `parallel=4` 与 server `max_running_requests=4` 匹配，运行中队列基本不堆积。
- 与此前官方 stop 单独使用相比，扩展 stop strings 后没有再出现打满 512 或串题，输出长度显著可控。
- 吞吐仍只有约 `2.5 completion token/s`，主要瓶颈仍是两卡 A100 40G 下的 CPU offload。CUDA graph 在当前 offload 路径不可用，不是可行提速点。

## 当前 blocker 和下一步

- 主要 blocker：CPU offload 导致 decode 吞吐很低，无法接近官方 TP4 全 GPU benchmark 的几千 token/s。
- 可继续测试：
  - 将 `max_running_requests` 从 4 调到 6，客户端 `parallel=6/8`，观察 token usage、OOM 和吞吐。
  - 生成 A100 MoE kernel config，减少当前日志中的默认 MoE kernel 警告。
  - 若有 4 卡或更大显存环境，优先尝试无 CPU offload、开启 CUDA graph 的官方路径。
  - 后续迁移 output deferral 时，应保持当前 5-shot prompt、stop string 和逐题记录格式，先在小样本上验证不串题、不 hit max。
