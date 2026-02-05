import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<300', 'p(99)<800'],
    http_req_failed: ['rate<0.01'],
  },
};

const baseUrl = __ENV.BASE_URL || 'http://localhost:8088';

export default function () {
  const res = http.get(`${baseUrl}/autocomplete?q=ha`);
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(0.5);
}
