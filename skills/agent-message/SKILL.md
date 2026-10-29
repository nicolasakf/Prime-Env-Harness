---
name: agent-message
description: Message an agent's parent, siblings, or direct children through the daemon. Discover reachable agents with agent_observe.list_agents, then send direct text without spoofing sender identity.
---

# Agent Message

Send direct messages within the current agent's nuclear family through the
local daemon: parent, siblings, and direct children only. Roots are siblings.
The daemon derives your sender identity from the current session; do not try
to include a `from` field.

Call directly from the kernel:

```python
children = await rlm.list_subagents()
child = next((item for item in children if item.active_session_id), None)
if child is not None:
    receipt = await agent_message.send(
        "Please inspect the latest result.",
        receiver_role="child",
        receiver_name=child.session_name,
    )
    # Keep the child until this follow-up finishes so its result remains observable.
```

## API

- `await agent_observe.list_agents()` (agent-observe skill) is the roster: it
  lists the parent, siblings, and children this skill can reach, active or not,
  with the `relationship` and `sessionName` that `send` takes as
  `receiver_role` and `receiver_name`.
- `await agent_message.send(message, receiver_role="parent" | "sibling" | "child", receiver_name=None)` — sends one direct
  text message to one family member. Sending to an inactive or idle completed
  subagent wakes it and starts an ordinary follow-up turn in that same session
  and context.
  The child remains available only until its parent session closes. The daemon
  resolves `receiver_role` within the current agent family; `receiver_name` is
  required for siblings and children and omitted for the unique parent.
  `send("all", message)` broadcasts only to the family roster and returns
  `{receipts: [...]}` in roster order; successful entries are ordinary receipts
  and failed entries contain the target id and a short `error`. One failed delivery
  does not reject successful deliveries. Messages always use steering delivery so
  a busy target sees them during its active run. Returns a receipt with a
  `deliveryStatus` field: `"delivered"` means the message reached an idle target's
  context; `"queued"` means a steering message was accepted and will deliver when
  the target's current work allows (`send` does not block waiting for that).
  Delivered receipts carry `deliveredAt`, queued receipts carry `queuedAt`.

## Queued delivery

Messages that arrive while the target is busy wait in its queue. When the
target is next free, the `agentMessageMode` setting in `settings.json` decides
how they are delivered:

- `"all"` (default): every agent message already queued is delivered together as
  one turn. Each message keeps its own sender and text, in the order it was
  queued, so a parent with several children answers all ready replies in a
  single turn instead of one turn per reply. A reply that has not arrived yet
  never holds the others back.
- `"one-at-a-time"`: one turn per message.

The setting is read when a session starts, so a change applies to new sessions.

## Safety

- Do not delete a child immediately after `send`: delivered follow-ups may still
  be running and queued receipts have not run yet. Wait until observation shows
  the child is idle and its context is no longer needed before calling
  `await rlm.delete_subagent(child)`.
- Reach is limited to parent, siblings, and direct children; relay through an
  intermediate child instead of messaging grandchildren or cousins directly.
- Sender identity is daemon-derived and cannot be spoofed from Python.
- The daemon enforces message size, rate, and pending-queue limits before
  accepting delivery.
