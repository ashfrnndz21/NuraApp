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
