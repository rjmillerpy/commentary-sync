/** Listening without an account: a guest token, fetched when first needed
 * and fetched again when the API says it has run out. It lives only in
 * memory, so a restarted app is a new guest (the API stores nothing about
 * guests either). The same `authorized` shape as Session's, so hooks don't
 * care which they have. */

import { type Api, ApiError, HTTP_UNAUTHORIZED } from "./api.ts";

export type GuestApi = Pick<Api, "guestToken">;

export class GuestPass {
  private readonly api: GuestApi;
  private token: string | null = null;
  // One request at a time: several hooks start at once on opening a stream.
  private fetching: Promise<string> | null = null;

  constructor(api: GuestApi) {
    this.api = api;
  }

  /** Run `action` with a guest token, getting a new one once if the API
   * says it has expired. */
  async authorized<T>(action: (accessToken: string) => Promise<T>): Promise<T> {
    const token = this.token ?? (await this.fetch());
    try {
      return await action(token);
    } catch (error) {
      const isExpired = error instanceof ApiError && error.status === HTTP_UNAUTHORIZED;
      if (!isExpired) throw error;
      this.token = null;
      return action(await this.fetch());
    }
  }

  private fetch(): Promise<string> {
    this.fetching ??= this.api
      .guestToken()
      .then(({ access_token }) => {
        this.token = access_token;
        return access_token;
      })
      .finally(() => {
        this.fetching = null;
      });
    return this.fetching;
  }
}
