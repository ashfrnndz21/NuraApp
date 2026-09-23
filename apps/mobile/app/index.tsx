import { Redirect } from 'expo-router';

/**
 * The golden path's own entry (master spec §38 Phase 2): Welcome first,
 * always — never straight to Home. A returning, already-signed-in
 * profile's fast path back to Home belongs to a persisted-session check
 * this checkpoint does not add yet (C6 will tell you if that gap still
 * shows against an acceptance item).
 */
export default function Index() {
  return <Redirect href="/welcome" />;
}
