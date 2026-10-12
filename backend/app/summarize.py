#!/usr/bin/env python3
"""Per-customer problem summaries, built from the `devices` and `routers` tables.

For each customer (grouped by login_id) this aggregates that customer's own
device rows plus their router/gateway details, then asks an OpenAI-compatible
LLM gateway for a short, problem-focused summary. The `customers` table is
never read.

Results are printed, optionally saved to customer_summaries.md, and written to
a `customer_summaries` table.

Usage:
    python summarize.py                  # every customer
    python summarize.py --limit 5        # first 5 customers
    python summarize.py --login-id X@unifi
    python summarize.py --overall        # one global summary (device data only)
    python summarize.py --no-db          # don't write the customer_summaries table
    python summarize.py --save
"""

import argparse
import os
import re
import sys
import time
from collections import Counter, defaultdict

import requests
from dotenv import load_dotenv
from urllib3.exceptions import InsecureRequestWarning

try:
    import psycopg2
except ImportError:
    psycopg2 = None

load_dotenv()

DB = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "55432")),
    "dbname": os.getenv("DB_NAME", "unifi"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
}

# Column order matters - customer_facts() reads these by index.
DEVICES_SQL = """
    SELECT login_id, device_type, link_type, manufacturer, brand,
           friendly_name, rssi, rx_rate, tx_rate, platform, cloud_device_type
    FROM devices
    ORDER BY login_id
"""

LOGIN_IDS_SQL = "SELECT DISTINCT login_id FROM devices ORDER BY login_id"

# Current router models. Anything else is considered outdated.
NEW_ROUTER_MODELS = {"AX3000", "BE7200"}

# Plan-upgrade signal: high usage, many devices, and the assigned plan is below 1Gbps.
HIGH_USAGE_GB = 1000
MANY_DEVICES = 8
# The AI chooses the order actions; only these values can appear in the UI.
ALLOWED_ACTIONS = ("mesh", "speed", "reboot")
PLAN_SPEEDS = {"100Mbps": 100, "300Mbps": 300, "500Mbps": 500, "1Gbps": 1000, "2Gbps": 2000}

ROUTERS_SQL = """
    SELECT login_id, serial_number, manufacturer, model, cpu_usage_pct,
           cpu_temperature_c, memory_usage_pct, monthly_usage_gb, rx_power_dbm
    FROM routers
    ORDER BY login_id
"""

PRODUCTS_SQL = "SELECT plan_name, price_per_month FROM product" 
CUSTOMER_PLANS_SQL = "SELECT login_id, plan_name FROM customers"

# Overall summary - every figure derived from the devices table only.
OVERALL_QUERIES = {
    "totals": "SELECT count(DISTINCT login_id), count(*) FROM devices",
    "devices_per_customer": """
        SELECT min(n), max(n), round(avg(n), 2) FROM (
            SELECT login_id, count(*) AS n FROM devices GROUP BY login_id
        ) t
    """,
    "devices_by_link_type": "SELECT link_type, count(*) FROM devices GROUP BY 1 ORDER BY 2 DESC",
    "devices_by_role": "SELECT cloud_device_type, count(*) FROM devices GROUP BY 1 ORDER BY 2 DESC",
    "top_manufacturers": "SELECT manufacturer, count(*) FROM devices GROUP BY 1 ORDER BY 2 DESC LIMIT 8",
    "signal_health": """
        SELECT count(*) FILTER (WHERE rssi < -80),
               count(*) FILTER (WHERE rssi IS NOT NULL),
               round(avg(rssi), 1)
        FROM devices
    """,
}

