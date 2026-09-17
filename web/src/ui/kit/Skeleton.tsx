// This local stand-in `SkeletonCard` has been retired: the shared skeleton card it stood in
// for landed in `./Conversation` when PR #240's `main` work was merged into this branch.
// `HomeParts.tsx` now gets `SkeletonCard` from `./Conversation` (re-exported by `./index`).
// Kept as an empty module, rather than deleted, because this session's tooling could not
// remove a tracked file; nothing imports from it directly any more.
export {};
