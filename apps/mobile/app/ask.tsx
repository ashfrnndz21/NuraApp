import { Redirect } from 'expo-router';

/**
 * There is no separate Ask screen (spec §9 / C5's own line: "the
 * composer expands in place, never a separate screen") — `AIComposer`
 * lives docked on Home. A caller that only has a route to push (a chip,
 * a deep link) lands here and goes straight to Home, where the composer
 * itself is.
 */
export default function Ask() {
  return <Redirect href="/home" />;
}
