import { PolicyShell } from "@/components/legal/policy-shell";
import { siteInfo } from "@/lib/site";

const contact = siteInfo.contactEmail
  ? siteInfo.contactEmail
  : "（联系方式待补充）";

export default function TermsPage() {
  return (
    <PolicyShell title="服务条款">
      <p>
        欢迎使用「{siteInfo.name}」。在使用本网站及服务（{siteInfo.domain}
        ）前，请仔细阅读并同意本服务条款。您注册或使用本服务，即表示已阅读、理解并同意本条款。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">一、服务内容</h2>
      <p>
        我们提供面向行政规范性文件等文本的智能合法性审查辅助服务，包括文档上传解析、AI
        辅助审查、法规依据检索与审查报告生成等功能。服务具体范围与可用功能可能随版本更新而调整。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">二、AI 辅助性质与免责说明</h2>
      <p>
        本服务提供的审查结果由人工智能模型辅助生成，<strong>仅供参考，不构成正式法律意见</strong>，
        不能替代具备资质人员的专业判断与人工复核。我们不对 AI 输出的准确性、完整性作出保证。
        任何基于服务结果作出的决策及其后果，由使用者自行承担。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">三、账号使用规范</h2>
      <ul className="list-disc pl-5">
        <li>您应妥善保管账号及登录凭据，对账号下的活动负责；</li>
        <li>您不得利用本服务从事违法违规活动，不得上传侵犯他人合法权益的内容；</li>
        <li>您应保证所提供信息的真实性、准确性与合法性。</li>
      </ul>

      <h2 className="text-lg font-semibold text-gray-900">四、知识产权</h2>
      <p>
        本网站及其软件、界面、商标、文档等内容的知识产权归我们或相应权利人所有。您上传的内容及其权利仍归您所有，您授予我们仅为提供服务所必需的存储与处理权限。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">五、费用</h2>
      <p>
        部分功能可能需要付费。具体价格、计费周期与退改规则以购买时页面展示为准。我们有权在提前通知后调整收费规则。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">六、服务的变更与终止</h2>
      <p>
        我们可能因产品更新、安全或合规原因变更、暂停或终止部分服务。如您违反本条款或法律法规，我们有权中止或终止为您提供服务。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">七、适用法律与争议解决</h2>
      <p>
        本条款的订立、效力与解释适用中华人民共和国法律。因本条款产生的争议，双方应友好协商解决；协商不成的，提交有管辖权的人民法院处理。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">八、联系我们</h2>
      <p>如您对本条款有任何疑问，请通过以下方式与我们联系：{contact}。</p>
    </PolicyShell>
  );
}