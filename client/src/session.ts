/** One signed-in account: the token pair, and renewing it.
 *
 * The access token lives only in memory. The refresh token is kept in a
 * TokenStore the app chooses (the studio: the tab's sessionStorage; the
 * listener app: the phone's secure storage), and is never sent anywhere but
 * /auth/refresh and /auth/logout.
 */

import { type Api, ApiError, HTTP_UNAUTHORIZED, type Registration } from "./api.ts";
import type { TokenPair } from "./schema.ts";

const SESSION_ENDED_DETAIL = "Your session has ended. Sign in again.";

/** Where the refresh token survives a restart of the page or app. */
export interface TokenStore {
  read(): string | null;
  write(token: string | null): void;
}

/** The calls a session makes itself. */
export type SessionApi = Pick<Api, "login" | "register" | "refresh" | "logout">;

export class Session {
  private readonly api: SessionApi;
  private readonly store: TokenStore;
  private accessToken: string | null = null;
  private refreshToken: string | null;
  // One renewal at a time: refresh tokens rotate, and presenting a used one
  // twice looks like theft to the API, which then revokes the whole session.
  private renewal: Promise<string> | null = null;

  constructor(api: SessionApi, store: TokenStore) {
    this.api = api;
    this.store = store;
    this.refreshToken = store.read();
  }

  get canRestore(): boolean {
    return this.refreshToken !== null;
  }

  async signIn(email: string, password: string): Promise<void> {
    this.keep(await this.api.login(email, password));
  }

  async register(registration: Registration): Promise<void> {
    this.keep(await this.api.register(registration));
  }

  /** Signed in again from the stored refresh token, if it still works. */
  async restore(): Promise<boolean> {
    if (this.refreshToken === null) return false;
    try {
      await this.renew();
      return true;
    } catch {
      return false; // expired or revoked: the user signs in again
    }
  }

  async signOut(): Promise<void> {
    const token = this.refreshToken;
    this.clear();
    if (token === null) return;
    await this.api.logout(token).catch(() => {
      // Signed out here either way; the API expires the session on its own.
    });
  }

  /** Run `action` with a valid access token, renewing it once if the API
   * says it has expired. */
  async authorized<T>(action: (accessToken: string) => Promise<T>): Promise<T> {
    const token = this.accessToken ?? (await this.renew());
    try {
      return await action(token);
    } catch (error) {
      const isExpired = error instanceof ApiError && error.status === HTTP_UNAUTHORIZED;
      if (!isExpired) throw error;
      return action(await this.renew());
    }
  }

  private renew(): Promise<string> {
    this.renewal ??= this.exchange().finally(() => {
      this.renewal = null;
    });
    return this.renewal;
  }

  private async exchange(): Promise<string> {
    if (this.refreshToken === null) throw new ApiError(HTTP_UNAUTHORIZED, SESSION_ENDED_DETAIL);
    try {
      return this.keep(await this.api.refresh(this.refreshToken));
    } catch (error) {
      const isRejected = error instanceof ApiError && error.status === HTTP_UNAUTHORIZED;
      if (!isRejected) throw error; // offline: keep the token and try later
      this.clear();
      throw new ApiError(HTTP_UNAUTHORIZED, SESSION_ENDED_DETAIL);
    }
  }

  private keep(pair: TokenPair): string {
    this.accessToken = pair.access_token;
    this.refreshToken = pair.refresh_token;
    this.store.write(pair.refresh_token);
    return pair.access_token;
  }

  private clear(): void {
    this.accessToken = null;
    this.refreshToken = null;
    this.store.write(null);
  }
}
