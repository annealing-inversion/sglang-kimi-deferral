# SGLang Kimi Linear GSM8K 5-shot + Stop Strings 测试报告

日期：2026-06-02

## 结论

本轮测试改用 5-shot GSM8K prompt，并加入 stop strings 后，输出质量明显改善：

- 未再观察到串到下一题的问题。
- 大多数样本能以 `#### answer` 格式正常停止。
- 连续样本 `idx=8..35` 共 28 题，数值 exact match 为 `19/28 = 0.679`。
- 输出吞吐仍低，约 `0.68 output token/s`，瓶颈仍是 2 x A100 40GB 下的 CPU offload。

准确率仍低于官方约 `0.895`，但已经明显高于 zero-shot/no-stop 的 smoke 结果。当前主要剩余问题是：

- 2 卡 CPU offload 速度慢；
- 仍有算错题；
- `max_new_tokens=256` 对少数题不够，建议后续默认用 `512`；
- 仍未复现官方 `tp=4` 全 GPU/高并发环境。

## 运行配置

服务端配置：

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

镜像：

```text
lmsysorg/sglang:v0.5.12.post1-cu129-runtime
```

显存：

- 权重加载后：约 `14.17GB/TP rank`
- 运行请求时：约 `18.3GB/GPU`
- GPU 利用率：请求运行时约 `100%`

## Prompt 与 Stop

本轮使用官方 GSM8K benchmark 的 5-shot prompt 结构：

```text
Question: ...
Answer: ... #### ...

...

Question: target question
Answer:
```

Stop strings 使用官方 stop 的基础上增加大小写变体：

```text
Question
question
Question:
question:
Assistant:
assistant:
<|separator|>
```

加入 lowercase stop 的原因：早前输出会生成 `question:` 小写形式，官方只含 `Question` 时不能拦截这类串题。

## 评测脚本变更

文件：`benchmark/gsm8k/kimi_sglang_eval.py`

新增能力：

- `--start-index`
- `--num-shots`
- 多个 `--stop`
- 记录 `finish_reason`
- 记录是否 `hit_max_tokens`
- 记录是否疑似串到下一题：`looks_like_next_question`
- 数值比较答案，避免 `26.00` 和 `26` 被误判为不同

## 分段结果

### idx=8..11, limit=4, max_new_tokens=256

输出文件：

```text
outputs/gsm8k/kimi_sglang_5shot_stop_idx8_limit4.jsonl
```

结果：

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 4 |
| 数值 exact match | 3 / 4 |
| accuracy | 0.750 |
| hit max tokens | 0 |
| 串题 | 0 |
| completion tokens | 404 |
| prompt tokens | 2947 |
| latency sum | 593.154 s |
| output throughput | 0.681 token/s |

观察：4 题都正常 stop，没有截断和串题，因此继续跑较大样本。

### idx=12..27, limit=16, max_new_tokens=256

输出文件：

```text
outputs/gsm8k/kimi_sglang_5shot_stop_idx12_limit16.jsonl
```

结果：

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 16 |
| 数值 exact match | 9 / 16 |
| accuracy | 0.5625 |
| hit max tokens | 1 |
| 串题 | 0 |
| completion tokens | 1581 |
| prompt tokens | 11549 |
| latency sum | 2324.426 s |
| output throughput | 0.680 token/s |

观察：`idx=19` 触发 `finish_reason=length`，说明 `max_new_tokens=256` 对少数题不够。没有观察到串题。

### idx=28..35, limit=8, max_new_tokens=512

输出文件：

```text
outputs/gsm8k/kimi_sglang_5shot_stop_idx28_limit8_mt512.jsonl
```

结果：

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 8 |
| 数值 exact match | 7 / 8 |
| accuracy | 0.875 |
| hit max tokens | 0 |
| 串题 | 0 |
| completion tokens | 552 |
| prompt tokens | 5707 |
| latency sum | 814.195 s |
| output throughput | 0.678 token/s |

观察：将 `max_new_tokens` 提到 512 后，这 8 题没有截断；由于 stop 生效，实际输出长度没有无意义膨胀。

## 合并结果

合并连续样本 `idx=8..35`：

| 指标 | 数值 |
| --- | ---: |
| 样本数 | 28 |
| 数值 exact match | 19 / 28 |
| accuracy | 0.679 |
| hit max tokens | 1 |
| 串题 | 0 |
| completion tokens | 2537 |
| prompt tokens | 20203 |
| latency sum | 3731.775 s |
| requests/s | 0.00750 |
| output throughput | 0.680 token/s |

## 与之前结果对比

之前 zero-shot/no-stop 的 `limit=8`：

- strict exact match：`0.000`
- flexible exact match：`0.375`
- 多个样本复读或打满 256 tokens
- output throughput：约 `0.522 token/s`

本轮 5-shot + stop：

- 连续 28 题 accuracy：`0.679`
- 串题：`0`
- 只有 1 条在 256 上限截断；512 补充段无截断
- output throughput：约 `0.680 token/s`

因此，质量问题的一大部分来自 prompt/stop 设置，而不是模型完全不能做 GSM8K。

## 当前仍未解决的问题

1. 吞吐仍远低于官方。
   当前是 2 卡 CPU offload，decode 约 `0.68 token/s`；官方是 `tp=4` 且高并发，不能直接对比。

2. 准确率仍低于官方。
   本轮 28 题为 `0.679`，低于 PR 中约 `0.895`。可能原因包括 CPU offload 数值路径、关闭 CUDA graph、未复现官方 full-GPU/TP=4、以及当前样本量较小。

3. 仍有个别输出较长。
   `max_new_tokens=256` 出现 1 条截断。后续建议默认 `512`。

4. EOS/tokenizer 仍需核对。
   日志显示 tokenizer EOS ID 为 `163585`，而本地配置中有 `eos_token_id=163586`。虽然 stop strings 已经避免串题，但 EOS 不一致仍值得单独确认。

## 下一步建议

1. 后续 GSM8K 默认使用：
   - `--num-shots 5`
   - `--max-new-tokens 512`
   - 当前 stop strings 列表

2. 若继续评测，应从 `idx=36` 开始顺着跑，避免重复样本。

3. 如果要追官方吞吐和准确率，优先争取 4 卡全 GPU `--tp 4`，而不是继续微调 2 卡 CPU offload。

4. 单独验证 SGLang Kimi Linear CPU offload 数值是否与 HF/reference 一致，尤其是 MoE expert offload 后的 logits/短生成一致性。
