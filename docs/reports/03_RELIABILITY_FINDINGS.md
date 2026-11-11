# Reliability findings

## Repairs verified in LAB

- DATA-04 now stages the web alert, outbox and rule transition atomically. Capacity rejection and persistence failures preserve the prior published state. Actual tmpfs ENOSPC and SIGKILL recovery passed.
- A real SQLite trigger abort reproduced a local Task event/outbox inconsistency. The repaired Task path commits its rule state with the event and jobs. The final focused regression passes.
- Web, Gateway and desktop persist sending state before dispatch. Interrupted sends and ambiguous responses become `delivery_unknown` and retain their IDs. Legacy exhausted attempts are held during recovery.
- The explicitly started OPC UA collector waits the configured interval after completing the full round. This avoids compressing receipt spacing when a read itself consumes time.
- Gateway ACK-loss coverage confirms retry deduplication and exact event/digest acknowledgement after durable commit. Reader Core ran 59 assertions in a network-disabled Linux container.

## Delivery contract

Gateway ACK and Telegram acceptance have separate fields and evidence. Definitive API rejections may enter failed or retry-pending state according to the existing policy. Ambiguous outcomes remain held. The legacy web retry action requires explicit duplicate-risk acknowledgement. The desktop and Gateway recovery tests establish retention, without a general operator resend workflow for every held job.

An explicit resend after an unknown outcome may deliver the same event twice. Exactly-once external delivery is unproven. API acceptance also does not establish that a person read a message.

## Fault coverage and limits

The recorded tests cover offline/retry, ACK loss, duplicate events, capacity rejection, pre-commit faults, post-rename uncertainty, corrupt web state, pending restart, failed SQLite outbox insertion, interrupted sends and real ENOSPC. Physical power loss, actual Windows COM cancellation and shutdown, actual field traffic and real Telegram remain unverified. Corrupt web state is retained and startup is blocked. This does not establish recovery for every possible SQLite corruption.

The bounded backpressure implementation differs from the historical proposal for a new overflow backlog. No overflow subsystem was added. Producers must handle the explicit 503 response. No data-loss claim extends beyond the recorded fault model.
