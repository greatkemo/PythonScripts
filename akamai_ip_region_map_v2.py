#!/usr/bin/env python3
"""
akamai_ip_region_map_v2.py

Generates a CSV mapping:
 - Akamai IPv4 CIDR blocks (Active + Removed per Akamai TechDocs) -> ASN/Org + Country/Region/City
 - Current resolved edge IPs for armmf.adobe.com across several resolvers -> ASN/Org + Country/Region/City
EXCLUDES GPS/location coordinates from the output.
Adds a "CableCutRegion" flag based on a configurable list of countries/regions affected by recent cable cuts/incidents.

Usage:
  export IPINFO_TOKEN=xxxxxxxxxxxxxxxx
  python3 akamai_ip_region_map_v2.py

Output:
  akamai_ip_region_map_v2.csv
"""

import os
import csv
import subprocess
import requests
from typing import Dict, List, Optional

IPINFO_TOKEN = os.environ.get("IPINFO_TOKEN", "YOUR_TOKEN_HERE")
HOST = "armmf.adobe.com"
CSV_OUT = "akamai_ip_region_map_v2.csv"
TIMEOUT_SECS = 7

# --- Akamai IPv4 ranges ---
# From Akamai "Update your origin server" (Origin IP ACL) and removed list (as of 2025-07-01).
ACTIVE_IPV4 = [
    "2.16.0.0/13",
    "23.0.0.0/12",
    "23.192.0.0/11",
    "23.32.0.0/11",
    "95.100.0.0/15",
    "184.24.0.0/13",
]
REMOVED_IPV4 = [
    "23.64.0.0/14",
    "23.72.0.0/13",
    "69.192.0.0/16",
    "72.246.0.0/15",
    "88.221.0.0/16",
    "92.122.0.0/15",
    "96.16.0.0/15",
    "96.6.0.0/15",
    "104.64.0.0/10",
    "118.214.0.0/16",
    "172.224.0.0/12",
    "172.232.0.0/13",
    "172.224.0.0/13",
    "173.222.0.0/15",
    "184.50.0.0/15",
    "184.84.0.0/14",
]

# Some Akamai edges (seen in your tests) also appear outside the Origin IP ACL "active" list.
# We include them via REMOVED_IPV4 above for completeness.

# --- Resolvers to compare ---
RESOLVERS = {
    "local": None,            # system default
    "google": "8.8.8.8",
    "cloudflare": "1.1.1.1",
    "quad9": "9.9.9.9",
    "opendns": "208.67.222.222",
}

# --- Cable-cut/incident correlation heuristics ---
# Countries/regions widely reported as impacted during early/mid Sep 2025 disruptions
AFFECTED_COUNTRIES = {
    # South Asia / Middle East / EMEA of interest
    "IN",  # India
    "IT",  # Italy (Milan incident)
    "BR",  # Brazil (São Paulo incident)
    "EG",  # Egypt (Red Sea crossings & landing points)
    "SA",  # Saudi Arabia
    "AE",  # UAE
    "QA",  # Qatar
    "OM",  # Oman
    "BH",  # Bahrain
    "KW",  # Kuwait
}

AFFECTED_REGIONS_KEYWORDS = {
    "Middle East",
    "West Asia",
    "Gulf",
    "São Paulo", "Sao Paulo",
    "Milan", "Lombardy",
    "Chennai", "Mumbai", "Maharashtra", "Tamil Nadu",
}

def cable_cut_flag(country: str, region: str, city: str) -> str:
    c = (country or "").strip().upper()
    r = (region or "").strip()
    ct = (city or "").strip()
    if c in AFFECTED_COUNTRIES:
        return "Likely"
    text = f"{r} {ct}"
    for kw in AFFECTED_REGIONS_KEYWORDS:
        if kw.lower() in text.lower():
            return "Likely"
    return "No"

