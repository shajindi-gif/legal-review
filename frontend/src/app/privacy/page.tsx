import { PolicyShell } from "@/components/legal/policy-shell";
import { siteInfo } from "@/lib/site";

const contact = siteInfo.contactEmail
  ? siteInfo.contactEmail
  : "（联系方式待补充）";

export default function PrivacyPage() {
  return (
    <PolicyShell title="隐私政策">
      <p>
        本隐私政策说明「{siteInfo.name}」（以下简称“我们”）如何收集、使用、存储和保护您在使用本网站及服务（{siteInfo.domain}
        ）过程中提供的个人信息。我们仅收集为实现服务所必需的信息，并依法保护您的个人信息权益。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">一、我们收集哪些信息</h2>
      <ul className="list-disc pl-5">
        <li>
          <strong>账号信息</strong>：注册或登录时提供的手机号、邮箱地址、用户名、姓名、所在单位，以及您自行设置的密码（密码以加密形式存储，不以明文保存）。
        </li>
        <li>
          <strong>验证信息</strong>：为验证手机号或邮箱归属而生成的验证码与验证记录（用于登录、换绑等安全校验）。
        </li>
        <li>
          <strong>业务内容</strong>：您上传的待审查文件及其内容、审查任务、审查结果与报告、您提交的反馈与评价。
        </li>
        <li>
          <strong>使用与设备信息</strong>：登录记录、IP 地址、浏览器类型（User-Agent）、Cookie 等用于保障账号与系统安全的信息。
        </li>
        <li>
          <strong>订单信息</strong>（仅在您使用付费服务时）：订单、支付状态及开票所需信息。
        </li>
      </ul>

      <h2 className="text-lg font-semibold text-gray-900">二、我们如何使用这些信息</h2>
      <ul className="list-disc pl-5">
        <li>提供、运行与改进合法性审查服务，并展示您的审查任务与报告；</li>
        <li>管理账号、验证身份、保障登录与数据安全、进行风险与滥用防护；</li>
        <li>响应您的请求、提供客户支持与必要的通知；</li>
        <li>在您使用付费服务时完成订单、支付处理与开票；</li>
        <li>满足法律法规要求或履行法定义务。</li>
      </ul>

      <h2 className="text-lg font-semibold text-gray-900">三、我们与谁共享信息</h2>
      <p>我们不会出售您的个人信息。仅在以下必要情形下与第三方发生数据流转：</p>
      <ul className="list-disc pl-5">
        <li>
          <strong>模型服务商</strong>：为实现 AI 审查，您的文件内容可能发送至我们所选用的模型服务商（如 DeepSeek、阿里云通义千问等）进行处理；
        </li>
        <li>
          <strong>短信与邮件服务商</strong>：用于发送验证码或通知；
        </li>
        <li>
          <strong>支付服务商</strong>（仅付费时）：用于完成支付；
        </li>
        <li>
          <strong>法律要求</strong>：依据法律法规、监管或司法机关的合法要求提供必要信息。
        </li>
      </ul>

      <h2 className="text-lg font-semibold text-gray-900">四、AI 处理说明</h2>
      <p>
        本站的审查结果由人工智能模型辅助生成，仅供您参考，<strong>不构成正式法律意见</strong>。
        最终判断与决策应由具备相应资质的人员结合实际情况进行人工复核。我们不承诺 AI
        输出绝对准确、完整或无遗漏，也不保证第三方模型服务商对数据的留存政策。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">五、存储与保留</h2>
      <p>
        我们将您的信息存储于用于提供服务的服务器与数据库中，并采取必要的技术与组织措施保护信息安全。我们仅在实现本政策所述目的所必需的期限内保留您的信息，法律法规另有规定的除外。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">六、您的权利</h2>
      <p>
        您有权访问、更正、删除您的个人信息，撤回同意，并对账户进行注销。相关请求可通过下方联系方式提出，我们将在合理的期限内响应。
      </p>

      <h2 className="text-lg font-semibold text-gray-900">七、联系我们</h2>
      <p>
        如您对本政策或个人信息处理有任何疑问，请通过以下方式与我们联系：{contact}
        。本政策如发生变更，我们将在本页面更新并标注生效日期。
      </p>
    </PolicyShell>
  );
}