CUSTOMER_SYSTEM = (
    "You are a network operations analyst writing a ticket note for a telecom "
    "engineer. You are given facts about ONE customer's home network, derived "
    "from its devices and its router/gateway.\n"
    "Reply with EXACTLY three lines and nothing else:\n"
    "PROBLEM: list EVERY significant problem you can find in the facts, one per "
    "sentence - there is usually more than one (for example weak WiFi signal, "
    "several devices with poor RSSI, high "
    "router CPU usage or CPU temperature, high memory usage, high monthly usage, "
    "weak optical RX power, or an outdated router model). Cite the supporting "
    "evidence for each (device counts, RSSI values, CPU %, memory %, usage GB, "
    "RX dBm) and explain its impact. Do NOT state any severity, urgency or "
    "priority rating.\n"
    "SUGGESTION: give a concrete action for EVERY problem you listed, with a "
    "short reason for each - never leave a listed problem without an action. "
    "Choose from: add a mesh node or repeater to extend coverage; move the device "
    "closer to the router or reposition the access point ; upgrade the internet plan; "
    "replace the router; reboot the router; contact the ISP about the optical/fibre "
    "signal.\n"
    "Do NOT suggest reducing, limiting or disconnecting the customer's devices.\n"
    "If the router model is outdated, you must recommend replacing the router.\n"
    "If the facts include a 'Recommended action: upgrade to a higher-speed WiFi "
    "plan' line, you must include that plan upgrade in your solution. Do not decide "
    "the plan upgrade yourself from the raw device count: access points and mesh "
    "nodes are not end devices and must not be counted towards it.\n"
    "If the facts include a 'Recommended action: reboot the router' line, you must "
    "include rebooting the router in your solution.\n"
    "When the problem is high router CPU or memory usage, recommend rebooting the "
    "router first, and also say that if the reboot does not fix the problem the "
    "router should be replaced.\n"
    "Only recommend actions the facts support.\n"
    "ACTIONS: the order actions the telecom engineer should be offered, as a "
    "comma-separated list using only these exact words: mesh, speed, reboot. "
    "Decide them from the problem and solution above - include 'mesh' only if "
    "the solution adds a mesh node or repeater, 'speed' only if it upgrades the "
    "internet plan, and 'reboot' only if it reboots the router. Leave the line "
    "empty if no order action is needed.\n"
    "Write in simple, plain English that a non-technical customer can easily "
    "understand. Use short sentences and everyday words, and avoid jargon or "
    "complicated vocabulary - for example say 'weak WiFi signal' instead of "
    "'signal degradation', 'the connection drops on and off' instead of "
    "'intermittent connectivity', and 'the router is working too hard' instead "
    "of 'resource contention'. Keep well-known units (GHz, RSSI, dBm). Begin "
    "every sentence with a capital letter, do not capitalise ordinary words in "
    "the middle of a sentence, and do not use all-caps words. No markdown, no "
    "bullets, no headings."
)

OVERALL_SYSTEM = (
    "You are a network operations analyst. Given aggregated facts about a "
    "network's devices, write a concise executive summary (around 150-200 "
    "words) covering scale, device/connection mix, signal-health concerns and "
    "notable outliers. Plain English."
)

def connect():
    if psycopg2 is None:
        sys.exit("Missing dependency: pip install -r requirements.txt")
    return psycopg2.connect(**DB)


def bullets(rows, indent="  "):
    return "\n".join(f"{indent}{label}: {count}" for label, count in rows)


DEVICE_LIMIT_WORDS = (
    "reduce the number", "limit the number", "fewer devices", "fewer connected",
    "disconnect", "remove devices", "reduce the connected", "limit connected",
    "reduce the amount", "reduce device",
)

SEVERITY_WORDS = ("severity", "urgency", "priority")

# If the solution mentions one of these, the matching action must be offered.
ACTION_TRIGGERS = {
    "mesh": ("mesh", "repeater", "extend coverage"),
    "speed": ("upgrade the internet plan", "upgrade to a higher-speed",
              "higher-speed plan", "higher-speed internet", "upgrade the plan",
              "upgrade speed"),
    "reboot": ("reboot", "restart the router"),
}


def sync_actions(suggestion, actions):
    """Guarantee every action the solution mentions is present in ACTIONS."""
    text = (suggestion or "").lower()
    synced = list(actions)
    for key, words in ACTION_TRIGGERS.items():
        if any(word in text for word in words) and key not in synced:
            synced.append(key)
    return [key for key in ALLOWED_ACTIONS if key in synced]


def strip_device_limits(text):
    """Drop any clause that tells the customer to cut down / disconnect their devices."""
    if not text:
        return text
    parts = re.split(r"(?<=[.;])\s+", text)
    kept = [p for p in parts if not any(w in p.lower() for w in DEVICE_LIMIT_WORDS)]
    return " ".join(p for p in kept if p.strip()).strip()


