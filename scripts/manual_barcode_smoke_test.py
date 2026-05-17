import argparse
import json
import urllib.error
import urllib.request


def _request_json(
    method: str,
    url: str,
    payload: dict | None = None,
) -> tuple[int, dict | None, str]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach server at {url}: {exc.reason}") from exc

    parsed = None
    if body:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            print(f"JSON parse error for {method} {url}")
            print(f"Raw response body: {body}")

    return status_code, parsed, body


def _print_product_summary(product: dict) -> None:
    evidence = product.get("evidence")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    print(f"product_name: {product.get('product_name')}")
    print(f"brand: {product.get('brand')}")
    print(f"barcode: {product.get('barcode')}")
    print(f"status: {product.get('status')}")
    print(f"evidence_count: {evidence_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual smoke test for barcode discovery API flow")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--barcode", default="3017620422003")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    barcode = args.barcode

    print("Step 1: Health check")
    status, payload, raw = _request_json("GET", f"{base_url}/health")
    if status >= 400:
        print(f"Health check failed with status {status}")
        print(raw)
        raise SystemExit(1)
    if payload is None:
        print("Health check did not return valid JSON.")
        raise SystemExit(1)
    print(payload)

    print("\nStep 2: Ingest barcode")
    status, payload, raw = _request_json(
        "POST",
        f"{base_url}/ingest/barcode",
        {"barcode": barcode},
    )
    if status >= 400:
        print(f"Ingest request failed with status {status}")
        print(raw)
        raise SystemExit(1)
    if payload is None:
        print("Ingest endpoint did not return valid JSON.")
        raise SystemExit(1)
    print(payload)

    job_id = payload.get("job_id")
    if not job_id:
        print("Ingest response missing job_id.")
        raise SystemExit(1)

    print("\nStep 3: Process job")
    status, payload, raw = _request_json("POST", f"{base_url}/jobs/{job_id}/process")
    if status >= 400:
        print(f"Process request failed with status {status}")
        print(raw)
        raise SystemExit(1)
    if payload is None:
        print("Process endpoint did not return valid JSON.")
        raise SystemExit(1)
    print(payload)

    process_status = payload.get("status")
    result_product_id = payload.get("result_product_id")
    if process_status != "completed":
        print(f"Process job status is '{process_status}', not 'completed'.")

    print("\nStep 4: Fetch product by ID")
    if result_product_id:
        status, payload, raw = _request_json("GET", f"{base_url}/products/{result_product_id}")
        if status >= 400:
            print(f"Product lookup by ID failed with status {status}")
            print(raw)
        elif payload is None:
            print("Product-by-ID endpoint did not return valid JSON.")
        else:
            _print_product_summary(payload)
    else:
        print("No result_product_id returned; skipping product-by-ID lookup.")

    print("\nStep 5: Fetch product by barcode")
    status, payload, raw = _request_json("GET", f"{base_url}/products/by-barcode/{barcode}")
    if status >= 400:
        print(f"Product lookup by barcode failed with status {status}")
        print(raw)
        if status == 404:
            print(f"No product found for barcode {barcode}.")
    elif payload is None:
        print("Product-by-barcode endpoint did not return valid JSON.")
    else:
        _print_product_summary(payload)


if __name__ == "__main__":
    main()
