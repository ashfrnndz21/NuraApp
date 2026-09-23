import { errorStateFromRefusal, ApiRefusalError } from '../refusals';

describe('errorStateFromRefusal — refusal → ErrorState, never an HTTP code or a class name on screen', () => {
  test('a named refusal (OutOfScope) gets its own plain-words copy', () => {
    const props = errorStateFromRefusal({ refusal: 'OutOfScope', scope: 'medicines', status: 403 });
    expect(props.title).not.toMatch(/OutOfScope/);
    expect(props.why).not.toMatch(/403|OutOfScope/);
    expect(props.why).toContain('medicines');
    expect(props.ctaLabel).toBe('Try again');
  });

  test('an unnamed refusal still gets honest, generic plain-words copy — never the raw class name', () => {
    const props = errorStateFromRefusal({ refusal: 'SomeFutureRefusalClass', status: 409 });
    expect(props.title).not.toMatch(/SomeFutureRefusalClass|409/);
    expect(props.why).not.toMatch(/SomeFutureRefusalClass|409/);
    expect(props.why.length).toBeGreaterThan(0);
  });

  test('every known refusal message is free of HTTP codes and class names', () => {
    const cases = [
      { refusal: 'OutOfScope', scope: 'ask', status: 403 },
      { refusal: 'NoConsent', status: 403 },
      { refusal: 'NotTheirsToRead', status: 403 },
      { refusal: 'NotTheOwner', status: 403 },
      { refusal: 'Unreachable', status: 500 },
    ];
    for (const c of cases) {
      const props = errorStateFromRefusal(c);
      expect(props.title).not.toMatch(/\b\d{3}\b/);
      expect(props.why).not.toMatch(/\b\d{3}\b/);
    }
  });

  test('A-013: a wrong sign-in code gets its own calm line, not the generic fallback', () => {
    const props = errorStateFromRefusal({ refusal: 'WrongCode', status: 401 });
    expect(props.title).not.toBe("We couldn't do that right now."); // the generic fallback's own title
    expect(props.title.toLowerCase()).toContain('code');
    expect(props.why).not.toMatch(/401|WrongCode/);
  });

  test('an expired or locked sign-in challenge each get their own line too', () => {
    const expired = errorStateFromRefusal({ refusal: 'ChallengeExpired', status: 401 });
    const locked = errorStateFromRefusal({ refusal: 'ChallengeLocked', status: 401 });
    expect(expired.title).not.toBe(locked.title);
    expect(expired.title).not.toBe("We couldn't do that right now.");
    expect(locked.title).not.toBe("We couldn't do that right now.");
  });
});

describe('ApiRefusalError', () => {
  test('carries the refusal, scope and status straight off the response body', () => {
    const err = new ApiRefusalError({ refusal: 'OutOfScope', scope: 'visits', status: 403 });
    expect(err).toBeInstanceOf(Error);
    expect(err.refusal).toBe('OutOfScope');
    expect(err.scope).toBe('visits');
    expect(err.status).toBe(403);
  });
});
