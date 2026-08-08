"""Host-side session client (Phase 2).

Drives one Managed Agents session per scan: uploads the document as a mounted
resource, sends the job manifest, answers the agent's custom tool calls
(cache_lookup, persist_result) with host-side credentials, and collects the
event log for the trace forwarder (Phase 4) and the L2 evals.
"""
