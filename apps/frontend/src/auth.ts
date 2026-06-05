import NextAuth from "next-auth"
import Google from "next-auth/providers/google"
import MicrosoftEntraId from "next-auth/providers/microsoft-entra-id"

// Extend session types to include idToken and provider
declare module "next-auth" {
    interface Session {
        idToken?: string;
        provider?: string;
        user: {
            id?: string;
            name?: string | null;
            email?: string | null;
            image?: string | null;
        };
    }
}

const providers = [
    Google({
        clientId: process.env.GOOGLE_CLIENT_ID!,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        // Disable PKCE: Cloud Run exposes two URL aliases for the same service
        // (hash-based and project-number-based). PKCE stores a verifier cookie on
        // the domain that initiates sign-in, but Google always redirects back to the
        // registered callback URL (potentially a different domain), causing
        // "Invalid code verifier" errors. Using state-only check is safe for
        // server-side OAuth flows and avoids this cross-domain cookie mismatch.
        checks: ["state"],
        authorization: {
            params: {
                access_type: "offline",
                prompt: "consent",
            },
        },
    }),
]

// Microsoft Entra ID provider — enabled only when Azure AD App registration is complete.
// Required env vars (set in Cloud Run + local .env):
//   AUTH_MICROSOFT_ENTRA_ID_ID      = Azure App (client) ID
//   AUTH_MICROSOFT_ENTRA_ID_SECRET  = Azure App client secret
//   AUTH_MICROSOFT_ENTRA_ID_TENANT_ID = Azure tenant ID (e.g. chimei.com.tw tenant UUID)
if (process.env.AUTH_MICROSOFT_ENTRA_ID_ID) {
    providers.push(
        MicrosoftEntraId({
            clientId: process.env.AUTH_MICROSOFT_ENTRA_ID_ID!,
            clientSecret: process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET!,
            // tenantId is passed via issuer URL; the type definition omits it
            // but NextAuth resolves it from the OIDC discovery endpoint
            issuer: process.env.AUTH_MICROSOFT_ENTRA_ID_TENANT_ID
                ? `https://login.microsoftonline.com/${process.env.AUTH_MICROSOFT_ENTRA_ID_TENANT_ID}/v2.0`
                : "https://login.microsoftonline.com/common/v2.0",
        }) as never
    )
}

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers,
    pages: {
        signIn: "/login",
    },
    callbacks: {
        // Capture ID token + provider from OAuth response
        async jwt({ token, account }) {
            if (account?.id_token) {
                token.idToken = account.id_token
            }
            if (account?.provider) {
                token.provider = account.provider
            }
            return token
        },
        // Expose idToken and provider to the session (used by API client)
        async session({ session, token }) {
            if (token.sub) {
                session.user.id = token.sub
            }
            if (token.idToken && typeof token.idToken === "string") {
                session.idToken = token.idToken
            }
            if (token.provider && typeof token.provider === "string") {
                session.provider = token.provider
            }
            return session
        },
        // Restrict sign-in to the allowed domain when AUTH_ALLOWED_DOMAIN is set
        async signIn({ user }) {
            const allowedDomain = process.env.AUTH_ALLOWED_DOMAIN
            if (allowedDomain) {
                return user.email?.toLowerCase().endsWith(`@${allowedDomain.toLowerCase()}`) ?? false
            }
            return true
        },
    },
    session: {
        strategy: "jwt",
    },
})


