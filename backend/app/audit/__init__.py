"""The audit trail: every read, every write and every share of one person's health graph.

`models` is the entry, `trail` is the one writer and the one query, and `access` is the pair
of doors that every service reaching profile data goes through so that no access can happen
without a line in the trail. The owner and his chief are the only readers.
"""
