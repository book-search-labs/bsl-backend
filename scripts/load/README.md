# Load / Performance Tests (k6)

These scripts provide **basic p95/p99 smoke** checks for local/stage environments.
Install k6: https://k6.io/docs/get-started/installation/

## Search
```bash
BASE_URL=http://localhost:8088 k6 run scripts/load/k6_search.js
```

## Autocomplete
```bash
BASE_URL=http://localhost:8088 k6 run scripts/load/k6_autocomplete.js
```

## Commerce (cart/order)
```bash
BASE_URL=http://localhost:8088 SKU_ID=1 SELLER_ID=1 k6 run scripts/load/k6_commerce.js
```
