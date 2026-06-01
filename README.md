# Nutanix Snapshot and Recovery Cleanup Script

A Python script for finding and optionally deleting old Nutanix recovery points and Prism Element snapshots.

The script runs in dry-run mode by default. It only deletes matching items when the `--delete` flag is explicitly provided.

## Features

- Lists old Nutanix v4 Data Protection recovery points through Prism Central
- Lists old Prism Element v2.0 snapshots on configured Prism Element clusters
- Supports cleanup of recovery points, snapshots, or both
- Runs in safe dry-run mode by default
- Requires `--delete` before anything is removed
- Supports filtering by item age
- Supports filtering by name
- Can write cleanup results to a JSON report
- Uses only the Python standard library

## Important Authentication Requirement

The same user account must exist on Prism Central and on every configured Prism Element cluster.

The username and password must be identical everywhere. This script uses one shared authentication token for Prism Central and all Prism Element API calls. Different users, different passwords, or separate credentials per Prism Element are not supported by this script.

## Requirements

- Python 3.8 or newer
- Network access to Nutanix Prism Central
- Network access to all configured Prism Element clusters
- A valid Nutanix API token
- Correct Prism Element host configuration

No external Python packages are required.

## Configuration

Before running the script, update these values in `nutanix_cleanup.py`:

```python
NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PE_AND_PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"

PE_HOSTS = [
    "IP_FROM_ELEMENTS_CLUSTER_1:9440",
    "IP_FROM_ELEMENTS_CLUSTER_2:9440",
    "IP_FROM_ELEMENTS_CLUSTER_3:9440",
]
```

## Usage

### Cleanup Recovery Points

Dry-run mode:

```bash
python nutanix_cleanup.py \
  --mode recovery \
  --older-than-days 14
```

Actually delete matching recovery points:

```bash
python nutanix_cleanup.py \
  --mode recovery \
  --older-than-days 14 \
  --delete
```

### Cleanup Snapshots

Dry-run mode:

```bash
python nutanix_cleanup.py \
  --mode snapshot \
  --older-than-days 14
```

Actually delete matching snapshots:

```bash
python nutanix_cleanup.py \
  --mode snapshot \
  --older-than-days 14 \
  --delete
```

### Cleanup Both Recovery Points and Snapshots

Dry-run mode:

```bash
python nutanix_cleanup.py \
  --mode both \
  --older-than-days 14
```

Actually delete matching items:

```bash
python nutanix_cleanup.py \
  --mode both \
  --older-than-days 14 \
  --delete
```

### Filter by Name

Only include items where the name contains a specific string:

```bash
python nutanix_cleanup.py \
  --mode both \
  --older-than-days 14 \
  --name-contains backup
```

### Include Items Without Creation Timestamp

By default, items without a detected creation timestamp are not included.

To include them:

```bash
python nutanix_cleanup.py \
  --mode both \
  --older-than-days 14 \
  --include-without-creation-time
```

### JSON Report

Write cleanup results to a JSON file:

```bash
python nutanix_cleanup.py \
  --mode both \
  --older-than-days 14 \
  --json-file cleanup-report.json
```

## Safety Notes

This script is intentionally conservative:

- It runs in dry-run mode by default.
- It requires `--delete` before deleting anything.
- It only includes items older than the value passed to `--older-than-days`.
- It can filter by name with `--name-contains`.
- It does not include items without a detected creation timestamp unless `--include-without-creation-time` is set.

Always run the script without `--delete` first and review the output carefully.

## Security Notes

Do not commit real API tokens, passwords, Prism Central addresses, Prism Element addresses, or internal infrastructure details to a public GitHub repository.

The script currently disables SSL certificate verification by using:

```python
ssl._create_unverified_context()
```

This may be useful in lab environments, but it is not recommended for production. For production use, configure proper certificate validation.

## Disclaimer

This script is provided as an example. Test it in a safe environment before using it against production Nutanix infrastructure.
