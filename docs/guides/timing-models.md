# Timing models

Both `replay` and `generate` apply a timing model to the base
`--interval` between batches. Four models are available.

| Model | Behaviour | Key options |
| --- | --- | --- |
| `uniform` | Constant intervals at the configured base value. | -- |
| `random` | Symmetric variation around the base interval. | `--random-factor 0.3` |
| `poisson` | Mixture of two exponential distributions (base and burst rates), producing burst clusters. | `--burst-probability`, `--burst-rate-multiplier` |
| `adaptive` | Exponentially distributed intervals; the rate parameter drifts via EMA of recent intervals. | `--adaptation-rate`, `--history-size` |

The Poisson and adaptive models are descriptive parameterisations and
have not been calibrated against empirical sequencer output. Use them
to stress-test pipelines against irregular timing rather than to
reproduce a specific sequencer's behaviour.

## Examples

```bash
# Deterministic, constant intervals
nanorunner replay -s /data -t /out --timing-model uniform --interval 10

# Symmetric random variation
nanorunner replay -s /data -t /out --timing-model random --random-factor 0.3

# Burst clusters via Poisson
nanorunner replay -s /data -t /out --timing-model poisson \
    --burst-probability 0.15 --burst-rate-multiplier 3.0

# Drifting intervals via adaptive
nanorunner replay -s /data -t /out --timing-model adaptive \
    --adaptation-rate 0.1 --history-size 10
```

## Profiles

Profiles bundle parameter sets for common scenarios. Inspect them with:

```bash
nanorunner list-profiles
nanorunner recommend                            # overview
nanorunner recommend --source /path/to/data     # recommend by input size
```

| Profile | Purpose |
| --- | --- |
| `development` | Fast iteration with deterministic uniform timing |
| `steady` | Low-variation random timing for controlled testing |
| `bursty` | Intermittent burst pattern for pipeline robustness |
| `high_throughput` | High file volume with burst timing for stress testing |
| `gradual_drift` | Slowly varying intervals via exponential moving average |
| `generate_test` | Quick smoke test for read generation (100 reads, builtin) |
| `generate_standard` | Standard generation run (5000 reads, auto backend) |

Apply a profile with `--profile NAME`. Subsequent flags override the
profile's defaults.

```bash
nanorunner replay -s /data -t /out --profile bursty --interval 3
```
