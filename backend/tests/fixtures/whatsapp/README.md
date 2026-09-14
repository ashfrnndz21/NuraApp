# WhatsApp fixtures

`media.json` is what the fixture provider (`app/channels/whatsapp/provider.py`) serves when
the channel fetches a media id: a content type and a label. The bytes served are the same
placeholder the paper fixtures use (`tests/paper.py`), so a forwarded `lipid-panel-photo`
reads as the lipid report in `tests/fixtures/paper/` and comes back as its review card. No
image is committed, and no provider is called.
