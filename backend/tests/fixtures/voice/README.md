# Voice fixtures

No audio is committed. Each file here is named by the sha256 of a placeholder byte string —
`b"nura-voice-placeholder:<label>\n"` (`backend/tests/voice.py`, and the same line in
`backend/scripts/checkpoints/cp11.py`) — and holds what the fixture transcriber
(`app/safety/transcribe.py`) heard on it: `{"text", "confidence", "language"}`. Bytes with no
file here are a note the transcriber cannot hear; the flow keeps the note, tells the family,
and asks him to say it again.

| Label | Digest | Heard | Confidence |
|---|---|---|---|
| `chest-pain` | `8304f39c86c0…` | 'I have chest pain' | 0.94 |
| `tired-today` | `96fac11f71fa…` | 'I feel tired today' | 0.91 |
| `dizzy-quite-a-lot` | `54ca8c2bbec8…` | 'dizzy, quite a lot, since this morning' | 0.9 |
| `sakit-dada` | `023ff271d8b2…` | 'dada saya sakit' | 0.88 |
