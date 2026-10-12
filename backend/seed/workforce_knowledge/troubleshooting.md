kb-synthetic-workforce-v1
Synthetic Household Troubleshooting
1.0
## Evidence freshness
Synthetic training procedure only. Identify the customer and authorised ticket before reading operational data. State the measurement timestamp and source. If measurements are old, missing or unreachable, request fresh telemetry and state that the current condition is unknown. A customer complaint is reported evidence, not a measured equipment state.
## Speed profile mismatch
Compare the subscribed download and upload rates with the applied provisioning profile. Compare a wired Internet speed test with those rates. If the applied profile differs from the authorised subscription, propose synchronisation through the provisioning adapter, subject to staff approval. Synchronisation must reapply the existing subscription; it must not upgrade the plan. Capture a new wired speed test after execution and report whether service improved. The current MVP does not implement the synchronisation action, so escalate when the tool is unavailable.
## Weak wifi coverage
Compare wired throughput with the affected client's Wi-Fi measurements, including the associated radio, band, RSSI, SNR and link rates. Good wired throughput and degraded client measurements support investigating wireless coverage. Check placement, distance and obstructions before proposing a configuration change. RSSI alone does not establish a root cause; thresholds depend on equipment and the service requirement.
## Wifi interference
Compare retries, packet loss, SNR and disconnect counts with a fresh radio/channel scan. High retries despite a strong received signal support investigating interference, but do not prove it. If a channel change is justified, propose a channel supported by the radio and regulatory domain and obtain approval. Preserve the previous configuration and compare new measurements after the change.
## Optical loss
Check whether the ONU reports a LOS alarm and whether other services are affected. A powered router can maintain local Wi-Fi while its upstream Internet connection is down. An unavailable optical reading is unknown rather than zero dBm. Router rebooting does not repair a broken optical path. Check the approved optical procedure and escalate a persistent optical fault for appropriate field investigation.
## Voice registration
Distinguish subscription status from operational registration status. When Internet works but voice is unregistered, obtain the registration error and verify the voice provisioning through an authorised adapter. Keep service passwords out of chat, transcripts and troubleshooting evidence. Escalate when credentials or a supported provisioning tool are unavailable.
## Iptv multicast
Distinguish an active TV subscription from an operational stream. Check the expected VLAN, set-top-box connectivity, multicast membership and stream errors. When Internet and voice are healthy but multicast join fails, investigate TV-specific provisioning. Broad router resets or unrelated Internet speed changes are not justified by this evidence.
## Recovery and approval
When current measurements are healthy, clarify whether the customer still has a problem and investigate the reported time window. Do not claim an action resolved a fault without new evidence. Read-only checks may run within the staff member's authorised scope. Reboot and configuration changes require explicit approval for the exact target and parameters, followed by measurement and an audit record.
