"""The feed (E21, backend).

`models` holds the tables: `FeedItem` (a card, immutable, rendered from a State snapshot),
`Source` (the allowlist), `SearchJob` (a self-search the engine runs for him), `Engagement`
(what he did with a card) and `FeedPage` (the last page rendered, for the offline launch).
`items` is the one way an item is written: the lines come from `app.delivery.strings`, pass
`app.safety.plain_words.verify`, and the row is stamped with its State by
`app.state.service.render_from_state`; an item that fails either is not created.
`compose` reads State and the record and makes today's items. `rank` orders them — a red
flag first, then now, today, the gate, story, learning — with the caps, the quiet hours and
the cursor. `engagement` writes what he did back as an Event and, for "not for me", a
preference Fact that State folds in. `search` runs a SearchJob through the `Searcher` and
`Compressor` ports (`compress`) against allowlisted sources only.
"""
