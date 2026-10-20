import { REFRESH_TOKEN_KEY, Session, tabStorage } from "@/lib/session";
import { FakeApi, PAIR, PAIR_2 } from "../_fakeApi";
import { MemoryStore } from "../_memoryStore";

// The session's behaviour is tested with the shared client (client/test).
// Here: that the studio's session calls the studio's API, and tab storage.

beforeEach(() => {
  new FakeApi()
    .on("POST", "/auth/login", { status: 200, body: PAIR })
    .on("POST", "/auth/register", { status: 201, body: PAIR })
    .on("POST", "/auth/refresh", { status: 200, body: PAIR_2 })
    .on("POST", "/auth/logout", { status: 204 })
    .install();
});

test("the studio's session signs in through the studio's API and keeps the token for a reload", async () => {
  const store = new MemoryStore();
  const session = new Session(store);
  expect(session.canRestore).toBe(false);
  await session.signIn("fan@example.com", "pw");
  expect(store.token).toBe("refresh-1");
  expect(session.canRestore).toBe(true);
});

describe("tab storage", () => {
  afterEach(() => {
    jest.restoreAllMocks();
    window.sessionStorage.clear();
  });

  test("keeps the refresh token in sessionStorage, and removes it", () => {
    tabStorage.write("refresh-1");
    expect(window.sessionStorage.getItem(REFRESH_TOKEN_KEY)).toBe("refresh-1");
    expect(tabStorage.read()).toBe("refresh-1");
    tabStorage.write(null);
    expect(tabStorage.read()).toBeNull();
  });

  test("blocked storage reads as empty and ignores writes", () => {
    const blocked = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    jest.spyOn(Storage.prototype, "getItem").mockImplementation(blocked);
    jest.spyOn(Storage.prototype, "setItem").mockImplementation(blocked);
    expect(tabStorage.read()).toBeNull();
    expect(() => tabStorage.write("refresh-1")).not.toThrow();
  });
});
