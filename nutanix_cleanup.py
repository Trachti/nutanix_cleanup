import http.client
import json
import argparse
import time
import ssl
import uuid
from datetime import datetime, timedelta, timezone

NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"

# Important:
# The same user with the same password must exist on Prism Central and on all configured Prism Element clusters.
# This script uses one shared token for Prism Central and all Prism Element hosts.
# Different credentials per Prism Element are not supported by this script.
PE_AND_PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"

PE_HOSTS = [
    "IP_FROM_ELEMENTS_CLUSTER_1:9440",
    "IP_FROM_ELEMENTS_CLUSTER_2:9440",
    "IP_FROM_ELEMENTS_CLUSTER_3:9440",
]


def get_conn(api_host):
    context = ssl._create_unverified_context()
    return http.client.HTTPSConnection(api_host, context=context)


def extract_error_message(data):
    err_list = data.get("data", {}).get("error", [])
    if err_list:
        first = err_list[0]
        return {
            "message": first.get("message", "Unknown error"),
            "code": first.get("code", "n/a"),
            "group": first.get("errorGroup", "n/a"),
            "raw": data
        }

    if "message" in data:
        return {
            "message": data.get("message", "Unknown error"),
            "code": data.get("error_code", {}).get("code", "n/a") if isinstance(data.get("error_code"), dict) else data.get("error_code", "n/a"),
            "group": "n/a",
            "raw": data
        }

    return {
        "message": str(data),
        "code": "n/a",
        "group": "n/a",
        "raw": data
    }


def api_request(api_host, method, url, payload=None, extra_headers=None):
    conn = get_conn(api_host)
    headers = {
        "Accept": "application/json",
        "Authorization": PE_AND_PC_TOKEN,
        "Content-Type": "application/json"
    }

    if extra_headers:
        headers.update(extra_headers)

    body = None
    if payload is not None:
        body = payload if isinstance(payload, str) else json.dumps(payload)

    conn.request(method, url, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw}

    if res.status >= 400:
        err = extract_error_message(data)
        raise RuntimeError(
            json.dumps({
                "http_status": res.status,
                "api_host": api_host,
                "url": url,
                "message": err["message"],
                "code": err["code"],
                "group": err["group"],
                "raw": err["raw"]
            }, ensure_ascii=False)
        )

    return data, res.status


def parse_datetime(value):
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        number = float(value)

        if number > 10_000_000_000_000:
            return datetime.fromtimestamp(number / 1_000_000, tz=timezone.utc)

        if number > 10_000_000_000:
            return datetime.fromtimestamp(number / 1000, tz=timezone.utc)

        return datetime.fromtimestamp(number, tz=timezone.utc)

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    return None


def get_first_datetime(item, field_names):
    for field_name in field_names:
        value = item.get(field_name)
        parsed = parse_datetime(value)
        if parsed:
            return parsed

    nested_data = item.get("data")
    if isinstance(nested_data, dict):
        for field_name in field_names:
            value = nested_data.get(field_name)
            parsed = parse_datetime(value)
            if parsed:
                return parsed

    return None


