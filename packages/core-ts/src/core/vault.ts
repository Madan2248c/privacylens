/**
 * Session Vault for PrivacyLens (TypeScript).
 *
 * Stores token-to-value mappings scoped by session ID.
 */

export interface SessionVault {
  /** Store a token-value mapping for the given session. */
  store(sessionId: string, token: string, value: string): void;

  /**
   * Retrieve the value for a token in the given session.
   * @throws {Error} if the token does not exist in the session.
   */
  retrieve(sessionId: string, token: string): string;

  /** Remove all token-value mappings for the given session. */
  clear(sessionId: string): void;
}

/**
 * In-memory session vault. Always available with no extra dependencies.
 */
export class MemoryVault implements SessionVault {
  private readonly _data: Map<string, Map<string, string>> = new Map();

  store(sessionId: string, token: string, value: string): void {
    let session = this._data.get(sessionId);
    if (session === undefined) {
      session = new Map();
      this._data.set(sessionId, session);
    }
    session.set(token, value);
  }

  retrieve(sessionId: string, token: string): string {
    const session = this._data.get(sessionId);
    if (session === undefined || !session.has(token)) {
      throw new Error(`Token not found in session: ${token}`);
    }
    return session.get(token) as string;
  }

  clear(sessionId: string): void {
    this._data.delete(sessionId);
  }
}
