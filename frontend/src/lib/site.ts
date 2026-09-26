// 站点合规信息（经营主体 / 备案 / 联系方式 / 政策生效日）。
//
// ⚠️ 以下字段均为【待确认】占位，需运营方核实后填入正式值后方可对外发布。
// 在填写前，页脚与政策页面会自动显示「主体信息待补充」，不会把占位值冒充为正式信息。
// 填入正式值后，全站 footer / 隐私政策 / 用户协议 / Cookie 政策自动生效。

export const siteInfo = {
  // 品牌
  name: "智审 · LegaReview",
  domain: "legalai86.com.cn",

  // 经营主体（待确认）
  legalEntityName: "", // 例："北京某某科技有限公司"
  unifiedSocialCreditCode: "", // 统一社会信用代码（用于开票落款）
  officeAddress: "", // 办公地址

  // 备案（待确认）
  icpRecord: "", // 例："京ICP备2025xxxxxx号-1"
  icpSecurityRecord: "", // 例："京公网安备110101xxxxxxxx号"

  // 联系方式（待确认）
  contactEmail: "", // 例："legal@legalai86.com.cn"
  contactPhone: "", // 例："010-xxxxxxx"

  // 政策生效日期（待确认）
  policyEffectiveDate: "", // 例："2026-08-26"
} as const;

/** 是否已填写经营主体（用于判断是否展示正式落款 vs 待补充提示）。 */
export const hasLegalEntity = () => Boolean(siteInfo.legalEntityName);

/** 取政策生效日，未填则用今天（仅用于草稿展示，正式发布前须填写确认）。 */
export const effectiveDateLabel = () =>
  siteInfo.policyEffectiveDate || "（待确认，正式发布前填写）";