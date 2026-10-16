import { NextResponse, type NextRequest } from "next/server";

/**
 * 路由层守卫（Next.js 16：middleware 已重命名为 proxy）。
 * 1. 无 auth cookie（lr_token）时将受保护路由重定向到 /login。
 * 2. 为每个页面响应注入 Content-Security-Policy，并在请求头携带同一 nonce：
 *    Next.js 16 会从请求头 content-security-policy 中解析出 nonce 并注入到
 *    它自己渲染的 <script> 标签（见 node_modules/next/dist/server/app-render/
 *    get-script-nonce-from-header.js）。这样可对 inline script 启用 nonce 白名单，
 *    而不必放行 'unsafe-inline'，兼顾安全与 Next.js 客户端脚本。
 */
const PROTECTED = [
  "/dashboard",
  "/upload",
  "/review",
  "/report",
  "/admin",
  "/notifications",
  "/account",
];

function buildCspHeader(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'`,
    // React/Radix 有内联 style 属性与内联 <style>，无法逐条 nonce，保留 unsafe-inline
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    // 生产 API/SSE 走同源；ws/wss 仅本地 dev 热更新需要
    "connect-src 'self' ws: wss:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'self'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  // 每次请求随机 nonce；base64 编码保证符合 CSP nonce-source 语法
  const nonce = btoa(crypto.randomUUID());
  const csp = buildCspHeader(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("content-security-policy", csp);

  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED.some(
    (p) => pathname === p || pathname.startsWith(p + "/"),
  );

  if (!isProtected) {
    const res = NextResponse.next({ request: { headers: requestHeaders } });
    res.headers.set("Content-Security-Policy", csp);
    return res;
  }

  // UX 层守卫：读非凭证 hint cookie（登录后由 JS 写入的 "1"）。
  // 真正鉴权始终在后端 JWT（Authorization: Bearer），此处只做跳转优化。
  const hint = request.cookies.get("lr_hint")?.value;
  if (!hint) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname + (request.nextUrl.search || ""));
    return NextResponse.redirect(loginUrl);
  }

  const res = NextResponse.next({ request: { headers: requestHeaders } });
  res.headers.set("Content-Security-Policy", csp);
  return res;
}

export const config = {
  // 覆盖全部页面请求，排除 API、Next 静态资源与带扩展名的文件
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|.*\\..*).*)",
  ],
};