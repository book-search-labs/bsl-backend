# Autocomplete Service

## Run (local)
```bash
cd /path/to/bsl-backend
./gradlew :services:autocomplete-service:bootRun
```

Default port: `8081` (from `src/main/resources/application.yml`).

## Test curl
```bash
curl -s "http://localhost:8081/autocomplete?q=harry&size=5"
```
