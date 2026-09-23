import React from 'react';
import { PlaceholderScreen } from '../components/states/PlaceholderScreen';

/**
 * FIX BEFORE MERGE (independent review of PR #332): Home's "Not well?"
 * button had no destination at all. The real triage flow
 * (`TRIAGE_RED_FLAG` on the run stream, backed by
 * `app.safety.not_feeling_well`) is real, safety-relevant work this
 * checkpoint does not build — a false, unfinished version of it here
 * would be worse than this honest placeholder, which at least never
 * leaves the tap going nowhere.
 */
export default function NotWell() {
  return (
    <PlaceholderScreen
      title="Not well?"
      line="This isn't built yet. If this is urgent, use your phone's own emergency call."
    />
  );
}
