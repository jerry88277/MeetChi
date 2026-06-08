import NextAuth from "next-auth"
import Google from "next-auth/providers/google"
import MicrosoftEntraId from "next-auth/providers/microsoft-entra-id"
import Credentials from "next-auth/providers/credentials"
import crypto from "crypto"

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

/** Mint a HS256 JWT signed with AUTH_SECRET — verified by backend verify_uat_token(). */
function mintUATToken(payload: Record<string, unknown>, secret: string): string {
    const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")
    const body = Buffer.from(JSON.stringify({
        ...payload,
        iss: "meetchi-uat",
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 8 * 3600,  // 8h
    })).toString("base64url")
    const sig = crypto
        .createHmac("sha256", secret)
        .update(`${header}.${body}`)
        .digest("base64url")
    return `${header}.${body}.${sig}`
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

// UAT Credentials provider — enabled via UAT_ENABLED=true env var.
// Accounts are stored server-side in UAT_USERS (JSON array, never exposed to client).
// Each UAT login mints a short-lived HS256 token verified by the backend.
if (process.env.UAT_ENABLED === "true") {
    type UATUser = { email: string; password: string; name: string }
    const uatUsers: UATUser[] = JSON.parse(process.env.UAT_USERS || "[]")

    providers.push(
        Credentials({
            id: "credentials",
            name: "測試帳號",
            credentials: {
                email: { label: "Email", type: "email" },
                password: { label: "密碼", type: "password" },
            },
            async authorize(credentials) {
                const user = uatUsers.find(
                    (u) => u.email === credentials.email && u.password === credentials.password
                )
                return user ? { id: user.email, email: user.email, name: user.name } : null
            },
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
            // UAT Credentials: mint a HS256 token the backend can verify.
            // Google/MS have real id_tokens; credentials provider has none.
            if (account?.provider === "credentials" && token.email && process.env.AUTH_SECRET) {
                token.idToken = mintUATToken(
                    { sub: token.sub ?? token.email, email: token.email, name: token.name },
                    process.env.AUTH_SECRET
                )
            }
            return token
        },
        // Expose idToken and provider to the session (used by API client)
        async session({ session, token }) {
            if (token.sub) session.user.id = token.sub
            // Explicitly propagate name/email so UAT credentials users show their own info,
            // not a stale Google session.
            if (token.name) session.user.name = token.name as string
            if (token.email) session.user.email = token.email as string
            if (token.idToken && typeof token.idToken === "string") {
                session.idToken = token.idToken
            }
            if (token.provider && typeof token.provider === "string") {
                session.provider = token.provider
            }
            return session
        },
        // Restrict sign-in to the allowed domain when AUTH_ALLOWED_DOMAIN is set.
        // UAT credentials users bypass this check (they may use non-company emails).
        async signIn({ user, account }) {
            if (account?.provider === "credentials") return true
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