def sentence_case(text):
    """Capitalise the first letter of the text and of each following sentence."""
    if not text:
        return text
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def strip_severity(text):
    """Drop any sentence that states a severity / urgency / priority rating."""
    if not text:
        return text
    parts = re.split(r"(?<=[.!?])\s+", text)
    kept = [p for p in parts if not any(w in p.lower() for w in SEVERITY_WORDS)]
    return " ".join(p for p in kept if p.strip()).strip()


def parse_reply(text):
    """Split the model's PROBLEM / SUGGESTION / ACTIONS reply into parts."""
    problem_m = re.search(
        r"PROBLEM:\s*(.+?)(?=\s*\n\s*(?:SUGGESTION|ACTIONS|PROBLEM):|$)", text, re.S | re.I)
    suggest_m = re.search(
        r"SUGGESTION:\s*(.+?)(?=\s*\n\s*(?:ACTIONS|PROBLEM|SUGGESTION):|$)", text, re.S | re.I)
    actions_m = re.search(r"ACTIONS:\s*(.*)", text, re.S | re.I)

    problem = problem_m.group(1).strip() if problem_m else text.strip()
    suggestion = suggest_m.group(1).strip() if suggest_m else ""
    suggestion = re.sub(r"\s*(?:PROBLEM|SUGGESTION|ACTIONS):\s*", " ", suggestion, flags=re.I).strip()
    suggestion = strip_device_limits(suggestion)

    # The actions are decided by the model; keep only recognised order types.
    actions = []
    if actions_m:
        raw = re.sub(r"(?:PROBLEM|SUGGESTION|ACTIONS):", " ", actions_m.group(1), flags=re.I)
        for word in re.split(r"[,\n;/]+", raw):
            key = word.strip().lower()
            if key in ALLOWED_ACTIONS and key not in actions:
                actions.append(key)
    actions = sync_actions(suggestion, actions)
    return (sentence_case(strip_severity(problem)),
            sentence_case(strip_severity(suggestion)), actions)


def ensure_coverage_action(suggestion, actions, facts):
    """Guarantee a mesh recommendation whenever weak WiFi coverage is in the facts."""
    if "Recommended action: add a mesh node" not in facts:
        return suggestion, actions
    text = (suggestion or "").strip()
    if not re.search(r"mesh|repeater|extend coverage", text, re.I):
        text = (text.rstrip() + " Add a mesh node or repeater to fix the weak WiFi "
                               "coverage.").strip()
    if "mesh" not in actions:
        actions = [key for key in ALLOWED_ACTIONS if key in (list(actions) + ["mesh"])]
    return text, actions


def ensure_reboot_escalation(suggestion, facts):
    """Guarantee the reboot -> replace escalation whenever reboot is recommended."""
    if "Recommended action: reboot the router" not in facts:
        return suggestion
    text = (suggestion or "").strip()
    low = text.lower()
    if "reboot" not in low and "restart" not in low:
        text = (text + " Reboot the router to clear the high CPU usage or temperature.").strip()
        low = text.lower()
    if "replace" not in low:
        text = (text.rstrip() + " If rebooting the router does not fix the problem, "
                               "the router should be replaced.")
    return text


def enforce_required_actions(suggestion, facts):
    """Ensure deterministic business actions requested by the device/router facts."""
    actions = [suggestion.strip()] if suggestion.strip() else []
    if "Recommended action: upgrade to a higher-speed WiFi plan" in facts and not re.search(
        r"upgrade.{0,45}(plan|speed)|higher.speed", suggestion, re.I
    ):
        actions.append("Upgrade to a higher-speed internet plan to better support the customer's usage and connected devices.")
    if "outdated model, replacement recommended" in facts and not re.search(
        r"replace.{0,35}router|router.{0,35}replace", suggestion, re.I
    ):
        actions.append("Replace the outdated router with a current model.")
    if "Recommended action: reboot the router" in facts and not re.search(
        r"reboot|restart", suggestion, re.I
    ):
        actions.append("Reboot the router to clear the high CPU usage or temperature.")
    return " ".join(actions)


