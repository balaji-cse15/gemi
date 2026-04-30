# Gemi — Legal & Ethical Use Disclaimer

**Last updated:** 2026

## TL;DR

Gemi includes offensive-security tools that can be misused. **You may
only use them on systems you own or have explicit written permission to
test.** Anything else is illegal in most jurisdictions and is not what
this software is intended for.

---

## 1. The tools

Gemi bundles tools commonly used in security testing, including but not
limited to:

| Category | Tools |
|---|---|
| Exploit payloads | `exploits` (SQLi, XSS, SSRF, XXE, SSTI, NoSQL, LDAP, command injection, path traversal, prototype pollution, JWT, CORS, HTTP smuggling, open redirect — 200+ variants across 15 categories) |
| Reconnaissance | `recon_subdomains`, `recon_dns`, `recon_asn`, `recon_fingerprint`, `recon_robots`, `recon_ports`, `recon_whois` |
| Crypto / forensics | `cipher_detect`, `cipher_decode`, `cipher_xor`, `cipher_caesar`, `cipher_morse`, `hash_identify`, `hash_hashcat_mode`, `hash_crack`, `crypto`, `forensics`, `stego` |
| Web security | `websec_headers`, `websec_methods`, `websec_cors`, `websec_xss_smoke`, `websec_sqli_smoke`, `header_analysis`, `payload_gen` |
| API testing | `api_introspect_graphql`, `api_openapi_discover`, `api_rate_limit_probe`, `api_auth_bypass` |
| Shells | `bash`, `cmd`, `powershell`, `shell`, `git` |
| Network probing | `port_scan`, `dns_lookup`, `whois_tool`, `subdomain_tool` |

All offensive tools are gated behind the **YOLO** permission tier and
require explicit opt-in (`--yolo` flag, `/yolo` command, `Ctrl+Y`, or a
saved profile that enables it).

---

## 2. Permitted uses

You may use Gemi's security tools for any of the following, provided
your activity complies with all applicable laws and the terms of
service of any third parties involved:

- **Authorized penetration testing** of systems you own or are
  contractually engaged to test, with written permission from the system
  owner (typically a Statement of Work, MSA, or Rules of Engagement
  document).
- **Bug-bounty programs** that publish a clear scope. Stay strictly
  within scope. Out-of-scope assets are unauthorized targets.
- **Capture-the-Flag (CTF) competitions** running on infrastructure
  designated for offensive challenges.
