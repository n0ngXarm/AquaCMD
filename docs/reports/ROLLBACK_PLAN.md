# AQUA COMMAND candidate rollback

1. Stop all capture and delivery workers for the isolated profile. Confirm they have exited before copying state.
2. Preserve private configuration, certificates, JSON state, SQLite including WAL/SHM where present, Reader spool, pending events, and ACK records together. Record hashes and run an integrity check on a copy. Keep the original protected.
3. Record every SENDING and DELIVERY_UNKNOWN item before reverting. Keep those records held. Never let an older worker replay an interrupted send until its outcome has been reviewed.
4. Revert the affected source commit on the candidate branch or select the prior unsigned package only in a disposable LAB. Do not restore a stale queue over newer acknowledged or pending events.
5. Re-run the old and new launcher against separate copies. Compare preserved event IDs, source sequences, ACK digests, queued counts, and settings before any proposed upgrade or downgrade.
6. Leave production rollback and reactivation to a separately approved deployment plan. No production custody or delivery guarantees follow from the container test.

## Candidate-specific boundaries

The final lifecycle test upgraded release 2 to 4 and removed release 4 in network-disabled Fedora 44/45 containers. Seeded config and SQLite retained their hashes and integrity. This is a narrow retention check. Full backup restoration and actual Reader spool recovery on Windows need separate acceptance.

Older release 3 and early release 4 artifacts may contain archival site references. They remain historical private evidence. Do not select them for distribution or restore a prior worker onto unresolved sending/unknown jobs. Source commit e466efe excludes the archival preview from the final Linux payload.