def customer_facts(login_id, devices, router, plan_name=None, plan_price=None):
    n = len(devices)
    roots = sum(1 for d in devices if d[1] == "Root")
    links = Counter(d[2] for d in devices)
    roles = Counter(d[10] for d in devices)
    mfrs = Counter(d[3] for d in devices)
    mesh = sum(1 for d in devices if d[1] != "Root" and d[10] == "Access Point")
    iot = roles.get("IoT", 0)

    wireless = [d for d in devices if d[6] is not None]
    weak = [d for d in wireless if d[6] < -80]
    avg_rssi = round(sum(d[6] for d in wireless) / len(wireless), 1) if wireless else None

    lines = [
        f"Customer login ID: {login_id}",
        f"Devices: {n} total ({roots} root, {n - roots} clients, of which {mesh} are access-point nodes)",
        f"Connected end devices (excluding access points): {n - roots - mesh}",
        "Connection types: " + ", ".join(f"{k} {v}" for k, v in links.most_common()),
        "Device roles: " + ", ".join(f"{k} {v}" for k, v in roles.most_common()),
        f"Mesh/AP nodes: {mesh} | IoT devices: {iot}",
        "Manufacturers: " + ", ".join(f"{k} {v}" for k, v in mfrs.most_common(5)),
    ]

    monthly = None
    cpu = temp = None
    if router:
        (_lid, serial, mfr, model, cpu, temp, mem_pct, monthly, rx) = router
        lines += [
            f"Router: {mfr} {model} (serial {serial}) - "
            f"{'current model' if model in NEW_ROUTER_MODELS else 'outdated model, replacement recommended'}",
            f"Router CPU: {cpu}% ({'high' if cpu > 65 else 'normal'}) | "
            f"CPU temperature: {temp} C ({'high' if temp > 65 else 'normal'})",
            f"Router memory used: {mem_pct}% | monthly usage {monthly} GB",
            f"Optical RX power: {rx} dBm ({'weak' if rx < -28 else 'normal'})",
        ]
    else:
        lines.append("Router: no router record")

    if (cpu or 0) > 65 or (temp or 0) > 65:
        lines.append(
            "Recommended action: reboot the router - CPU usage or CPU temperature is high.")

    if wireless and weak:
        lines.append(
            f"Recommended action: add a mesh node or repeater - {len(weak)} of "
            f"{len(wireless)} wireless devices have a weak WiFi signal "
            f"(worst {min(d[6] for d in wireless)} dBm).")

    plan_speed = None
    for label, speed in PLAN_SPEEDS.items():
        if plan_name and label in plan_name:
            plan_speed = speed
            break
    if plan_name:
        price_text = f"RM {plan_price}/month" if plan_price is not None else "price unavailable"
        lines.append(f"Current WiFi plan: {plan_name} ({price_text})")

    end_devices = n - roots - mesh
    plan_upgrade_needed = (
        monthly is not None
        and monthly >= HIGH_USAGE_GB
        and end_devices >= MANY_DEVICES
        and plan_speed is not None
        and plan_speed < 1000
    )
    if plan_upgrade_needed:
        lines.append(
            f"Recommended action: upgrade to a higher-speed WiFi plan. Monthly usage is "
            f"{monthly} GB with {end_devices} end devices (access points are not counted); "
            f"the current plan is {plan_speed} Mbps."
        )

    if wireless:
        lines.append(
            f"Wireless signal: {len(weak)} of {len(wireless)} wireless devices are weak "
            f"(RSSI below -80 dBm); average RSSI {avg_rssi} dBm, worst "
            f"{min(d[6] for d in wireless)} dBm"
        )
        worst = sorted(wireless, key=lambda d: d[6])[:3]
        lines.append(
            "Worst devices: " + ", ".join(f"{d[5]} ({d[6]} dBm, {d[2]})" for d in worst)
        )
    else:
        lines.append("Wireless signal: no wireless clients")
    return "\n".join(lines)


def tls_verify():
    """Value for requests' verify= : a CA bundle path, True, or False."""
    ca = os.getenv("LLM_CA_BUNDLE", "").strip()
    if ca:
        return ca
    if os.getenv("LLM_VERIFY_TLS", "true").strip().lower() in ("false", "0", "no", "off"):
        return False
    return True


