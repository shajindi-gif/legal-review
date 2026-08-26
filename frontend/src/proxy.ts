import { NextResponse, type NextRequest } from "next/server";

/**
 * 路由层守卫（Next.js 16：middleware 已重命名为 proxy）。
 * 无 auth cookie（lr_token）时将受保护路由重定向到 /login。
 * token 在客户端登录时由 lib/auth.ts 同步写入 cookie，供此处的服务端读取。
 */
const PROTECTED = [
  "/dashboard",
  "/upload",
  "/review",
  "/report",
  "/admin",
  "/notifications",
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );
  if (!isProtected) {
    return NextResponse.next();
  }

  const token = request.cookies.get("lr_token")?.value;
  if (!token) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/upload/:path*",
    "/review/:path*",
    "/report/:path*",
    "/admin/:path*",
    "/assistant/:path*",
    "/tasks/:path*",
    "/reports/:path*",
    "/documents/:path*",
    "/notifications/:path*",
    "/dashboard",
    "/upload",
    "/admin",
    "/assistant",
    "/tasks",
    "/reports",
    "/documents",
    "/notifications",
  ],
};
