# WEATHER-HMAC-V1 protocol

## Headers

| Header | Meaning |
|--------|---------|
| `X-Weather-Device` | Stable device id |
| `X-Weather-Key-Id` | Signing key id |
| `X-Weather-Timestamp` | Unix UTC seconds |
| `X-Weather-Nonce` | 32 lowercase/uppercase hex chars (16 bytes) |
| `X-Weather-Signature` | lowercase hex HMAC-SHA256 |

`Content-Type` must be exactly `application/x-www-form-urlencoded` (no charset parameter in the signed value; clients should send that media type).

## Canonical string

UTF-8, LF separators, **no** trailing newline:

```text
WEATHER-HMAC-V1
POST
/weather_station/weather_api/datasets/
application/x-www-form-urlencoded
<device_id>
<key_id>
<timestamp>
<nonce>
<sha256_hex_of_exact_raw_body>
```

The body digest is SHA-256 of the **exact bytes** on the wire. Do not re-serialize or reorder fields before hashing on the server.

Signature = HMAC-SHA256(secret, canonical_utf8) as lowercase hex.

## Skew and replay

- Timestamp tolerance: ±300 seconds (configurable).
- Nonce replay TTL: ≥600 seconds in Redis/cache.
- Identical retry (same device, key, nonce, body) after success returns 200 without a second DB row.
- Same nonce with a different body digest is rejected.

## Fixed test vector

```text
secret_hex = 0000000000000000000000000000000000000000000000000000000000000000
device_id  = test-device
key_id     = key1
timestamp  = 1700000000
nonce      = 00112233445566778899aabbccddeeff
body       = jd=2460000.00000&temperature=20.00
```

Expected (locked by firmware `tools/hmac_selftest` and `SecurityRemediationTests.test_signing_helpers_stable`):

```text
body_sha256 = 272add28edef85bb137dd1dec6f7c69d5a74f13f2032f00507465a8e564fb7f9
signature   = 17dcbd5904c2dbf8a7780e2e90a8b63cb91fda199810fa18a24b1a3fb9a87c3c
```

## Bulk upload (`/datasets/bulk/`)

Many samples in one request, used by the R4 firmware since v1.9 (one request per minute instead of one per sample).

- `POST /weather_station/weather_api/datasets/bulk/`, `Content-Type: text/csv`, same headers as above.
- The canonical string uses the **bulk path** and **`text/csv`**: a signature made for `/datasets/` is not valid here and vice versa.
- Body: a header line with exactly these columns (any order), then one line per sample, at most `BULK_UPLOAD_MAX_ROWS` (600) rows:

  ```text
  jd,temperature,pressure,humidity,illuminance,wind_speed,rain,sky_temp,box_temp,is_raining,pm1_0,pm2_5,pm10,uv_index
  ```

- Every row is validated like a single upload (same ranges, all fields required). Invalid rows and samples already stored for this device (same `jd` to 7 decimals) are **skipped**; the request still succeeds.
- Response `201`: `{"created": n, "rejected": m, "duplicates": d, "errors": [{"row": i, "errors": {...}}, ...]}` (at most 10 errors listed). An identical retry (same nonce and body) returns `200` with the same summary. A malformed body (empty, wrong header, too many rows) returns `400`.

Bulk test vector (secret, device, key, timestamp and nonce as above; body ends with a newline):

```text
body        = jd,temperature,pressure,humidity,illuminance,wind_speed,rain,sky_temp,box_temp,is_raining,pm1_0,pm2_5,pm10,uv_index\n
              2460000.0000000,20.00,1013.00,50.00,100.000,0,0.00,10.00,15.00,0,1,2,3,0\n
body_sha256 = 012f723a4f081f2da62da1e2d7d3fcf7bcd4bb5a1405257ab8ffb33fd166f2df
signature   = 1fc948e3deaaee6ea8f66087dc3e9e96a09c3f07efcb09e1141e3b9d7218b2e8
```

Locked by `BulkUploadTests.test_bulk_signing_vector` and the firmware self-test.

## Provisioning

```bash
python manage.py provision_upload_device --device-id r4-main --label "UNO R4"
python manage.py rotate_upload_key --device-id r4-main
python manage.py revoke_upload_key --device-id r4-main --key-id <old>
```

Set `UPLOAD_AUTH_MODE=dual` during migration, then `hmac_only` after canary.
