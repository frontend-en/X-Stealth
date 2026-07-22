# Queue identity deduplication

## Problem

The queue API could return both a legacy item from `tweets.txt` and its managed state from `queue.jsonl` when they shared an ID. The frontend then rendered duplicate React keys and could not reliably reconcile the two rows.

## Contract

- `QueueService.list_items()` returns at most one item for each `QueueItem.id`.
- A managed `queue.jsonl` item supersedes a legacy `tweets.txt` item with the same ID.
- Items with distinct IDs remain in the response.
- Item ordering remains newest-first when timestamps are available.

## Acceptance criteria

1. A legacy `tweet-0001` and managed `tweet-0001` produce one API item.
2. The returned item contains the managed text and status.
3. The frontend queue receives unique IDs and emits no duplicate-key warning for this case.
4. No publishing or pipeline action is needed to validate the change.

## Compatibility and rollback

Existing managed state entries continue to use their current IDs. Rolling back consists of restoring the former `_load_items` implementation; no data migration is required.
