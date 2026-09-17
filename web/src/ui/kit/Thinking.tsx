// This local stand-in (message bubble, source chips, looked-at line, trace step) has been
// retired: the shared components it stood in for landed in `./Conversation` when PR #240's
// `main` work was merged into this branch. `Ask.tsx` now imports `MessageBubble`, `LookedAt`
// and `StepTrace` from `./Conversation` (re-exported by `./index`) instead of this file. Kept
// as an empty module, rather than deleted, because this session's tooling could not remove a
// tracked file; nothing imports from it directly any more.
export {};
