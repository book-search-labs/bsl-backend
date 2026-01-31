import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1200'],
    http_req_failed: ['rate<0.02'],
  },
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8088';
const skuId = __ENV.SKU_ID;
const sellerId = __ENV.SELLER_ID || '1';

if (!skuId) {
  throw new Error('SKU_ID is required (export SKU_ID=123)');
}

const headers = {
  'Content-Type': 'application/json',
  'x-user-id': __ENV.USER_ID || '1001',
};

export default function () {
  const payload = JSON.stringify({ skuId: Number(skuId), sellerId: Number(sellerId), qty: 1 });
  const res = http.post(`${baseUrl}/api/v1/cart/items`, payload, { headers });
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
