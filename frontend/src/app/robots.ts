import type { MetadataRoute } from "next";
import { siteInfo } from "@/lib/site";

const BASE_URL = `https://${siteInfo.domain}`;

/** robots.txt（R2-3）：放行公开页，屏蔽登录后的业务与后台路径。 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/pricing", "/solutions/", "/privacy", "/terms", "/cookies"],
        disallow: [
          "/api/",
          "/dashboard",
          "/upload",
          "/review",
          "/report",
          "/tasks",
          "/documents",
          "/admin",
          "/notifications",
          "/account",
          "/login",
          "/register",
        ],
      },
    ],
    sitemap: `${BASE_URL}/sitemap.xml`,
    host: BASE_URL,
  };
}
