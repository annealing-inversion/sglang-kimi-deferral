# SGLang Kimi Linear GSM8K 5shot 鲁棒 stop 320 样本测试

日期：2026-06-03 UTC

## 结论

本轮按 64 样本一个块，连续跑 5 块，共 320 个 GSM8K test 样本，范围为 `idx=280..599`。配置沿用前面验证稳定的 5shot、`parallel=4`、`max_new_tokens=512` 和大小写鲁棒 stop strings。

总体结果：

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 320 |
| strict exact match | 209/320 = 0.653125 |
| flexible exact match | 208/320 = 0.650000 |
| error count | 0 |
| hit max tokens | 6/320 |
| 串到下一题 | 0/320 |
| 总 wall time | 11688.97 s = 3.25 h |
| requests/s | 0.0274 |
| completion tokens | 29047 |
| prompt tokens | 232121 |
| completion tokens/s | 2.485 |
| 平均单请求 latency | 139.95 s |
| latency 范围 | 36.54 s 到 781.02 s |

本轮说明鲁棒 stop 后，串题问题基本被压住；剩余主要问题是少量样本仍会复读或长推理直到 512 token 上限，以及 CPU offload 路径吞吐很低。

## 版本与运行环境

- SGLang repo commit：`a689bb8` (`Evaluate Kimi GSM8K robust stop batch`)
- Docker image：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 模型：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`
- 模型容器路径：`/models/Kimi-Linear-48B-A3B-Instruct`
- Kimi Linear 实现：`python/sglang/srt/models/kimi_linear.py`
- GPU：2 x A100 40G
- 观测显存：约 `19810 MiB / 40960 MiB` 每卡
- 观测 GPU 利用率：运行期间多数时间为 100%
- CPU offload：使用，参数见下方启动命令

## 启动命令

服务端命令：

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
  --disable-piecewise-cuda-graph \
  --disable-custom-all-reduce
```

评测命令模板：

```bash
python3 benchmark/gsm8k/kimi_sglang_eval.py \
  --data-path outputs/gsm8k/gsm8k_test.jsonl \
  --url http://127.0.0.1:30000 \
  --model /models/Kimi-Linear-48B-A3B-Instruct \
  --start-index START \
  --limit 64 \
  --parallel 4 \
  --num-shots 5 \
  --max-new-tokens 512 \
  --request-timeout 1800 \
  --extract-mode official \
  --stop Question \
  --stop Question: \
  --stop question \
  --stop question: \
  --stop Assistant: \
  --stop assistant: \
  --stop "<|separator|>" \
  --output outputs/gsm8k/kimi_sglang_5shot_stop_idxSTART_limit64_p4_mt512_robuststop.jsonl
```

注意：本轮继续使用大小写鲁棒 stop。之前只用 `Question` / `Assistant:` / `<|separator|>` 时，模型会输出小写 `question:`，导致大量样本 hit max tokens 和串题。

## 分块结果

| start idx | strict | flexible | hit max | 串题 | wall time s | requests/s | completion tok/s | completion tokens | 输出文件 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 280 | 42/64 = 0.65625 | 42/64 = 0.65625 | 1 | 0 | 2450.72 | 0.0261 | 2.509 | 6150 | `outputs/gsm8k/kimi_sglang_5shot_stop_idx280_limit64_p4_mt512_robuststop.jsonl` |
| 344 | 41/64 = 0.640625 | 41/64 = 0.640625 | 1 | 0 | 2230.71 | 0.0287 | 2.494 | 5563 | `outputs/gsm8k/kimi_sglang_5shot_stop_idx344_limit64_p4_mt512_robuststop.jsonl` |
| 408 | 38/64 = 0.59375 | 38/64 = 0.59375 | 1 | 0 | 2607.62 | 0.0245 | 2.335 | 6088 | `outputs/gsm8k/kimi_sglang_5shot_stop_idx408_limit64_p4_mt512_robuststop.jsonl` |
| 472 | 43/64 = 0.671875 | 43/64 = 0.671875 | 2 | 0 | 2200.79 | 0.0291 | 2.574 | 5664 | `outputs/gsm8k/kimi_sglang_5shot_stop_idx472_limit64_p4_mt512_robuststop.jsonl` |
| 536 | 45/64 = 0.703125 | 44/64 = 0.6875 | 1 | 0 | 2199.13 | 0.0291 | 2.538 | 5582 | `outputs/gsm8k/kimi_sglang_5shot_stop_idx536_limit64_p4_mt512_robuststop.jsonl` |

对应 summary 文件：

- `outputs/gsm8k/kimi_sglang_5shot_stop_idx280_limit64_p4_mt512_robuststop.summary.json`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx344_limit64_p4_mt512_robuststop.summary.json`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx408_limit64_p4_mt512_robuststop.summary.json`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx472_limit64_p4_mt512_robuststop.summary.json`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx536_limit64_p4_mt512_robuststop.summary.json`

## hit max 样本

本轮 hit max tokens 的题号：

- `idx=303`
- `idx=369`
- `idx=464`
- `idx=493`
- `idx=499`
- `idx=577`

这些样本没有串到下一题，但输出达到 `max_new_tokens=512`，会拖慢对应块的尾部 latency。后续加速或质量调试时应优先人工查看这些输出，判断是 stop string 仍缺少某种形式，还是模型本身在题目上进入复读/长推理。

## 当前问题

1. 吞吐仍很低：总 completion throughput 约 2.49 token/s，远低于官方 4 卡全 GPU 高并发结果。当前瓶颈基本是 CPU offload 路径，而不是 GPU 空闲；观测 GPU util 多数时间为 100%，但 offload 导致有效解码速度低。
2. CPU offload 是必要配置：两张 A100 40G 下当前模型不能按全 GPU 常规方式放下，使用 `--offload-group-size 4 --offload-num-in-group 3 --offload-mode cpu` 才能稳定运行。
3. CUDA graph 仍关闭：之前 CPU offload 路径打开 CUDA graph 会触发 capture 相关错误，因此本轮保留 `--disable-cuda-graph --disable-piecewise-cuda-graph`。
4. 少量样本仍 hit max：320 个样本中 6 个到达 512 token 上限。鲁棒 stop 已解决小写 `question:` 串题，但不能完全避免长推理/复读。

## 下一步建议

1. 先人工审查 6 个 hit max 输出，确认是否有新的 stop 模式可以稳定加入；如果只是模型长推理，不应为了少数样本过度加 stop。
2. 如果要继续提速，优先考虑增加可用 GPU 或找到官方支持的更少 offload 配置；在当前 2 x A100 40G + CPU offload 下，调高并发只会增加尾部排队和内存压力，未必提高有效吞吐。
3. 迁移 output deferral 前，应固定当前鲁棒 stop 设置和评测脚本，避免 deferral 变更与 prompt/stop 问题混在一起。
