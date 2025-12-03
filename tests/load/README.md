# Phone Agent Load Testing

Comprehensive load testing suite for the Phone Agent system.

## Quick Start

```bash
# Install dependencies
pip install locust websockets aiohttp psutil

# Start the server (in another terminal)
python -m phone_agent

# Run quick smoke test
python tests/load/run_load_tests.py --profile quick
```

## Test Profiles

| Profile  | Duration | API Users | WebSocket | AI Calls | Use Case |
|----------|----------|-----------|-----------|----------|----------|
| quick    | 1 min    | 10        | 5         | 3        | CI/CD smoke test |
| standard | 5 min    | 50        | 20        | 10       | Typical production |
| stress   | 10 min   | 200       | 50        | 30       | Find breaking points |
| soak     | 60 min   | 25        | 10        | 5        | Memory leak detection |

## Individual Tests

### API Load Test (Locust)

```bash
# Interactive mode (web UI at localhost:8089)
locust -f tests/load/locustfile.py --host=http://localhost:8080

# Headless mode
locust -f tests/load/locustfile.py --host=http://localhost:8080 \
    --users 100 --spawn-rate 10 --run-time 5m --headless
```

### WebSocket Stress Test

```bash
python tests/load/websocket_stress.py --connections 50 --duration 60
```

### AI Pipeline Test

```bash
python tests/load/ai_pipeline_stress.py --calls 10 --duration 60
```

## Understanding Results

### Key Metrics

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| API p95 latency | <200ms | 200-500ms | >500ms |
| API success rate | >99% | 95-99% | <95% |
| WebSocket success | >95% | 80-95% | <80% |
| AI real-time factor | <0.8x | 0.8-1.0x | >1.0x |
| Memory growth | <50MB | 50-100MB | >100MB |

### Real-Time Factor

The "real-time factor" measures whether AI processing keeps up with audio:
- **<1.0x**: Processing faster than real-time (good)
- **=1.0x**: Processing exactly at real-time (edge case)
- **>1.0x**: Processing slower than real-time (will cause delays)

## Architecture

```
tests/load/
├── run_load_tests.py       # Unified test runner
├── locustfile.py           # API load tests (locust)
├── websocket_stress.py     # WebSocket stress test
├── ai_pipeline_stress.py   # AI pipeline test
└── README.md               # This file
```

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Load Test
  run: |
    python tests/load/run_load_tests.py \
      --profile quick \
      --output load-results.json

- name: Check Results
  run: |
    python -c "
    import json
    with open('load-results.json') as f:
      r = json.load(f)
    assert r['api'].get('success', False), 'API test failed'
    assert r['ai_pipeline'].get('success', False), 'AI test failed'
    "
```

## Troubleshooting

### Server not responding
```bash
# Check if server is running
curl http://localhost:8080/api/v1/health

# Start with debug logging
ITF_DEBUG=true python -m phone_agent
```

### Rate limiting too aggressive
The API has rate limits. If you see 429 errors:
1. Reduce spawn rate: `--spawn-rate 5`
2. Or adjust limits in `src/phone_agent/api/rate_limits.py`

### Memory issues during soak test
1. Enable garbage collection monitoring
2. Use `--skip-api` to isolate AI pipeline
3. Check for leaking connections

## Extending Tests

### Adding new API endpoints
Edit `locustfile.py` and add new `@task` methods:

```python
@task(1)
def my_new_endpoint(self):
    with self.client.get("/api/v1/new-endpoint") as response:
        if response.status_code == 200:
            response.success()
```

### Custom WebSocket scenarios
Create new classes inheriting from the base stress test.

### Testing with real AI services
Set `use_real_services=True` in `MockAudioProcessor` (requires API keys).
