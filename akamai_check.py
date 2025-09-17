#!/usr/bin/env python3
import subprocess, shlex, sys, time, datetime

HOST = "armmf.adobe.com"
MAC_TXT = "/arm-manifests/mac/AcrobatDC/acrobat/current_version.txt"
MAC_ARM = "/arm-manifests/mac/AcrobatDC/acrobat/AcrobatManifest.arm"
WIN_CAB = "/arm-manifests/win/SCUP/AcrobatCatalog-DC.cab"
TIMEOUT = 8  # seconds

# Ordered list of (label, resolver) — empty resolver = local
RESOLVERS = [
    ("local",     ""),
    ("vodafone",  "207.126.96.248"),
    ("google",    "8.8.8.8"),
    ("cloudflare","1.1.1.1"),
    ("quad9",     "9.9.9.9"),
    ("opendns",   "208.67.222.222"),
]

SHOW_BODY = "--show-body" in sys.argv

def run(cmd, timeout=TIMEOUT):
    try:
        p = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"

def dig(host, rrtype="A", resolver=""):
    if resolver:
        cmd = f"dig +short @{resolver} {host} {rrtype}"
    else:
        cmd = f"dig +short {host} {rrtype}"
    rc, out, err = run(cmd)
    ips = []
    if rc == 0 and out:
        for line in out.splitlines():
            line = line.strip()
            if rrtype == "A" and line.count(".") == 3:
                ips.append(line)
            if rrtype == "AAAA" and ":" in line:
                ips.append(line)
    return ips

def curl_head(ip, path):
    url = f"https://{HOST}{path}"
    cmd = f'curl -m {TIMEOUT} -sSI --resolve {HOST}:443:{ip} {url}'
    rc, out, err = run(cmd)
    if rc != 0:
        return {}
    headers = {}
    for line in out.splitlines():
        if line.startswith("HTTP/"):
            headers["HTTP"] = line
        else:
            k = line.split(":", 1)[0].strip().lower()
            v = line.split(":", 1)[1].strip() if ":" in line else ""
            if k in {"content-length","etag","last-modified","date","akamai-grn","x-n","server"}:
                headers[k] = v
    return headers

def curl_body(ip, path, max_bytes=128):
    url = f"https://{HOST}{path}"
    cmd = f'curl -m {TIMEOUT} -s --resolve {HOST}:443:{ip} {url}'
    rc, out, err = run(cmd)
    if rc != 0:
        return "", 0
    return out[:max_bytes], len(out)

def line(title, value):
    print(f"{title:<11} | {value}")

def main():
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"==== Adobe/Akamai multi-resolver check @ {ts} ====")
    print(f"Host: {HOST}")
    print()

    # A/AAAA per resolver
    print("==== DNS SUMMARY (A / AAAA) ====")
    all_v4 = set()
    for name, resolver in RESOLVERS:
        a = dig(HOST, "A", resolver)
        aaaa = dig(HOST, "AAAA", resolver)
        if a: all_v4.update(a)
        line(name, f"A: {', '.join(a) if a else 'none'} | AAAA: {', '.join(aaaa) if aaaa else 'none'}")
    if not all_v4:
        print("\nNo IPv4 edges found. Exiting.")
        sys.exit(1)

    print("\n==== EDGE CHECKS (mac + win controls) ====")
    for ip in sorted(all_v4):
        print(f"\n>> EDGE {ip}  (MAC TXT: {MAC_TXT})")
        h1 = curl_head(ip, MAC_TXT)
        if h1:
            print("   ", h1.get("HTTP",""))
            for k in ("content-length","etag","last-modified","date","akamai-grn","x-n","server"):
                if k in h1: print(f"    - {k}: {h1[k]}")
        else:
            print("    (no headers / timeout)")

        body_preview = ""
        body_len = 0
        if SHOW_BODY:
            body_preview, body_len = curl_body(ip, MAC_TXT)
            print(f"    - body(len={body_len}): {repr(body_preview)}")
        else:
            # still measure length without printing content
            _, body_len = curl_body(ip, MAC_TXT)
            print(f"    - body length: {body_len}")

        print(f"-- (MAC ARM: {MAC_ARM})")
        h2 = curl_head(ip, MAC_ARM)
        if h2:
            print("   ", h2.get("HTTP",""))
            for k in ("content-length","etag","last-modified","date","akamai-grn","x-n","server"):
                if k in h2: print(f"    - {k}: {h2[k]}")
        else:
            print("    (no headers / timeout)")

        print(f"-- (WIN CAB: {WIN_CAB})")
        h3 = curl_head(ip, WIN_CAB)
        if h3:
            print("   ", h3.get("HTTP",""))
            for k in ("content-length","etag","last-modified","date","akamai-grn","x-n","server"):
                if k in h3: print(f"    - {k}: {h3[k]}")
        else:
            print("    (no headers / timeout)")

    print("\n==== INTERPRETATION HINTS ====")
    print("- Good edge for mac: MAC TXT content-length == 12 and body length == 12 (e.g., '25.001.20693').")
    print("- Bad edge for mac: MAC TXT content-length == 0 (empty); WIN CAB typically still non-zero.")
    print("- If resolvers in the same country map to different edges, that’s Akamai DNS steering differences.")

if __name__ == "__main__":
    main()