# --- Helpers ---
def sample_ip_in_cidr(cidr: str) -> str:
    base = cidr.split("/")[0]
    parts = base.split(".")
    # Choose a simple sample in-range IP (x.y.z.1)
    return ".".join(parts[:3] + ["1"])

def ipinfo_lookup(ip: str) -> Dict[str, str]:
    if IPINFO_TOKEN in ("", "YOUR_TOKEN_HERE", None):
        return {}
    url = f"https://ipinfo.io/{ip}?token={IPINFO_TOKEN}"
    try:
        r = requests.get(url, timeout=TIMEOUT_SECS)
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}

def dig_query(resolver: Optional[str]) -> List[str]:
    cmd = ["dig", "+short", HOST]
    if resolver:
        cmd.insert(1, f"@{resolver}")
    try:
        out = subprocess.check_output(cmd, text=True, timeout=TIMEOUT_SECS)
    except Exception:
        return []
    ips = []
    for line in out.splitlines():
        line = line.strip()
        if line and line[0].isdigit():
            ips.append(line)
    return ips

def main():
    rows = []
    fieldnames = [
        "Source",          # CIDR or Resolved(<name>)
        "Status",          # Active / Removed for CIDR rows
        "Input",           # CIDR or Host
        "IP",              # Sample IP for CIDR; resolved IP for Resolved rows
        "ASN",
        "Org",
        "Country",
        "Region",
        "City",
        "Anycast",
        "CableCutRegion",  # Likely / No
    ]

    # 1) Add ALL CIDR blocks (Active + Removed)
    for cidr in ACTIVE_IPV4 + REMOVED_IPV4:
        status = "Active" if cidr in ACTIVE_IPV4 else "Removed"
        sample_ip = sample_ip_in_cidr(cidr)
        info = ipinfo_lookup(sample_ip)

        org = info.get("org", "")
        asn = org.split()[0] if org else ""
        org_name = " ".join(org.split()[1:]) if org else ""

        country = info.get("country", "") or ""
        region = info.get("region", "") or ""
        city = info.get("city", "") or ""
        anycast = str(info.get("anycast", "")) if "anycast" in info else ""

        rows.append({
            "Source": "CIDR",
            "Status": status,
            "Input": cidr,
            "IP": sample_ip,
            "ASN": asn,
            "Org": org_name,
            "Country": country,
            "Region": region,
            "City": city,
            "Anycast": anycast,
            "CableCutRegion": cable_cut_flag(country, region, city),
        })

    # 2) Add resolved edges for HOST from multiple resolvers (unique IPs)
    seen = set()
    for name, resolver in RESOLVERS.items():
        ips = dig_query(resolver)
        for ip in ips:
            if ip in seen:
                continue
            seen.add(ip)

            info = ipinfo_lookup(ip)
            org = info.get("org", "")
            asn = org.split()[0] if org else ""
            org_name = " ".join(org.split()[1:]) if org else ""

            country = info.get("country", "") or ""
            region = info.get("region", "") or ""
            city = info.get("city", "") or ""
            anycast = str(info.get("anycast", "")) if "anycast" in info else ""

            rows.append({
                "Source": f"Resolved({name})",
                "Status": "",
                "Input": HOST,
                "IP": ip,
                "ASN": asn,
                "Org": org_name,
                "Country": country,
                "Region": region,
                "City": city,
                "Anycast": anycast,
                "CableCutRegion": cable_cut_flag(country, region, city),
            })

    # 3) Write CSV (no GPS/loc fields included)
    with open(CSV_OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote: {CSV_OUT}")
    # Pretty print summary
    for r in rows:
        print(f"{r['Source']:16} | {r['Status'] or '-':7} | {r['Input']:16} | {r['IP']:15} | "
              f"{r['ASN']:10} | {r['Org'][:30]:30} | {r['Country']:2} | {r['Region'][:16]:16} | "
              f"{r['City'][:16]:16} | CableCutRegion={r['CableCutRegion']}")

if __name__ == "__main__":
    main()
