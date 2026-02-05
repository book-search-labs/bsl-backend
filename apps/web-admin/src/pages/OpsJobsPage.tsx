import { Fragment, useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Form,
  Row,
  Spinner,
  Tab,
  Table,
  Tabs,
} from "react-bootstrap";
import { fetchJson } from "../lib/api";
import { resolveAdminApiMode, resolveBffBaseUrl, routeRequest } from "../lib/apiRouter";

type OpsListResponse<T> = {
  version: string;
  trace_id: string;
  request_id: string;
  count: number;
  items: T[];
};

type JobRun = {
  job_run_id: number;
  job_type: string;
  status: string;
  params?: unknown;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

type JobRunResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  job_run: JobRun;
};

type ReindexJob = {
  reindex_job_id: number;
  logical_name: string;
  from_physical?: string | null;
  to_physical?: string | null;
  status: string;
  params?: unknown;
  progress?: unknown;
  error?: unknown;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  paused_at?: string | null;
};

type ReindexJobResponse = {
  version: string;
  trace_id: string;
  request_id: string;
  job: ReindexJob;
};

type OpsTask = {
  task_id: number;
  task_type: string;
  status: string;
  payload?: unknown;
  assigned_admin_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type StartReindexPayload = {
  logical_name: string;
  params?: Record<string, unknown>;
};

const DEFAULT_LIMIT = 50;

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
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

function progressLabel(progress?: unknown) {
  if (!progress || typeof progress !== "object") return "-";
  const record = progress as Record<string, unknown>;
  const total = Number(record.total ?? 0);
  const processed = Number(record.processed ?? 0);
  const failed = Number(record.failed ?? 0);
  const retries = Number(record.retries ?? 0);
  if (!total) return `${processed} processed`;
  const pct = Math.min(100, Math.round((processed / total) * 100));
  return `${pct}% (${processed}/${total}) · fail ${failed} · retry ${retries}`;
}

function hasProgress(progress?: unknown) {
  return progress && typeof progress === "object" && Object.keys(progress as object).length > 0;
}

export default function OpsJobsPage() {
  const bffBaseUrl = resolveBffBaseUrl();
  const apiMode = resolveAdminApiMode();
  const indexWriterBaseUrl = import.meta.env.VITE_INDEX_WRITER_BASE_URL ?? "http://localhost:8090";

  const [jobRuns, setJobRuns] = useState<JobRun[]>([]);
  const [reindexJobs, setReindexJobs] = useState<ReindexJob[]>([]);
  const [opsTasks, setOpsTasks] = useState<OpsTask[]>([]);
  const [activeTab, setActiveTab] = useState<string>("jobRuns");
  const [expandedJobRun, setExpandedJobRun] = useState<number | null>(null);
  const [expandedReindex, setExpandedReindex] = useState<number | null>(null);
  const [expandedTask, setExpandedTask] = useState<number | null>(null);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loadingJobRuns, setLoadingJobRuns] = useState(false);
  const [loadingReindex, setLoadingReindex] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const [logicalName, setLogicalName] = useState("books_doc");
  const [indexPrefix, setIndexPrefix] = useState("");
  const [mappingPath, setMappingPath] = useState("");
  const [materialKinds, setMaterialKinds] = useState("");
  const [deleteExisting, setDeleteExisting] = useState(false);

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

  const callReindex = useCallback(
    async <T,>(bffPath: string, directPath: string, init?: RequestInit) => {
      return routeRequest<T>({
        route: bffPath,
        mode: apiMode,
        allowFallback: false,
        bff: (context) =>
          fetchJson<T>(joinUrl(bffBaseUrl, bffPath), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
        direct: (context) =>
          fetchJson<T>(joinUrl(indexWriterBaseUrl, directPath), {
            ...init,
            headers: { ...context.headers, ...(init?.headers ?? {}) },
          }),
      });
    },
    [apiMode, bffBaseUrl, indexWriterBaseUrl]
  );

  const loadJobRuns = useCallback(async () => {
    setLoadingJobRuns(true);
    setErrorMessage(null);
    const { result } = await callBff<OpsListResponse<JobRun>>(`/admin/ops/job-runs?limit=${DEFAULT_LIMIT}`);
    if (result.ok) {
      setJobRuns(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load job runs (${result.status || result.statusText}).`);
    }
    setLoadingJobRuns(false);
  }, [callBff]);

  const loadReindexJobs = useCallback(async () => {
    setLoadingReindex(true);
    setErrorMessage(null);
    const { result } = await callBff<OpsListResponse<ReindexJob>>(`/admin/ops/reindex-jobs?limit=${DEFAULT_LIMIT}`);
    if (result.ok) {
      setReindexJobs(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load reindex jobs (${result.status || result.statusText}).`);
    }
    setLoadingReindex(false);
  }, [callBff]);

  const loadOpsTasks = useCallback(async () => {
    setLoadingTasks(true);
    setErrorMessage(null);
    const { result } = await callBff<OpsListResponse<OpsTask>>(`/admin/ops/tasks?limit=${DEFAULT_LIMIT}`);
    if (result.ok) {
      setOpsTasks(result.data.items ?? []);
    } else {
      setErrorMessage(`Failed to load ops tasks (${result.status || result.statusText}).`);
    }
    setLoadingTasks(false);
  }, [callBff]);

  useEffect(() => {
    loadJobRuns();
    loadReindexJobs();
    loadOpsTasks();
  }, [loadJobRuns, loadReindexJobs, loadOpsTasks]);

  const handleRetryJobRun = async (jobRunId: number) => {
    setActionLoading(true);
    setErrorMessage(null);
    const { result } = await callBff<JobRunResponse>(`/admin/ops/job-runs/${jobRunId}/retry`, {
      method: "POST",
    });
    if (!result.ok) {
      setErrorMessage(`Retry failed (${result.status || result.statusText}).`);
    } else {
      await loadJobRuns();
    }
    setActionLoading(false);
  };

  const handleStartReindex = async () => {
    if (!logicalName.trim()) {
      setErrorMessage("logical_name is required.");
      return;
    }
    const params: Record<string, unknown> = {};
    if (indexPrefix.trim()) params.index_prefix = indexPrefix.trim();
    if (mappingPath.trim()) params.mapping_path = mappingPath.trim();
    if (materialKinds.trim()) {
      params.material_kinds = materialKinds
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    }
    if (deleteExisting) params.delete_existing = true;
    const payload: StartReindexPayload = {
      logical_name: logicalName.trim(),
      params: Object.keys(params).length ? params : undefined,
    };

    setActionLoading(true);
    setErrorMessage(null);
    const { result } = await callReindex<ReindexJobResponse>(
      "/admin/ops/reindex-jobs/start",
      "/internal/index/reindex-jobs",
      {
      method: "POST",
      body: JSON.stringify(payload),
      }
    );
    if (!result.ok) {
      setErrorMessage(`Failed to start reindex (${result.status || result.statusText}).`);
    } else {
      await loadReindexJobs();
    }
    setActionLoading(false);
  };

  const handleReindexAction = async (jobId: number, action: "pause" | "resume" | "retry") => {
    setActionLoading(true);
    setErrorMessage(null);
    const { result } = await callReindex<ReindexJobResponse>(
      `/admin/ops/reindex-jobs/${jobId}/${action}`,
      `/internal/index/reindex-jobs/${jobId}/${action}`,
      { method: "POST" }
    );
    if (!result.ok) {
      setErrorMessage(`Failed to ${action} reindex (${result.status || result.statusText}).`);
    } else {
      await loadReindexJobs();
    }
    setActionLoading(false);
  };

  const canPause = (status: string) => {
    const normalized = status.toUpperCase();
    return [
      "CREATED",
      "PREPARE",
      "BUILD_INDEX",
      "BULK_LOAD",
      "VERIFY",
      "ALIAS_SWAP",
      "CLEANUP",
      "RETRY",
      "RESUME",
    ].includes(normalized);
  };

  const canResume = (status: string) => status.toUpperCase() === "PAUSED";
  const canRetry = (status: string) => status.toUpperCase() === "FAILED";

  return (
    <>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h3 className="mb-1">Ops Jobs</h3>
          <div className="text-muted small">BFF API mode: {apiMode}</div>
        </div>
        <Button
          variant="outline-secondary"
          size="sm"
          onClick={async () => {
            if (activeTab === "jobRuns") await loadJobRuns();
            if (activeTab === "reindex") await loadReindexJobs();
            if (activeTab === "tasks") await loadOpsTasks();
          }}
          disabled={loadingJobRuns || loadingReindex || loadingTasks}
        >
          Refresh
        </Button>
      </div>

      {errorMessage ? <Alert variant="danger">{errorMessage}</Alert> : null}

      <Tabs activeKey={activeTab} onSelect={(key) => key && setActiveTab(key)} className="mb-3">
        <Tab eventKey="jobRuns" title="Job Runs">
          <Card className="shadow-sm">
            <Card.Body>
              {loadingJobRuns ? (
                <div className="d-flex align-items-center gap-2 text-muted">
                  <Spinner size="sm" /> Loading job runs...
                </div>
              ) : (
                <Table responsive hover className="align-middle">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Started</th>
                      <th>Finished</th>
                      <th>Error</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobRuns.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="text-muted">No job runs found.</td>
                      </tr>
                    ) : (
                      jobRuns.map((job) => (
                        <Fragment key={job.job_run_id}>
                          <tr key={job.job_run_id}>
                            <td>{job.job_run_id}</td>
                            <td>{job.job_type}</td>
                            <td>
                              <Badge bg={statusVariant(job.status)}>{job.status}</Badge>
                            </td>
                            <td>{formatTime(job.started_at)}</td>
                            <td>{formatTime(job.finished_at)}</td>
                            <td className="text-truncate" style={{ maxWidth: 200 }}>
                              {job.error_message ?? "-"}
                            </td>
                            <td className="text-end">
                              <Button
                                size="sm"
                                variant="outline-primary"
                                onClick={() => setExpandedJobRun(expandedJobRun === job.job_run_id ? null : job.job_run_id)}
                                className="me-2"
                              >
                                Details
                              </Button>
                              <Button
                                size="sm"
                                variant="primary"
                                onClick={() => handleRetryJobRun(job.job_run_id)}
                                disabled={actionLoading}
                              >
                                Retry
                              </Button>
                            </td>
                          </tr>
                          {expandedJobRun === job.job_run_id ? (
                            <tr key={`job-details-${job.job_run_id}`}>
                              <td colSpan={7}>
                                <div className="bg-light rounded p-3">
                                  <div className="fw-semibold mb-2">Params</div>
                                  <pre className="mb-0 small">{prettyJson(job.params)}</pre>
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      ))
                    )}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>

        <Tab eventKey="reindex" title="Reindex Jobs">
          <Card className="shadow-sm mb-3">
            <Card.Body>
              <Row className="g-3 align-items-end">
                <Col md={3}>
                  <Form.Label>Logical name</Form.Label>
                  <Form.Control value={logicalName} onChange={(e) => setLogicalName(e.target.value)} />
                </Col>
                <Col md={3}>
                  <Form.Label>Index prefix (optional)</Form.Label>
                  <Form.Control value={indexPrefix} onChange={(e) => setIndexPrefix(e.target.value)} />
                </Col>
                <Col md={4}>
                  <Form.Label>Mapping path (optional)</Form.Label>
                  <Form.Control value={mappingPath} onChange={(e) => setMappingPath(e.target.value)} />
                </Col>
                <Col md={2}>
                  <Button variant="primary" className="w-100" onClick={handleStartReindex} disabled={actionLoading}>
                    Start reindex
                  </Button>
                </Col>
                <Col md={4}>
                  <Form.Label>Material kinds (comma)</Form.Label>
                  <Form.Control
                    placeholder="BOOK,MAGAZINE"
                    value={materialKinds}
                    onChange={(e) => setMaterialKinds(e.target.value)}
                  />
                </Col>
                <Col md={3}>
                  <Form.Check
                    type="switch"
                    id="deleteExisting"
                    label="Delete existing index"
                    checked={deleteExisting}
                    onChange={(e) => setDeleteExisting(e.target.checked)}
                  />
                </Col>
              </Row>
            </Card.Body>
          </Card>

          <Card className="shadow-sm">
            <Card.Body>
              {loadingReindex ? (
                <div className="d-flex align-items-center gap-2 text-muted">
                  <Spinner size="sm" /> Loading reindex jobs...
                </div>
              ) : (
                <Table responsive hover className="align-middle">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Logical</th>
                      <th>Status</th>
                      <th>Progress</th>
                      <th>Updated</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {reindexJobs.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="text-muted">No reindex jobs found.</td>
                      </tr>
                    ) : (
                      reindexJobs.map((job) => (
                        <Fragment key={job.reindex_job_id}>
                          <tr key={job.reindex_job_id}>
                            <td>{job.reindex_job_id}</td>
                            <td>{job.logical_name}</td>
                            <td>
                              <Badge bg={statusVariant(job.status)}>{job.status}</Badge>
                            </td>
                            <td>{progressLabel(job.progress)}</td>
                            <td>{formatTime(job.updated_at ?? job.started_at)}</td>
                            <td className="text-end">
                              <Button
                                size="sm"
                                variant="outline-primary"
                                className="me-2"
                                onClick={() =>
                                  setExpandedReindex(expandedReindex === job.reindex_job_id ? null : job.reindex_job_id)
                                }
                              >
                                Details
                              </Button>
                              {canPause(job.status) ? (
                                <Button
                                  size="sm"
                                  variant="warning"
                                  onClick={() => handleReindexAction(job.reindex_job_id, "pause")}
                                  disabled={actionLoading}
                                  className="me-2"
                                >
                                  Pause
                                </Button>
                              ) : null}
                              {canResume(job.status) ? (
                                <Button
                                  size="sm"
                                  variant="success"
                                  onClick={() => handleReindexAction(job.reindex_job_id, "resume")}
                                  disabled={actionLoading}
                                  className="me-2"
                                >
                                  Resume
                                </Button>
                              ) : null}
                              {canRetry(job.status) ? (
                                <Button
                                  size="sm"
                                  variant="danger"
                                  onClick={() => handleReindexAction(job.reindex_job_id, "retry")}
                                  disabled={actionLoading}
                                >
                                  Retry
                                </Button>
                              ) : null}
                            </td>
                          </tr>
                          {expandedReindex === job.reindex_job_id ? (
                            <tr key={`reindex-details-${job.reindex_job_id}`}>
                              <td colSpan={6}>
                                <Row className="g-3">
                                  <Col md={4}>
                                    <div className="bg-light rounded p-3 h-100">
                                      <div className="fw-semibold mb-2">Params</div>
                                      <pre className="small mb-0">{prettyJson(job.params)}</pre>
                                    </div>
                                  </Col>
                                  <Col md={4}>
                                    <div className="bg-light rounded p-3 h-100">
                                      <div className="fw-semibold mb-2">Progress</div>
                                      <div className="small text-muted mb-2">
                                        {hasProgress(job.progress) ? progressLabel(job.progress) : "No progress yet"}
                                      </div>
                                      <pre className="small mb-0">{prettyJson(job.progress)}</pre>
                                    </div>
                                  </Col>
                                  <Col md={4}>
                                    <div className="bg-light rounded p-3 h-100">
                                      <div className="fw-semibold mb-2">Error</div>
                                      <div className="small text-muted mb-2">{job.error_message ?? "-"}</div>
                                      <pre className="small mb-0">{prettyJson(job.error)}</pre>
                                    </div>
                                  </Col>
                                </Row>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      ))
                    )}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>

        <Tab eventKey="tasks" title="Ops Tasks">
          <Card className="shadow-sm">
            <Card.Body>
              {loadingTasks ? (
                <div className="d-flex align-items-center gap-2 text-muted">
                  <Spinner size="sm" /> Loading ops tasks...
                </div>
              ) : (
                <Table responsive hover className="align-middle">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Assignee</th>
                      <th>Updated</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {opsTasks.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="text-muted">No ops tasks found.</td>
                      </tr>
                    ) : (
                      opsTasks.map((task) => (
                        <Fragment key={task.task_id}>
                          <tr key={task.task_id}>
                            <td>{task.task_id}</td>
                            <td>{task.task_type}</td>
                            <td>
                              <Badge bg={statusVariant(task.status)}>{task.status}</Badge>
                            </td>
                            <td>{task.assigned_admin_id ?? "-"}</td>
                            <td>{formatTime(task.updated_at ?? task.created_at)}</td>
                            <td className="text-end">
                              <Button
                                size="sm"
                                variant="outline-primary"
                                onClick={() => setExpandedTask(expandedTask === task.task_id ? null : task.task_id)}
                              >
                                Details
                              </Button>
                            </td>
                          </tr>
                          {expandedTask === task.task_id ? (
                            <tr key={`task-details-${task.task_id}`}>
                              <td colSpan={6}>
                                <div className="bg-light rounded p-3">
                                  <div className="fw-semibold mb-2">Payload</div>
                                  <pre className="small mb-0">{prettyJson(task.payload)}</pre>
                                </div>
                              </td>
                            </tr>
                          ) : null}
                        </Fragment>
                      ))
                    )}
                  </tbody>
                </Table>
              )}
            </Card.Body>
          </Card>
        </Tab>
      </Tabs>
    </>
  );
}