def call_chat(base_url, model, key, system, user):
    """Call an OpenAI-compatible /chat/completions endpoint."""
    verify = tls_verify()
    if verify is False:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    resp = requests.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        verify=verify,
    )
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices") or []
    message = (choices[0].get("message") if choices else None) or {}
    content = message.get("content")

    if content is None:
        # Some gateways return the text elsewhere, or nothing at all.
        content = message.get("reasoning_content") or message.get("text")
    if isinstance(content, list):  # content as a list of parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if content is None or not str(content).strip():
        finish = choices[0].get("finish_reason") if choices else None
        raise requests.exceptions.RequestException(
            f"Gateway returned empty content (finish_reason={finish}): {str(data)[:300]}"
        )
    return str(content).strip()


def run_llm(system, user, retries=3):
    base = os.getenv("LLM_BASE_URL", "").strip()
    key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not base:
        return None, "LLM_BASE_URL is not set in .env"
    if not key:
        return None, "LLM_API_KEY is not set in .env"
    if not model:
        return None, "LLM_MODEL is not set in .env"

    for attempt in range(1, retries + 1):
        try:
            return call_chat(base, model, key, system, user), None
        except requests.exceptions.SSLError as e:
            return None, (
                "TLS certificate verification failed (private CA). Set LLM_CA_BUNDLE=/path/ca.pem, "
                f"or dev-only LLM_VERIFY_TLS=false. ({e})"
            )
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response is not None else None
            body = e.response.text[:300] if e.response is not None else ""
            # Retry transient gateway errors (5xx).
            if code is not None and code >= 500 and attempt < retries:
                time.sleep(2 * attempt)
                continue
            return None, f"Gateway returned HTTP {code}: {body}"
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            return None, f"Request failed: {e}"


def ensure_table(conn):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_summaries (
                login_id       TEXT PRIMARY KEY REFERENCES customers(login_id) ON DELETE CASCADE,
                summary        TEXT NOT NULL,
                recommendation TEXT,
                actions        TEXT,
                model          TEXT,
                generated_at   TIMESTAMP DEFAULT now()
            );
            ALTER TABLE customer_summaries ADD COLUMN IF NOT EXISTS recommendation TEXT;
            ALTER TABLE customer_summaries ADD COLUMN IF NOT EXISTS actions TEXT;
            """
        )


def save_to_db(conn, login_id, summary, recommendation, model, actions=""):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO customer_summaries (login_id, summary, recommendation, actions, model)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (login_id) DO UPDATE
            SET summary = EXCLUDED.summary,
                recommendation = EXCLUDED.recommendation,
                actions = EXCLUDED.actions,
                model = EXCLUDED.model,
                generated_at = now()
            """,
            (login_id, summary, recommendation, actions, model),
        )


def load_devices(conn, login_id):
    """Load device, router, and assigned product-plan facts."""
    with conn.cursor() as cur:
        cur.execute(LOGIN_IDS_SQL)
        login_ids = [r[0] for r in cur.fetchall()]
        cur.execute(DEVICES_SQL)
        devices = cur.fetchall()
        cur.execute(ROUTERS_SQL)
        routers = cur.fetchall()
        cur.execute(CUSTOMER_PLANS_SQL)
        plans = cur.fetchall()
        cur.execute(PRODUCTS_SQL)
        products = cur.fetchall()

    by_customer = defaultdict(list)
    for d in devices:
        by_customer[d[0]].append(d)
    router_by_login = {r[0]: r for r in routers}
    plan_by_login = {login: (name, products_by_name.get(name))
                     for login, name in plans
                     for products_by_name in [{p: price for p, price in products}]}

    if login_id:
        login_ids = [i for i in login_ids if i == login_id]
    return login_ids, by_customer, router_by_login, plan_by_login


