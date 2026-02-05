import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

// Extend session types to include idToken
declare module "next-auth" {
    interface Session {
        idToken?: string;
        user: {
            id?: string;
            name?: string | null;
            email?: string | null;
            image?: string | null;
        };
    }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers: [
        Google({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
            authorization: {
                params: {
                    // Request ID token for backend verification
                    access_type: "offline",
                    prompt: "consent",
                },
            },
        }),
    ],
    pages: {
        signIn: "/login",
    },
    callbacks: {
        // Capture ID token from Google OAuth
        async jwt({ token, account }) {
            if (account?.id_token) {
                token.idToken = account.id_token;
            }
            return token;
        },
        // Add user info and idToken to session
        async session({ session, token }) {
            if (token.sub) {
                session.user.id = token.sub;
            }
            // Expose idToken for API calls
            if (token.idToken && typeof token.idToken === 'string') {
                session.idToken = token.idToken;
            }
            return session;
        },
        // Control access - MVP: allow all Google users
        async signIn({ user, account, profile }) {
            // For production, add email whitelist or domain check here
            // Example: return profile?.email?.endsWith("@company.com") ?? false
            return true;
        },
    },
    // Use JWT for session (works well with Edge/Middleware)
    session: {
        strategy: "jwt",
    },
})

