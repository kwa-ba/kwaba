import Credentials from "next-auth/providers/credentials";
import { ouvrirSession } from "@/lib/api/auth/connexion";

/**
 * Sign-in with the identity token given by Apple in the browser (ADR-045), checked by the API. The code lets the API
 * revoke the link when the account is deleted; it was obtained with `redirectUri`, which Apple asks again at the
 * exchange. Apple gives the names only at the very first sign-in.
 */
export const appleProvider = Credentials({
  id: "apple-id-token",
  name: "Apple",
  credentials: {
    idToken: { label: "Apple ID token", type: "text" },
    code: { label: "Apple authorization code", type: "text" },
    redirectUri: { label: "Return address", type: "text" },
    firstName: { label: "First name", type: "text" },
    lastName: { label: "Last name", type: "text" },
  },
  async authorize(credentials, request) {
    if (!credentials?.idToken) return null;
    return ouvrirSession(
      "/v1/auth/apple/",
      {
        identity_token: String(credentials.idToken),
        authorization_code: String(credentials.code ?? ""),
        redirect_uri: String(credentials.redirectUri ?? ""),
        first_name: String(credentials.firstName ?? ""),
        last_name: String(credentials.lastName ?? ""),
      },
      request,
    );
  },
});
