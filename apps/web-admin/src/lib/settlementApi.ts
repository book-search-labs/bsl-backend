import { fetchJson } from "./api";
import { routeRequest, type AdminApiMode } from "./apiRouter";

export type SettlementCycle = {
  cycle_id: number;
  start_date: string;
  end_date: string;
  status: string;
  generated_at?: string;
  created_at?: string;
  updated_at?: string;
};

export type SettlementLine = {
  settlement_line_id: number;
  cycle_id: number;
  seller_id: number;
  gross_sales: number;
  total_fees: number;
  refund_amount?: number;
  net_amount: number;
  status: string;
  created_at?: string;
  updated_at?: string;
};

export type Payout = {
  payout_id: number;
  settlement_line_id: number;
  status: string;
  paid_at?: string | null;
  failure_reason?: string | null;
  cycle_id?: number;
  seller_id?: number;
  net_amount?: number;
  line_status?: string;
  created_at?: string;
  updated_at?: string;
};

export type ReconciliationItem = {
  payment_id: number;
  order_id: number;
  payment_amount: number;
  sale_amount: number;
  pg_fee_amount?: number;
  platform_fee_amount?: number;
  refund_amount?: number;
  ledger_entry_count: number;
  currency?: string;
  provider?: string;
  created_at?: string;
};

type QueryValue = string | number | null | undefined;

function joinUrl(base: string, path: string) {
  return `${base.replace(/\/$/, "")}${path}`;
}

function toHeaderRecord(headers?: HeadersInit) {
  if (!headers) {
    return {};
  }
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return headers;
}

function buildQuery(params: Record<string, QueryValue>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

async function callSettlementApi<T>(apiMode: AdminApiMode, bffBaseUrl: string, path: string, init?: RequestInit) {
  const { result } = await routeRequest<T>({
    route: path,
    mode: apiMode,
    allowFallback: false,
    bff: (context) =>
      fetchJson<T>(joinUrl(bffBaseUrl, path), {
        ...init,
        headers: { ...context.headers, ...toHeaderRecord(init?.headers) },
      }),
    direct: (context) =>
      fetchJson<T>(joinUrl(bffBaseUrl, path), {
        ...init,
        headers: { ...context.headers, ...toHeaderRecord(init?.headers) },
      }),
  });
  return result;
}

export function createSettlementApi(apiMode: AdminApiMode, bffBaseUrl: string) {
  return {
    listCycles(params: { limit?: string; status?: string; from?: string; to?: string }) {
      return callSettlementApi<{ items: SettlementCycle[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/cycles${buildQuery(params)}`
      );
    },
    getCycle(cycleId: number) {
      return callSettlementApi<{ cycle: SettlementCycle; lines: SettlementLine[]; payouts: Payout[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/cycles/${cycleId}`
      );
    },
    listCycleLines(cycleId: number) {
      return callSettlementApi<{ items: SettlementLine[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/cycles/${cycleId}/lines`
      );
    },
    createCycle(payload: { startDate: string; endDate: string }) {
      return callSettlementApi<{ cycle: SettlementCycle; lines: SettlementLine[]; payouts: Payout[] }>(
        apiMode,
        bffBaseUrl,
        "/admin/settlements/cycles",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      );
    },
    generateCycle(cycleId: number) {
      return callSettlementApi<{ cycle: SettlementCycle; lines: SettlementLine[]; payouts: Payout[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/cycles/${cycleId}/generate`,
        {
          method: "POST",
        }
      );
    },
    listPayouts(params: { limit?: string; status?: string }) {
      return callSettlementApi<{ items: Payout[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/payouts${buildQuery(params)}`
      );
    },
    payPayout(payoutId: number) {
      return callSettlementApi<{ cycle: SettlementCycle; payout: Payout; payouts: Payout[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/payouts/${payoutId}/pay`,
        {
          method: "POST",
        }
      );
    },
    listReconciliation(params: { limit?: string; from?: string; to?: string }) {
      return callSettlementApi<{ items: ReconciliationItem[] }>(
        apiMode,
        bffBaseUrl,
        `/admin/settlements/reconciliation${buildQuery(params)}`
      );
    },
  };
}

export function toLocalDateInput(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function formatDateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "-";
}
