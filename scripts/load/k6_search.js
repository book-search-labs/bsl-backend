import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1200'],
    http_req_failed: ['rate<0.01'],
  },
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8088';
const headers = { 'Content-Type': 'application/json' };

export default function () {
  const payload = JSON.stringify({ query: { raw: '해리포터' } });
  const res = http.post(`${baseUrl}/search`, payload, { headers });
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