def get_recovery_point_items(response):
    data = response.get("data")

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("entities", "items", "recoveryPoints"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    for key in ("entities", "items", "recoveryPoints"):
        value = response.get(key)
        if isinstance(value, list):
            return value

    return []


def list_recovery_points():
    endpoints = [
        "/api/dataprotection/v4.0/config/recovery-points?$limit=100",
        "/api/dataprotection/v4.0/config/recovery-points"
    ]

    last_error = None

    for endpoint in endpoints:
        try:
            response, _ = api_request(NTNX_PRISMCENTRAL_IP, "GET", endpoint)
            return get_recovery_point_items(response)
        except Exception as exc:
            last_error = exc

    raise last_error


def get_recovery_point_id(item):
    return (
        item.get("extId")
        or item.get("id")
        or item.get("uuid")
        or item.get("recoveryPointId")
        or item.get("data", {}).get("extId") if isinstance(item.get("data"), dict) else None
    )


def get_recovery_point_name(item):
    return (
        item.get("name")
        or item.get("displayName")
        or item.get("data", {}).get("name") if isinstance(item.get("data"), dict) else None
    )


def get_recovery_point_created_at(item):
    return get_first_datetime(item, [
        "creationTime",
        "createdTime",
        "createTime",
        "createdAt",
        "creation_time",
        "created_time"
    ])


def get_recovery_point_expiration_at(item):
    return get_first_datetime(item, [
        "expirationTime",
        "expiryTime",
        "expiration_time",
        "expiry_time",
        "expiresAt"
    ])


def delete_recovery_point(rp_id):
    headers = {
        "NTNX-Request-Id": str(uuid.uuid4())
    }

    response, status = api_request(
        NTNX_PRISMCENTRAL_IP,
        "DELETE",
        f"/api/dataprotection/v4.0/config/recovery-points/{rp_id}",
        extra_headers=headers
    )

    return response, status, headers["NTNX-Request-Id"]


def list_snapshots_from_pe(pe_host):
    response, _ = api_request(pe_host, "GET", "/api/nutanix/v2.0/snapshots/")
    items = response.get("entities")

    if isinstance(items, list):
        return items

    if isinstance(response.get("snapshots"), list):
        return response.get("snapshots")

    if isinstance(response, list):
        return response

    return []


def get_snapshot_id(item):
    return (
        item.get("uuid")
        or item.get("snapshot_uuid")
        or item.get("id")
        or item.get("metadata", {}).get("uuid")
    )


def get_snapshot_name(item):
    return (
        item.get("snapshot_name")
        or item.get("name")
        or item.get("metadata", {}).get("name")
    )


def get_snapshot_created_at(item):
    return get_first_datetime(item, [
        "created_time",
        "creation_time",
        "created_time_usecs",
        "creation_time_usecs",
        "createdTime",
        "creationTime",
        "createdAt"
    ])


def wait_for_pe_task(pe_host, task_uuid, timeout=300, interval=5):
    url = f"/api/nutanix/v2.0/tasks/{task_uuid}"
    start = time.time()

    while time.time() - start < timeout:
        data, _ = api_request(pe_host, "GET", url)

        status = str(
            data.get("progress_status")
            or data.get("status")
            or data.get("operation_type")
            or ""
        ).upper()

        percentage = data.get("percentage_complete")

        if "FAILED" in status or "ABORTED" in status:
            raise RuntimeError(f"PE task {task_uuid} failed: {data}")

        if any(x in status for x in ["SUCCEEDED", "COMPLETE", "COMPLETED"]):
            return data

        if percentage == 100:
            return data

        time.sleep(interval)

    raise TimeoutError(f"PE task {task_uuid} reached timeout after {timeout}s.")


def delete_snapshot(pe_host, snapshot_id):
    response, status = api_request(
        pe_host,
        "DELETE",
        f"/api/nutanix/v2.0/snapshots/{snapshot_id}"
    )

    task_uuid = (
        response.get("task_uuid")
        or response.get("taskUuid")
        or response.get("uuid")
        or response.get("metadata", {}).get("uuid")
    )

    if task_uuid:
        wait_for_pe_task(pe_host, task_uuid)

    return response, status, task_uuid


def is_older_than(created_at, threshold):
    if not created_at:
        return False

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return created_at < threshold


def cleanup_recovery_points(older_than_days, delete_enabled, name_contains=None, include_without_creation_time=False):
    threshold = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    items = list_recovery_points()
    results = []

    for item in items:
        rp_id = get_recovery_point_id(item)
        name = get_recovery_point_name(item)
        created_at = get_recovery_point_created_at(item)
        expiration_at = get_recovery_point_expiration_at(item)

        if name_contains and name_contains.lower() not in str(name or "").lower():
            continue

        eligible = is_older_than(created_at, threshold)

        if not created_at and include_without_creation_time:
            eligible = True

        if not eligible:
            continue

        result = {
            "kind": "recovery_point",
            "api_host": NTNX_PRISMCENTRAL_IP,
            "name": name,
            "id": rp_id,
            "created_at": created_at.isoformat() if created_at else None,
            "expiration_at": expiration_at.isoformat() if expiration_at else None,
            "deleted": False,
            "status": "dry-run"
        }

        if delete_enabled:
            try:
                response, http_status, request_id = delete_recovery_point(rp_id)
                result["deleted"] = True
                result["status"] = "deleted"
                result["http_status"] = http_status
                result["request_id"] = request_id
                result["raw_response"] = response
            except Exception as exc:
                result["status"] = "failed"
                result["error"] = str(exc)

        results.append(result)

    return results


def cleanup_snapshots(older_than_days, delete_enabled, name_contains=None, include_without_creation_time=False):
    threshold = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    results = []

    for pe_host in PE_HOSTS:
        items = list_snapshots_from_pe(pe_host)

        for item in items:
            snapshot_id = get_snapshot_id(item)
            name = get_snapshot_name(item)
            created_at = get_snapshot_created_at(item)

            if name_contains and name_contains.lower() not in str(name or "").lower():
                continue

            eligible = is_older_than(created_at, threshold)

            if not created_at and include_without_creation_time:
                eligible = True

            if not eligible:
                continue

            result = {
                "kind": "snapshot",
                "api_host": pe_host,
                "name": name,
                "id": snapshot_id,
                "created_at": created_at.isoformat() if created_at else None,
                "deleted": False,
                "status": "dry-run"
            }

            if delete_enabled:
                try:
                    response, http_status, task_uuid = delete_snapshot(pe_host, snapshot_id)
                    result["deleted"] = True
                    result["status"] = "deleted"
                    result["http_status"] = http_status
                    result["task_uuid"] = task_uuid
                    result["raw_response"] = response
                except Exception as exc:
                    result["status"] = "failed"
                    result["error"] = str(exc)

            results.append(result)

    return results


def print_results(results, delete_enabled):
    mode_text = "DELETE MODE" if delete_enabled else "DRY-RUN MODE"
    print(f"\nCleanup result ({mode_text})")
    print("=" * (17 + len(mode_text)))

    if not results:
        print("No matching items found.")
        return

    for item in results:
        print("-" * 80)
        print(f"Type: {item.get('kind')}")
        print(f"API host: {item.get('api_host')}")
        print(f"Name: {item.get('name')}")
        print(f"ID: {item.get('id')}")
        print(f"Created at: {item.get('created_at')}")
        if item.get("expiration_at"):
            print(f"Expiration at: {item.get('expiration_at')}")
        print(f"Status: {item.get('status')}")
        if item.get("request_id"):
            print(f"Request ID: {item.get('request_id')}")
        if item.get("task_uuid"):
            print(f"Task UUID: {item.get('task_uuid')}")
        if item.get("error"):
            print(f"Error: {item.get('error')}")

    deleted = sum(1 for item in results if item.get("deleted"))
    failed = sum(1 for item in results if item.get("status") == "failed")

    print("-" * 80)
    print(f"Matching items: {len(results)}")
    print(f"Deleted items: {deleted}")
    print(f"Failed items: {failed}")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up old Nutanix recovery points and Prism Element snapshots."
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=["recovery", "snapshot", "both"],
        help="Cleanup mode"
    )
    parser.add_argument(
        "--older-than-days",
        required=True,
        type=int,
        help="Only include items older than this number of days"
    )
    parser.add_argument(
        "--name-contains",
        required=False,
        help="Optional name filter. Only matching items will be included."
    )
    parser.add_argument(
        "--include-without-creation-time",
        action="store_true",
        help="Also include items where no creation timestamp could be detected"
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete matching items. Without this flag, the script runs in dry-run mode."
    )
    parser.add_argument(
        "--json-file",
        required=False,
        help="Optional path to write cleanup results as JSON"
    )

    args = parser.parse_args()

    if args.older_than_days < 1:
        raise ValueError("--older-than-days must be at least 1")

    results = []

    if args.mode in ("recovery", "both"):
        results.extend(cleanup_recovery_points(
            older_than_days=args.older_than_days,
            delete_enabled=args.delete,
            name_contains=args.name_contains,
            include_without_creation_time=args.include_without_creation_time
        ))

    if args.mode in ("snapshot", "both"):
        results.extend(cleanup_snapshots(
            older_than_days=args.older_than_days,
            delete_enabled=args.delete,
            name_contains=args.name_contains,
            include_without_creation_time=args.include_without_creation_time
        ))

    print_results(results, args.delete)

    if args.json_file:
        with open(args.json_file, "w", encoding="utf-8") as file:
            json.dump(results, file, indent=2, ensure_ascii=False)
        print(f"\nJSON output written to: {args.json_file}")

    if any(item.get("status") == "failed" for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