def run_overall(conn, save):
    with conn.cursor() as cur:
        facts = {}
        for name, sql in OVERALL_QUERIES.items():
            cur.execute(sql)
            facts[name] = cur.fetchall()

    customers, devices = facts["totals"][0]
    mn, mx, avg = facts["devices_per_customer"][0]
    weak, measured, avg_rssi = facts["signal_health"][0]
    text = "\n".join(
        [
            f"Customers (distinct login_id in devices): {customers}",
            f"Total devices: {devices}",
            f"Devices per customer: min {mn}, max {mx}, average {avg}",
            "",
            "Devices by link type:",
            bullets(facts["devices_by_link_type"]),
            "",
            "Devices by role:",
            bullets(facts["devices_by_role"]),
            "",
            "Top manufacturers:",
            bullets(facts["top_manufacturers"]),
            "",
            f"Signal: {weak} of {measured} wireless weak (< -80), average RSSI {avg_rssi}",
        ]
    )
    summary, err = run_llm(OVERALL_SYSTEM, f"Device facts:\n\n{text}\n\nWrite the summary.")
    print(text)
    print()
    if summary:
        print("=== AI summary ===")
        print(summary)
    else:
        print(f"=== AI summary skipped: {err} ===")
    if save:
        with open("summary.md", "w") as f:
            f.write(f"# Device summary\n\n## Facts\n\n```\n{text}\n```\n\n## AI summary\n\n{summary or err}\n")
        print("\nSaved -> summary.md")


def run_per_customer(conn, args):
    login_ids, by_customer, router_by_login, plan_by_login = load_devices(conn, args.login_id)
    if args.limit:
        login_ids = login_ids[: args.limit]
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='customer_summaries'")
        if args.skip_existing and cur.fetchone():
            cur.execute("SELECT login_id FROM customer_summaries")
            done = {row[0] for row in cur.fetchall()}
            login_ids = [lid for lid in login_ids if lid not in done]
    if not login_ids:
        sys.exit("No customers to process.")

    model = os.getenv("LLM_MODEL", "").strip()
    if not args.no_db:
        ensure_table(conn)
    print(f"Processing {len(login_ids)} customer(s).")

    results = []
    for i, login_id in enumerate(login_ids, 1):
        plan_name, plan_price = plan_by_login.get(login_id, (None, None))
        facts = customer_facts(login_id, by_customer.get(login_id, []),
                               router_by_login.get(login_id), plan_name, plan_price)
        reply, err = run_llm(CUSTOMER_SYSTEM, f"Device facts for this customer:\n\n{facts}\n\nWrite the response.")

        if reply:
            problem, suggestion, actions = parse_reply(reply)
            suggestion, actions = ensure_coverage_action(suggestion, actions, facts)
            suggestion = sentence_case(ensure_reboot_escalation(suggestion, facts))
            results.append((login_id, problem, suggestion))
            print(f"[{i}/{len(login_ids)}] {login_id}")
            print(f"    PROBLEM:    {problem}")
            print(f"    SUGGESTION: {suggestion}")
            if not args.no_db:
                save_to_db(conn, login_id, problem, suggestion, model, ",".join(actions))
        else:
            print(f"[{i}/{len(login_ids)}] {login_id}: SKIPPED - {err}")
            if i == 1:
                # config/network problem - no point continuing
                break

    print(f"\nGenerated {len(results)} summary(ies).")
    if not args.no_db:
        print("Wrote results to the customer_summaries table.")

    if args.save and results:
        with open("customer_summaries.md", "w") as f:
            f.write("# Per-customer summaries (device data only)\n\n")
            for login_id, problem, suggestion in results:
                f.write(f"## {login_id}\n\n{problem}\n\n**Suggestion:** {suggestion}\n\n")
        print("Saved -> customer_summaries.md")


def main():
    parser = argparse.ArgumentParser(description="Per-customer device summaries.")
    parser.add_argument("--login-id", help="only this customer")
    parser.add_argument("--limit", type=int, help="only the first N customers")
    parser.add_argument("--skip-existing", action="store_true",
                        help="skip customers that already have a stored summary")
    parser.add_argument("--overall", action="store_true", help="one global summary instead of per-customer")
    parser.add_argument("--no-db", action="store_true", help="do not write the customer_summaries table")
    parser.add_argument("--save", action="store_true", help="also write the results to a markdown file")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.overall:
            run_overall(conn, args.save)
        else:
            run_per_customer(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()