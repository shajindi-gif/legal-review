import { PolicyShell } from "@/components/legal/policy-shell";
import { siteInfo } from "@/lib/site";

const contact = siteInfo.contactEmail
  ? siteInfo.contactEmail
  : "（联系方式待补充）";

export default function CookiesPage() {
  return (
    <PolicyShell title="Cookie 政策">
      <p>
        本政策说明「{siteInfo.name}」（{siteInfo.domain}
        ）如何以及为何使用 Cookie 与类似技术。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">一、什么是 Cookie</h2>
      <p>
        Cookie 是网站存储在您浏览器中的小型文本文件，用于识别登录状态、保障安全并提升使用体验。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">二、我们使用的 Cookie</h2>
      <ul className="list-disc pl-5">
        <li>
          <strong>必要 Cookie</strong>：用于维持您的登录会话、校验身份与防止跨站请求伪造，是服务正常运行所必需的；
        </li>
        <li>
          <strong>偏好 Cookie</strong>：用于记住您的界面偏好设置，以提升使用体验。
        </li>
      </ul>
      <p>我们目前不使用用于跨站行为追踪的第三方广告或分析 Cookie。</p>

      <h2 className="text-lg font-semibold text-gray-900">三、如何管理 Cookie</h2>
      <p>
        您可以通过浏览器设置删除或禁用 Cookie。请注意，禁用必要 Cookie
        可能导致登录等核心功能无法正常使用。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">四、联系我们</h2>
      <p>如您对本政策有任何疑问，请通过以下方式与我们联系：{contact}。</p>
    </PolicyShell>
  );
}