#!/usr/bin/env python3
"""
resolver_pop_tester.py

Check how different recursive DNS resolvers steer armmf.adobe.com to Akamai
edges, and verify each edge by fetching the mac manifest endpoints.

Classification:
- GOOD:  current_version.txt body length == 12 (and non-zero .arm)
- BAD:   current_version.txt body length == 0   (often .arm is 0 too)
- MIXED: multiple IPs with mixed results
- UNK:   could not fetch/timeout

Usage:
  python3 resolver_pop_tester.py [--show-headers] [--timeout 8]
"""

import subprocess, shlex, sys, argparse, textwrap
from collections import defaultdict

HOST = "armmf.adobe.com"
MAC_TXT = "/arm-manifests/mac/AcrobatDC/acrobat/current_version.txt"
MAC_ARM = "/arm-manifests/mac/AcrobatDC/acrobat/AcrobatManifest.arm"

# Resolver label -> IP (empty string = system default)
RESOLVERS = [
    ("local",        ""),
    ("opendns-1",    "208.67.222.222"),
    ("opendns-2",    "208.67.220.220"),
    ("lumen-1",      "4.2.2.1"),
    ("lumen-2",      "4.2.2.2"),
    ("quad9-1",      "9.9.9.9"),
    ("quad9-2",      "149.112.112.112"),
    ("comodo-1",     "8.26.56.26"),
    ("comodo-2",     "8.20.247.20"),
    ("google",       "8.8.8.8"),
    ("cloudflare",   "1.1.1.1"),
    ("vodafone-zayo","207.126.96.248"),
]

def run(cmd: str, timeout: int):
    try:
        p = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"

def dig(host: str, rrtype: str, resolver: str, timeout: int):
    cmd = f"dig +short {host} {rrtype}"
    if resolver:
        cmd = f"dig +short @{resolver} {host} {rrtype}"
    rc, out, _ = run(cmd, timeout=timeout)
    if rc != 0 or not out:
        return []
    ips = []
    for line in out.splitlines():
        line = line.strip()
        if rrtype == "A" and line.count(".") == 3:
            ips.append(line)
        elif rrtype == "AAAA" and ":" in line:
            ips.append(line)
    # De-dupe while preserving order
    seen = set(); ordered = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip); ordered.append(ip)
    return ordered

def curl_head(ip: str, path: str, timeout: int):
    url = f"https://{HOST}{path}"
    cmd = f'curl -m {timeout} -sSI --resolve {HOST}:443:{ip} {url}'
    rc, out, err = run(cmd, timeout=timeout)
    if rc != 0:
        return {}
    headers = {}
    for line in out.splitlines():
        if line.startswith("HTTP/"):
            headers["HTTP"] = line
        elif ":" in line:
            k, v = line.split(":", 1)
            k = k.strip().lower()
            v = v.strip()
            headers[k] = v
    return headers

def curl_body_len(ip: str, path: str, timeout: int):
    url = f"https://{HOST}{path}"
    cmd = f'curl -m {timeout} -s --resolve {HOST}:443:{ip} {url}'
    rc, out, err = run(cmd, timeout=timeout)
    if rc != 0:
        return -1
    return len(out)

def classify_edge(ip: str, timeout: int, show_headers: bool):
    # Check TXT first (fast, authoritative signal)
    h_txt = curl_head(ip, MAC_TXT, timeout)
    len_txt = curl_body_len(ip, MAC_TXT, timeout)

    h_arm = curl_head(ip, MAC_ARM, timeout)
    len_arm = int(h_arm.get("content-length", "0")) if h_arm else -1

    status = "UNK"
    if len_txt == 12:
        status = "GOOD"
    elif len_txt == 0:
        status = "BAD"

    details = {
        "ip": ip,
        "txt_len": len_txt,
        "arm_len": len_arm,
        "txt_etag": (h_txt or {}).get("etag", ""),
        "arm_etag": (h_arm or {}).get("etag", ""),
        "txt_http": (h_txt or {}).get("HTTP", ""),
        "arm_http": (h_arm or {}).get("HTTP", ""),
        "txt_date": (h_txt or {}).get("date", ""),
        "arm_date": (h_arm or {}).get("date", ""),
        "ak_grn_txt": (h_txt or {}).get("akamai-grn", ""),
        "ak_grn_arm": (h_arm or {}).get("akamai-grn", ""),
    }
    if show_headers:
        details["txt_headers"] = h_txt
        details["arm_headers"] = h_arm
    return status, details

def main():
    ap = argparse.ArgumentParser(description="Test resolver → Akamai edge mapping for armmf.adobe.com")
    ap.add_argument("--timeout", type=int, default=8, help="curl/dig timeout seconds (default: 8)")
    ap.add_argument("--show-headers", action="store_true", help="print raw headers per edge")
    args = ap.parse_args()

    print("== Resolver → Edge → Classification ==")
    print(f"Host: {HOST}")
    print()

    for name, resolver in RESOLVERS:
        a_records = dig(HOST, "A", resolver, args.timeout)
        if not a_records:
            print(f"[{name:<13}] A: (none)  →  SKIP")
            continue

        results = []
        for ip in a_records:
            status, info = classify_edge(ip, args.timeout, args.show_headers)
            results.append((status, info))

        # Summarize for resolver
        statuses = {s for s, _ in results}
        if statuses == {"GOOD"}:
            overall = "GOOD"
        elif statuses == {"BAD"}:
            overall = "BAD"
        elif len(statuses) == 0:
            overall = "UNK"
        else:
            overall = "MIXED"

        # Pretty print
        ips = ", ".join([r[1]["ip"] for r in results])
        print(f"[{name:<13}] A: {ips or '(none)'}  →  {overall}")
        for s, info in results:
            print(f"   - {info['ip']}: {s:5} | txt_len={info['txt_len']:<3} | arm_len={info['arm_len']:<5} | etag_txt={info['txt_etag']}")
            if args.show_headers:
                # Nicely indent a couple of key headers
                if info.get("txt_headers"):
                    print("     > TXT:", info["txt_headers"].get("HTTP",""), "|", info["txt_headers"].get("content-length",""), info["txt_headers"].get("etag",""), info["txt_headers"].get("date",""))
                if info.get("arm_headers"):
                    print("     > ARM:", info["arm_headers"].get("HTTP",""), "|", info["arm_headers"].get("content-length",""), info["arm_headers"].get("etag",""), info["arm_headers"].get("date",""))
        print()

    guidance = textwrap.dedent("""
    Interpretation:
      - GOOD  = mac current_version.txt length == 12 (e.g., 25.001.20693) → healthy POP
      - BAD   = mac current_version.txt length == 0 → broken POP for mac manifests
      - MIXED = resolver returns multiple IPs with mixed results
      - UNK   = timeouts/errors
    Tip: If you need to force-hit a specific POP, use:
      curl -I --resolve armmf.adobe.com:443:<EDGE_IP> https://armmf.adobe.com/arm-manifests/mac/AcrobatDC/acrobat/current_version.txt
    """).strip()
    print(guidance)

if __name__ == "__main__":
    main()