- **Educational labs** that simulate vulnerable systems (e.g.
  HackTheBox, TryHackMe, OverTheWire, PortSwigger Web Security Academy,
  PentesterLab, your university's lab environment).
- **Defensive security work** — red-team exercises, purple-team drills,
  attack-surface mapping of your own infrastructure, threat-emulation,
  authorized incident-response simulations.
- **Security research** on your own equipment, published research where
  you have responsibly disclosed and received permission, or research
  on legally-purchased software you can analyze under your local fair-use
  / reverse-engineering laws.
- **Coursework, training, certifications** (OSCP, CEH, GPEN, etc.) using
  the lab environments those programs provide.

---

## 3. Prohibited uses

You may **not** use Gemi to:

- Scan, probe, or enumerate systems you do not own and have not received
  written authorization to test.
- Exploit vulnerabilities in production systems, websites, applications,
  APIs, or networks belonging to others without authorization.
- Crack passwords, hashes, or encryption belonging to others without
  authorization.
- Target individuals — harassment, stalking, doxxing, account takeover,
  identity theft.
- Disrupt services (DoS/DDoS), corrupt data, or cause loss of
  availability without authorization.
- Bypass authentication, authorization, paywalls, license checks, DRM,
  or similar controls without authorization.
- Engage in activity prohibited by applicable laws, including but not
  limited to:
  - **United States:** Computer Fraud and Abuse Act (CFAA, 18 U.S.C. § 1030),
    Wiretap Act, ECPA, DMCA anti-circumvention provisions, state computer
    crime statutes
  - **United Kingdom:** Computer Misuse Act 1990
  - **European Union:** Directive 2013/40/EU, GDPR (where personal data is
    involved)
  - **Canada:** Criminal Code Section 342.1
  - **Australia:** Cybercrime Act 2001
  - **Equivalent statutes in any jurisdiction where you, the target, or
    intermediate infrastructure is located**
- Engage in activity that violates the terms of service of a target
  platform, even if no specific law is broken.
- Distribute exploit payloads, recon results, or stolen data targeting
  systems you don't own.

---

## 4. Authorization checklist

Before running ANY offensive tool against a target you don't fully own:

1. **Written permission?** A signed Statement of Work, contract, or
   Rules of Engagement from the asset owner.
2. **Scope confirmed?** What hosts, IP ranges, applications, and APIs
   are in-scope? Get them in writing.
3. **Methods authorized?** Some engagements forbid certain techniques
   (DoS, social engineering, physical access, supply-chain).
4. **Time window agreed?** Most pentests have an authorized time window;
   running tools outside it can void authorization.
5. **Logging and chain of custody?** For professional work, document
   what you did, when, against what.
6. **Data handling agreed?** What happens to PII, credentials, or
   internal docs you find? Most engagements forbid exfiltration even
   for proof.
7. **Disclosure plan?** Coordinated disclosure, embargo period, who
   gets the report.

If you can't answer any of these, **stop**. Get the answers in writing
before running the tools.

---

## 5. Bug-bounty specifics

Bug-bounty programs are not blanket authorization to run any tool:

- **Read the program's policy in full.** Most programs forbid
  brute-forcing auth, running automated scanners, DoS-style testing,
  social engineering, or testing third-party services.
- **Scope is strict.** "*.example.com" does not include
  "internal.subsidiary-of-example.com" unless explicitly listed.
- **Aggressive scanning gets you banned.** Automated payload-spraying is
  typically prohibited even when the underlying vulnerability class is
  in-scope.
- **PII boundaries are real.** Stop testing the moment you reach actual
  user data. Don't view, exfiltrate, or share it.
- **Coordinate disclosure** through the program's documented channel.

---

## 6. AI-assisted offensive work — additional caveats

Gemi orchestrates LLMs that can chain tool calls automatically. This
amplifies the speed and scale at which security tools can be used. That
amplification cuts both ways:

- **Authorization scope must be enforced by you, the operator.** The LLM
  has no understanding of contractual scope. If an autopilot loop
  decides to "also check the parent domain," it will, and that may put
  you out of scope.
- **Audit logs.** Use Gemi's `/logs on` mode and keep `~/.gemi/logs/` for
  your own evidence chain. Hooks (`PreToolUse` / `PostToolUse`) can
  enforce additional gates.
- **Approval flow.** For client work, enable the interactive approval
  flow (`/approval on`) so risky tool calls require human y/n
  confirmation.
- **YOLO mode is opt-in.** It bypasses all permission tiers. Don't use
  it on engagements where every action must be reviewed.

---

## 7. No warranty, no liability

Gemi is licensed under Apache 2.0 (see [LICENSE](LICENSE)). The license
includes the standard "AS IS" disclaimer:

> Unless required by applicable law or agreed to in writing, Licensor
> provides the Work [...] on an "AS IS" BASIS, WITHOUT WARRANTIES OR
> CONDITIONS OF ANY KIND, either express or implied, including, without
> limitation, any warranties or conditions of TITLE, NON-INFRINGEMENT,
> MERCHANTABILITY, or FITNESS FOR A PARTICULAR PURPOSE.

The author and contributors:

- **Provide no warranty.** Tools may have bugs, may produce false
  positives or false negatives, may misbehave on edge cases.
- **Accept no liability for misuse.** If you use Gemi to commit a
  computer-crime offense, the consequences are entirely yours.
- **Accept no liability for damages.** If a tool damages a system you
  were authorized to test, that liability is allocated by your
  engagement contract — not by us.
- **Will not assist with unauthorized activity.** Issue reports,
  pull requests, or support requests describing unauthorized targets
  will be closed without engagement.

---

## 8. Reporting misuse

If you become aware of someone using Gemi for unauthorized activity
against your systems, please report it to law enforcement and to the
relevant platforms (GitHub abuse, hosting provider, etc.). We do not
have visibility into how downstream users employ this software.

---

## 9. Plain English summary

If you're here to learn security, build defensive tools, or do
authorized work — welcome. Read the docs, test against your own boxes
or a CTF, and have fun.

If you're here to break into someone else's stuff — this isn't the
project for that. Don't.

If you're not sure whether what you're about to do is authorized:
**don't do it. Ask first. Get it in writing.**

---

By using Gemi, you confirm you have read and accept this disclaimer.
