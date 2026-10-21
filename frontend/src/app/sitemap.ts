import type { MetadataRoute } from "next";
import { siteInfo } from "@/lib/site";

const BASE_URL = `https://${siteInfo.domain}`;

/**
 * 站点地图（R2-3）：仅收录可公开访问、无需登录的页面。
 * 受保护的业务页面（/dashboard、/review、/admin 等）由 robots.txt 排除。
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE_URL}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE_URL}/pricing`, lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    {
      url: `${BASE_URL}/solutions/sifaju`,
      lastModified: now,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    { url: `${BASE_URL}/privacy`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${BASE_URL}/terms`, lastModified: now, changeFrequency: "yearly", priority: 0.3 },
    { url: `${BASE_URL}/cookies`, lastModified: now, changeFrequency: "yearly", priority: 0.2 },
  ];
}
