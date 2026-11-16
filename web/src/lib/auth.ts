// Sign-in with Keycloak (ADR-006) through the authorization code flow with PKCE. The
// sign-in page itself is Keycloak's; this app only starts it and reads the token.
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { setTokenProvider } from "./api";

// Public settings (an issuer URL and a public client ID), not secrets. The defaults are
// the local stack's (infra/docker-compose.yml); a deploy sets the VITE_ variables.
const authority = import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8080/realms/home-base";
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID ?? "home-base-web";

export const CALLBACK_PATH = "/signed-in";

let manager: UserManager | null = null;

export function userManager(): UserManager {
  manager ??= new UserManager({
    authority,
    client_id: clientId,
    redirect_uri: `${window.location.origin}${CALLBACK_PATH}`,
    post_logout_redirect_uri: window.location.origin,
    response_type: "code",
    scope: "openid profile",
    automaticSilentRenew: true,
    // Session storage: the token is gone when the tab closes, and never in localStorage.
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  });
  return manager;
}

export function installTokenProvider(): void {
  setTokenProvider(async () => {
    const user = await userManager().getUser();
    return user && !user.expired ? user.access_token : null;
  });
}
