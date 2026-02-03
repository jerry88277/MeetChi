import { auth } from "@/auth"
import { NextResponse } from "next/server"

export default auth((req) => {
    const { nextUrl } = req
    const isLoggedIn = !!req.auth

    // Public routes that don't require authentication
    const publicRoutes = ["/", "/login", "/api/auth"]
    const isPublicRoute = publicRoutes.some(route =>
        nextUrl.pathname === route || nextUrl.pathname.startsWith("/api/auth")
    )

    // API routes (except auth) - let them handle their own auth
    const isApiRoute = nextUrl.pathname.startsWith("/api/") &&
        !nextUrl.pathname.startsWith("/api/auth")

    // Protected routes
    const isProtectedRoute = nextUrl.pathname.startsWith("/dashboard")

    // Redirect unauthenticated users to login
    if (isProtectedRoute && !isLoggedIn) {
        const loginUrl = new URL("/login", nextUrl.origin)
        loginUrl.searchParams.set("callbackUrl", nextUrl.pathname)
        return NextResponse.redirect(loginUrl)
    }

    // Redirect authenticated users away from login page
    if (nextUrl.pathname === "/login" && isLoggedIn) {
        return NextResponse.redirect(new URL("/dashboard", nextUrl.origin))
    }

    return NextResponse.next()
})

export const config = {
    matcher: [
        // Match all routes except static files and _next
        "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
    ],
}
