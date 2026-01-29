# I-0321 — MIS Scaling/Resource Profile (CPU/GPU Options) + Autoscale Standard

## Goal
MIS is stable in CPU/GPU environment,
Create “Resource Profile” for simultaneous/queue/batch and set up an autoscale standard.

## Why
- reranker/cross-encoder is a great way to buy a bottleneck
- If there is no scale standard, p99 turns or costly

## Scope
### 1) Profiling scenario
- Measurement of latency by input length/loader(topR)/batch size
- CPU 1~N core, GPU 1(optional)
- QPS ramp test

### 2 years ) Fixed setting parameters
- `max_batch_size`, `max_queue_size`, `max_seq_len`, `timeout_ms`
- dynamic batching on/off
- concurrency(work)

### 3) Autoscale standard
- CPU util
- queue depth
- p95 latency
- (GPU) GPU util / memory

### 4) Runbook/Alam connection
- scale-out/scale-in scenario
- Degrade Policy in Overload (Total: I-0317, I-0316)

## Non-goals
- Multi GPU Dispersion Abstract (Extra)

## DoD
- Documentation (e.g. CPU-only baseline, GPU option)
- Autoscape Rules are defined and validated in the stage
- scale + degrade based on queue of overload

## Codex Prompt
Create MIS scaling profiles:
- Benchmark MIS latency under varying batch/concurrency/topR/seq_len on CPU (and GPU if available).
- Define recommended configs and autoscaling rules based on queue depth and latency.
- Document in runbook and wire alerts.
