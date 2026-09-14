import { describe, expect, it, vi } from "vitest";
import { keyBytes, remindersState, turnOff, turnOn, type PushEnv } from "../../src/push/reminders";

/** RFC 8291's example application-server key: a P-256 point, 65 bytes, base64url. */
const KEY = "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8";
const ENDPOINT = "https://push.example.test/abc";

/** A phone that can take pushes: it counts every time it is asked, and remembers what it was
 *  subscribed with. `answer` is what it says when asked. */
function phone(answer: NotificationPermission = "granted") {
  let permission: NotificationPermission = "default";
  let subscribed = false;
  const asked = { count: 0 };
  const options: PushSubscriptionOptionsInit[] = [];
  const subscription = () =>
    ({
      endpoint: ENDPOINT,
      toJSON: () => ({ endpoint: ENDPOINT, keys: { p256dh: "p", auth: "a" } }),
      unsubscribe: async () => {
        subscribed = false;
        return true;
      },
    }) as unknown as PushSubscription;
  const registration = {
    pushManager: {
      getSubscription: async () => (subscribed ? subscription() : null),
      subscribe: async (given: PushSubscriptionOptionsInit) => {
        options.push(given);
        subscribed = true;
        return subscription();
      },
    },
  } as unknown as ServiceWorkerRegistration;
  const env: PushEnv = {
    permission: () => permission,
    requestPermission: async () => {
      asked.count += 1;
      permission = answer;
      return answer;
    },
    registration: async () => registration,
  };
  const backend = { subscribe: vi.fn(async () => ({})), forget: vi.fn(async () => undefined) };
  return { env, backend, asked, options };
}

describe("reminders on this phone", () => {
  it("reading whether they are on never asks the phone", async () => {
    const p = phone();
    expect(await remindersState(p.env)).toBe("off");
    expect(p.asked.count).toBe(0);
    expect(await remindersState(null)).toBe("unsupported");
  });

  it("a tap asks once, subscribes with the push key and tells the backend", async () => {
    const p = phone();
    expect(await turnOn(p.env, KEY, p.backend)).toBe("on");
    expect(p.asked.count).toBe(1);
    expect(p.options).toHaveLength(1);
    const [given] = p.options;
    expect(given?.userVisibleOnly).toBe(true);
    expect(new Uint8Array(given?.applicationServerKey as ArrayBuffer)).toEqual(new Uint8Array(keyBytes(KEY)));
    expect(p.backend.subscribe).toHaveBeenCalledWith({ endpoint: ENDPOINT, keys: { p256dh: "p", auth: "a" } });
    expect(await remindersState(p.env)).toBe("on");
  });

  it("a no from the phone subscribes nothing and tells the backend nothing", async () => {
    const p = phone("denied");
    expect(await turnOn(p.env, KEY, p.backend)).toBe("denied");
    expect(p.options).toHaveLength(0);
    expect(p.backend.subscribe).not.toHaveBeenCalled();
    expect(await remindersState(p.env)).toBe("denied");
  });

  it("stopping forgets the phone on the backend and in the browser", async () => {
    const p = phone();
    await turnOn(p.env, KEY, p.backend);
    expect(await turnOff(p.env, p.backend)).toBe("off");
    expect(p.backend.forget).toHaveBeenCalledWith(ENDPOINT);
    expect(await remindersState(p.env)).toBe("off");
  });

  it("the push key is the 65 bytes of a P-256 point", () => {
    const bytes = new Uint8Array(keyBytes(KEY));
    expect(bytes).toHaveLength(65);
    expect(bytes[0]).toBe(4);
  });
});
