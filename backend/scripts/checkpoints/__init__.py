"""One module per checkpoint from here on, each exposing `run(base_url, dev_log) -> int`.

`scripts.checkpoint` dispatches to them by number; a module walks its scenario over HTTP
only, prints one ✓/✗ line per step, and returns the exit code. Checkpoints 2 to 6 still live
in `scripts.checkpoint` itself.
"""
