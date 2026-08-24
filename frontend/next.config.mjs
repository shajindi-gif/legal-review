/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // 同一域名下:/api/* 自动代理到后端
  // 本地开发 -> 127.0.0.1:8889,Docker 部署 -> backend:8000 (容器网络名)
  // 部署时通过环境变量 BACKEND_URL 覆盖;本地默认走 127.0.0.1:8889
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8889";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  // Next.js 16 默认开启 Origin 校验,反代场景下需要明确放行公网域名
  // https://nextjs.org/docs/app/api-reference/config/next-config-js/allowedDevOrigins
  allowedDevOrigins: [
    "127.0.0.1:3080",
    "localhost:3080",
    "127.0.0.1:3000",
    "localhost:3000",
    "127.0.0.1:3081",
    "localhost:3081",
    "legalai86.com.cn",
    "www.legalai86.com.cn",
    // Cloudflare 临时域名(以 trycloudflare.com 结尾)
    "*.trycloudflare.com",
  ],
  // Server Actions origin 白名单(防止 CSRF)
  experimental: {
    serverActions: {
      allowedOrigins: [
        "127.0.0.1:3080",
        "localhost:3080",
        "127.0.0.1:3081",
        "localhost:3081",
        "legalai86.com.cn",
        "www.legalai86.com.cn",
        "*.trycloudflare.com",
      ],
    },
  },
  // SSE 长连接需要这些 header
  async headers() {
    return [
      {
        source: "/api/:path*",
        headers: [
          { key: "X-Forwarded-Proto", value: "https" },
        ],
      },
    ];
  },
};

export default nextConfig;
