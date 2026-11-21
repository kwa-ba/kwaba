import "next-auth";
import "next-auth/jwt";
import type { TwoFactorError } from "@/lib/api/auth/two-factor";

declare module "next-auth" {
  interface Session {
    error?: "RefreshAccessTokenError";
    /** Refusal of the last back-office second factor code (ADR-028), only in the answer to update(). */
    twoFactorError?: TwoFactorError;
    user: {
      id: string;
      name: string;
      email: string;
      image?: string | null;
      role: string;
    };
  }

  interface User {
    accessToken?: string;
    refreshToken?: string;
    role?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    refreshToken?: string;
    accessTokenExpires?: number;
    role?: string;
    userId?: string;
    error?: "RefreshAccessTokenError";
    twoFactorError?: TwoFactorError;
  }
}
