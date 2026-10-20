import type { TokenStore } from "@commentary-sync/client/session";

/** A refresh-token store in memory, standing in for sessionStorage. */
export class MemoryStore implements TokenStore {
  constructor(public token: string | null = null) {}
  read(): string | null {
    return this.token;
  }
  write(token: string | null): void {
    this.token = token;
  }
}
