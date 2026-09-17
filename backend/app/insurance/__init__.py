"""The insurance module: what he is covered by, as he or his chief typed it.

The one place an insurance identifier is kept (CLAUDE.md: identity-card numbers never outside
this module, and here only when a guarantee letter needs one — which is not yet). Every
policy reference and claim reference stays here: never logged, never on a card body, never in
analytics, never in a message.

    `insurer`   the one line the emergency card says (E13-01): the insurer's name and a
                policy reference, typed on a yes.
    `policy`    the fuller record (E13-03): every policy on the profile — insurer, policy
                reference, type, who is covered, start and renewal dates, status, what it
                covers in his own words, and when the premium is due.
    `claim`     a claim against one policy, for one visit already on the spine: its status,
                and the papers behind it (whatever is already attached to that visit —
                nothing here opens a second upload path).
    `relevance` given an upcoming visit, whether his cover is likely to apply and what to
                bring — never whether it *is* covered; that is always the insurer's or the
                clinic's word, and every line here says so.

A policy and a claim are read and written under `Scope.MONEY`, the door already reserved for
"your insurance letters" and already preset to nobody but a chief
(`app.keys.scopes.ROLE_SCOPES`, `app.consent.texts.SCOPE_WORDS`): a helper, a viewer, an
emergency-only key and a clinic key do not see them; the owner, a steward before a claim, and
a chief the family named do. `insurer` stays on `Scope.EMERGENCY`, which every role holds,
because it is what a stranger needs to say at a hospital desk — a different question, on
purpose, from what a policy pays for.
"""
