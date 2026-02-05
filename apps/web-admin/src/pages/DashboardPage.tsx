import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Col, Row, Spinner } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type MetricSummary = {
  query_count: number;
  p95_ms: number;
  p99_ms: number;
  zero_result_rate: number;
  rerank_rate: number;
  error_rate: number;
};

type MetricPoint = { ts: string; value: number };

type MetricsPayload = {
  summary: MetricSummary;
  series: Record<string, MetricPoint[]>;
};

type MetricsResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  summary: MetricSummary;
};

type SeriesResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  metric: string;
  items: MetricPoint[];
};

const WINDOWS = [
  { label: "15m", value: "15m" },
  { label: "1h", value: "1h" },
  { label: "24h", value: "24h" },
];

const METRIC_CARDS = [
  { key: "query_count", label: "Queries", format: (value: number) => value.toLocaleString() },
  { key: "p95_ms", label: "P95 Latency", format: (value: number) => `${value.toFixed(0)}ms` },
  { key: "p99_ms", label: "P99 Latency", format: (value: number) => `${value.toFixed(0)}ms` },
  { key: "zero_result_rate", label: "Zero Result", format: (value: number) => `${(value * 100).toFixed(1)}%` },
  { key: "rerank_rate", label: "Rerank Applied", format: (value: number) => `${(value * 100).toFixed(1)}%` },
  { key: "error_rate", label: "Error Rate", format: (value: number) => `${(value * 100).toFixed(2)}%` },
];

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function buildMockMetrics(windowKey: string): MetricsPayload {
  const now = Date.now();
  const points = windowKey === "15m" ? 12 : windowKey === "1h" ? 12 : 24;
  const intervalMs = windowKey === "15m" ? 60_000 : windowKey === "1h" ? 5 * 60_000 : 60 * 60_000;

  const buildSeries = (base: number, variance: number, clampMin = 0) => {
    return Array.from({ length: points }).map((_, index) => {
      const value = Math.max(clampMin, base + (Math.random() - 0.5) * variance);
      return {
        ts: new Date(now - (points - index) * intervalMs).toISOString(),
        value,
      };
    });
  };

  const querySeries = buildSeries(windowKey === "24h" ? 4200 : 1400, 400, 100);
  const p95Series = buildSeries(220, 60, 50);
  const p99Series = buildSeries(380, 90, 90);
  const zeroSeries = buildSeries(0.08, 0.04, 0);
  const rerankSeries = buildSeries(0.62, 0.08, 0);
  const errorSeries = buildSeries(0.012, 0.01, 0);

  return {
    summary: {
      query_count: Math.round(querySeries[querySeries.length - 1].value),
      p95_ms: Math.round(p95Series[p95Series.length - 1].value),
      p99_ms: Math.round(p99Series[p99Series.length - 1].value),
      zero_result_rate: zeroSeries[zeroSeries.length - 1].value,
      rerank_rate: rerankSeries[rerankSeries.length - 1].value,
      error_rate: errorSeries[errorSeries.length - 1].value,
    },
    series: {
      query_count: querySeries,
      p95_ms: p95Series,
      p99_ms: p99Series,
      zero_result_rate: zeroSeries,
      rerank_rate: rerankSeries,
      error_rate: errorSeries,
    },
  };
}

function Sparkline({ points, color }: { points: MetricPoint[]; color: string }) {
  if (!points.length) return null;
  const values = points.map((point) => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 120;
  const height = 36;
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  });

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <polyline fill="none" stroke={color} strokeWidth="2" points={coords.join(" ")} />
    </svg>
  );
}

export default function DashboardPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();
  const liveEnabled = (import.meta.env.VITE_ADMIN_METRICS_LIVE ?? "").toLowerCase() === "true";

  const [windowKey, setWindowKey] = useState("15m");
  const [metrics, setMetrics] = useState<MetricsPayload>(() => buildMockMetrics(windowKey));
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [usingMock, setUsingMock] = useState(!liveEnabled);

  const callBff = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      return routeRequest<T>({
        route: path,
        mode: apiMode,
        allowFallback: false,
        bff: (context) =>
          fetchJson<T>(joinUrl(bffBaseUrl, path), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
        direct: (context) =>
          fetchJson<T>(joinUrl(bffBaseUrl, path), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
      });
    },
    [apiMode, bffBaseUrl]
  );

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);

    if (!liveEnabled) {
      setMetrics(buildMockMetrics(windowKey));
      setUsingMock(true);
      setLoading(false);
      return;
    }

    const summaryParams = new URLSearchParams({ window: windowKey });
    const { result: summaryResult } = await callBff<MetricsResponse>(
      `/admin/ops/metrics/summary?${summaryParams}`
    );

    if (!summaryResult.ok) {
      setErrorMessage("Live metrics unavailable. Showing mock data.");
      setMetrics(buildMockMetrics(windowKey));
      setUsingMock(true);
      setLoading(false);
      return;
    }

    const seriesEntries = await Promise.all(
      METRIC_CARDS.map(async (metric) => {
        const params = new URLSearchParams({ metric: metric.key, window: windowKey });
        const { result } = await callBff<SeriesResponse>(`/admin/ops/metrics/timeseries?${params}`);
        if (result.ok) {
          return [metric.key, result.data.items ?? []] as const;
        }
        return [metric.key, []] as const;
      })
    );

    setMetrics({
      summary: summaryResult.data.summary,
      series: Object.fromEntries(seriesEntries),
    });
    setUsingMock(false);
    setLoading(false);
  }, [callBff, liveEnabled, windowKey]);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  const summary = metrics.summary;

  return (
    <div className="d-flex flex-column gap-3">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-2">
        <div>
          <h3 className="mb-1">Dashboard</h3>
          <p className="text-muted mb-0">Search platform operational metrics.</p>
        </div>
        <div className="d-flex align-items-center gap-2">
          {usingMock ? <Badge bg="secondary">Mock Data</Badge> : <Badge bg="success">Live</Badge>}
          <Button variant="outline-secondary" size="sm" onClick={loadMetrics} disabled={loading}>
            {loading ? <Spinner size="sm" /> : "Refresh"}
          </Button>
        </div>
      </div>

      {errorMessage ? <Alert variant="warning">{errorMessage}</Alert> : null}

      <Card className="shadow-sm">
        <Card.Body className="d-flex flex-wrap gap-2">
          {WINDOWS.map((item) => (
            <Button
              key={item.value}
              size="sm"
              variant={windowKey === item.value ? "primary" : "outline-primary"}
              onClick={() => setWindowKey(item.value)}
            >
              {item.label}
            </Button>
          ))}
        </Card.Body>
      </Card>

      <Row className="g-3">
        {METRIC_CARDS.map((metric) => (
          <Col key={metric.key} xs={12} md={6} xl={4}>
            <Card className="shadow-sm h-100">
              <Card.Body>
                <div className="d-flex justify-content-between align-items-center">
                  <div>
                    <div className="text-muted small">{metric.label}</div>
                    <div className="fs-4 fw-bold">{metric.format(summary[metric.key as keyof MetricSummary])}</div>
                  </div>
                  <Sparkline points={metrics.series[metric.key] ?? []} color="#0d6efd" />
                </div>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
