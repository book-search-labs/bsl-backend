import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Modal, Spinner, Table } from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type ReindexJob = {
  reindex_job_id: number;
  logical_name: string;
  from_physical?: string | null;
  to_physical?: string | null;
  status: string;
  params?: unknown;
  progress?: unknown;
  created_at?: string | null;
  updated_at?: string | null;
};

type OpsListResponse<T> = {
  version: string;
  trace_id: string;
  request_id: string;
  count: number;
  items: T[];
};

type IndexRow = {
  index_name: string;
  logical_name: string;
  role: "source" | "target";
  status?: string;
  updated_at?: string | null;
  job?: ReindexJob;
};

type AliasRow = {
  logical_name: string;
  read_alias: string;
  write_alias: string;
  active_index?: string | null;
  status?: string;
  updated_at?: string | null;
};

const DEFAULT_LIMIT = 80;

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusVariant(status?: string) {
  if (!status) return "secondary";
  const normalized = status.toUpperCase();
  if (normalized.includes("FAIL")) return "danger";
  if (normalized.includes("SUCCESS")) return "success";
  if (normalized.includes("PAUSE")) return "warning";
  if (normalized.includes("RUN") || normalized.includes("BUILD") || normalized.includes("LOAD")) return "info";
  return "secondary";
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

export default function IndexOpsPage() {
  const apiMode = resolveAdminApiMode();
  const bffBaseUrl = resolveBffBaseUrl();

  const [jobs, setJobs] = useState<ReindexJob[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<ReindexJob | null>(null);

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

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    const { result } = await callBff<OpsListResponse<ReindexJob>>(
      `/admin/ops/reindex-jobs?limit=${DEFAULT_LIMIT}`
    );
    if (result.ok) {
      setJobs(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load reindex jobs (${result.status || result.statusText}).`);
    }
    setLoading(false);
  }, [callBff]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const aliasRows = useMemo<AliasRow[]>(() => {
    const byLogical = new Map<string, ReindexJob>();
    jobs.forEach((job) => {
      const current = byLogical.get(job.logical_name);
      if (!current) {
        byLogical.set(job.logical_name, job);
        return;
      }
      const currentDate = new Date(current.updated_at ?? current.created_at ?? 0).getTime();
      const nextDate = new Date(job.updated_at ?? job.created_at ?? 0).getTime();
      if (nextDate >= currentDate) {
        byLogical.set(job.logical_name, job);
      }
    });

    return Array.from(byLogical.values()).map((job) => ({
      logical_name: job.logical_name,
      read_alias: `${job.logical_name}_read`,
      write_alias: `${job.logical_name}_write`,
      active_index: job.to_physical ?? job.from_physical ?? null,
      status: job.status,
      updated_at: job.updated_at ?? job.created_at ?? null,
    }));
  }, [jobs]);

  const indexRows = useMemo<IndexRow[]>(() => {
    const rows = new Map<string, IndexRow>();

    jobs.forEach((job) => {
      if (job.from_physical) {
        rows.set(job.from_physical, {
          index_name: job.from_physical,
          logical_name: job.logical_name,
          role: "source",
          status: job.status,
          updated_at: job.updated_at ?? job.created_at ?? null,
          job,
        });
      }
      if (job.to_physical) {
        rows.set(job.to_physical, {
          index_name: job.to_physical,
          logical_name: job.logical_name,
          role: "target",
          status: job.status,
          updated_at: job.updated_at ?? job.created_at ?? null,
          job,
        });
      }
    });

    return Array.from(rows.values());
  }, [jobs]);

  return (
    <div className="d-flex flex-column gap-3">
      <div className="d-flex align-items-center justify-content-between">
        <div>
          <h3 className="mb-1">Indices Overview</h3>
          <p className="text-muted mb-0">
            Reindex job data is used to infer alias targets. Document counts and mappings require
            index metadata API support.
          </p>
        </div>
        <Button variant="outline-secondary" size="sm" onClick={loadJobs} disabled={loading}>
          {loading ? <Spinner size="sm" /> : "Refresh"}
        </Button>
      </div>

      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}

      <Card className="shadow-sm">
        <Card.Header className="d-flex align-items-center justify-content-between">
          <strong>Alias Summary (inferred)</strong>
          <Badge bg="secondary">{aliasRows.length} logical names</Badge>
        </Card.Header>
        <Card.Body>
          <Table responsive hover size="sm" className="mb-0">
            <thead>
              <tr>
                <th>Logical</th>
                <th>Read Alias</th>
                <th>Write Alias</th>
                <th>Active Index</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {aliasRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-muted">
                    No reindex jobs found.
                  </td>
                </tr>
              ) : (
                aliasRows.map((row) => (
                  <tr key={row.logical_name}>
                    <td>{row.logical_name}</td>
                    <td>{row.read_alias}</td>
                    <td>{row.write_alias}</td>
                    <td>{row.active_index ?? "-"}</td>
                    <td>
                      <Badge bg={statusVariant(row.status)}>{row.status ?? "-"}</Badge>
                    </td>
                    <td>{formatDate(row.updated_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      <Card className="shadow-sm">
        <Card.Header className="d-flex align-items-center justify-content-between">
          <strong>Indices</strong>
          <Badge bg="secondary">{indexRows.length} physical indices</Badge>
        </Card.Header>
        <Card.Body>
          <Table responsive hover size="sm" className="mb-0">
            <thead>
              <tr>
                <th>Index</th>
                <th>Logical</th>
                <th>Role</th>
                <th>Status</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {indexRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-muted">
                    No indices inferred from reindex jobs.
                  </td>
                </tr>
              ) : (
                indexRows.map((row) => (
                  <tr key={row.index_name}>
                    <td>{row.index_name}</td>
                    <td>{row.logical_name}</td>
                    <td className="text-muted">{row.role}</td>
                    <td>
                      <Badge bg={statusVariant(row.status)}>{row.status ?? "-"}</Badge>
                    </td>
                    <td>{formatDate(row.updated_at)}</td>
                    <td>
                      <Button
                        variant="outline-primary"
                        size="sm"
                        onClick={() => setSelectedJob(row.job ?? null)}
                        disabled={!row.job}
                      >
                        View details
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </Table>
        </Card.Body>
      </Card>

      <Modal
        show={!!selectedJob}
        onHide={() => setSelectedJob(null)}
        size="lg"
        centered
      >
        <Modal.Header closeButton>
          <Modal.Title>Index Details</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {selectedJob ? (
            <div className="d-flex flex-column gap-3">
              <div className="d-flex flex-wrap gap-3">
                <div>
                  <div className="text-muted small">Logical</div>
                  <div className="fw-semibold">{selectedJob.logical_name}</div>
                </div>
                <div>
                  <div className="text-muted small">Status</div>
                  <Badge bg={statusVariant(selectedJob.status)}>{selectedJob.status}</Badge>
                </div>
                <div>
                  <div className="text-muted small">Updated</div>
                  <div className="fw-semibold">{formatDate(selectedJob.updated_at ?? selectedJob.created_at)}</div>
                </div>
              </div>
              <div>
                <div className="text-muted small mb-1">Params</div>
                <pre className="small bg-light p-2 rounded mb-0">{prettyJson(selectedJob.params)}</pre>
              </div>
              <div>
                <div className="text-muted small mb-1">Progress</div>
                <pre className="small bg-light p-2 rounded mb-0">{prettyJson(selectedJob.progress)}</pre>
              </div>
              <Alert variant="info" className="mb-0">
                Mapping/settings metadata is not available from reindex jobs. Connect the index
                metadata API to enable JSON views.
              </Alert>
            </div>
          ) : null}
        </Modal.Body>
      </Modal>
    </div>
  );
}
