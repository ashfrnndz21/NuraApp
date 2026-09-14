"""Scope enforcement. Every read of profile data goes through this package.

`resolve_key_context` is the only way to get a `KeyContext`, and `scoped_select` /
`scoped_new` are the only way to touch a row of profile data with one.
"""
