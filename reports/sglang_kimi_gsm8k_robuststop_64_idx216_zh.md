# SGLang Kimi Linear GSM8K 64 样本评测（鲁棒 stop）

## 配置

- 模型：`/data/zyx/huggingface/Kimi-Linear-48B-A3B-Instruct`
- SGLang Docker：`lmsysorg/sglang:v0.5.12.post1-cu129-runtime`
- 启动参数：`tp-size=2`，`dtype=bfloat16`，`linear-attn-backend=triton`
- CPU offload：`--offload-group-size 4 --offload-num-in-group 3 --offload-mode cpu`
- 显存参数：`--mem-fraction-static 0.60 --max-total-tokens 8192 --max-running-requests 4`
- CUDA graph：关闭，`--disable-cuda-graph --disable-piecewise-cuda-graph`
- custom all-reduce：关闭，`--disable-custom-all-reduce`
- 评测：5-shot，`parallel=4`，`max_new_tokens=512`，`temperature=0`
- stop strings：`Question`, `Question:`, `question`, `question:`, `Assistant:`, `assistant:`, `<|separator|>`

## 结果

样本范围：`idx216..279`，共 64 题，拆成 4 个 16 样本块运行。

| start index | 样本数 | strict | flexible | wall time | completion tok/s | hit max | nextq |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 216 | 16 | 14/16 | 14/16 | 610.64s | 2.153 | 0 | 0 |
| 232 | 16 | 10/16 | 10/16 | 544.89s | 2.200 | 0 | 0 |
| 248 | 16 | 11/16 | 9/16 | 534.58s | 2.374 | 0 | 0 |
| 264 | 16 | 14/16 | 13/16 | 704.65s | 2.153 | 0 | 0 |

总体：

- strict exact match：49/64 = 0.765625
- flexible exact match：46/64 = 0.71875
- finish reason：64/64 `stop`
- hit max tokens：0/64
- next-question 串题：0/64
- error：0/64
- chunk wall time 总和：2394.76s
- requests/s：0.0267
- completion tokens：5300
- prompt tokens：46213
- completion tokens/s：2.213

## 输出文件

- `outputs/gsm8k/kimi_sglang_5shot_stop_idx216_limit16_p4_mt512_robuststop.jsonl`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx232_limit16_p4_mt512_robuststop.jsonl`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx248_limit16_p4_mt512_robuststop.jsonl`
- `outputs/gsm8k/kimi_sglang_5shot_stop_idx264_limit16_p4_mt512_robuststop.jsonl`
- 汇总：`outputs/gsm8k/kimi_sglang_5shot_stop_idx216_limit64_p4_mt512_robuststop.summary.json`

## 结论

鲁棒 stop 设置解决了之前官方大写 stop 导致的 `question:` 小写串题问题。本轮 64 样本没有任何 `hit_max_tokens` 或 next-question 串题，准确率恢复到可用区间。

当前主要问题仍是吞吐偏低，completion token/s 约 2.2。主要原因仍是 2x A100 40G 下使用 CPU offload，且 CUDA graph 关闭。后续如果继续优化速度，应优先在不破坏鲁棒 stop 的前提下测试更合适的 offload/显存占用参数，或寻找可用的 4 GPU / 更大显存配置。
