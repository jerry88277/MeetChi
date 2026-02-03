import NextAuth from "next-auth"
import Google from "next-auth/providers/google"

export const { handlers, signIn, signOut, auth } = NextAuth({
    providers: [
        Google({
            clientId: process.env.GOOGLE_CLIENT_ID!,
            clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        }),
    ],
    pages: {
        signIn: "/login",
    },
    callbacks: {
        // Add user info to session
        async session({ session, token }) {
            if (token.sub) {
                session.user.id = token.sub;
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
