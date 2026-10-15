// 站点合规信息（经营主体 / 备案 / 联系方式 / 政策生效日）。
// 填入正式值后，全站 footer / 隐私政策 / 用户协议 / Cookie 政策自动生效。

export const siteInfo = {
  // 品牌
  name: "智审 · LegalReview",
  domain: "legalai86.com.cn",

  // 经营主体（2026-10-15 运营方提供）
  legalEntityName: "上海衍策引擎人工智能科技有限公司",
  unifiedSocialCreditCode: "", // 统一社会信用代码（用于开票落款，待补）
  officeAddress: "", // 办公地址（待补）

  // 备案（2026-10-15 运营方提供）
  icpRecord: "沪ICP备2026045851号-4",
  icpSecurityRecord: "", // 公安备案号（待补）

  // 联系方式（2026-10-15 运营方提供）
  contactEmail: "yanceai@163.com",
  contactPhone: "",

  // 政策生效日期（待确认）
  policyEffectiveDate: "", // 例："2026-08-26"
} as const;

/** 是否已填写经营主体（用于判断是否展示正式落款 vs 待补充提示）。 */
export const hasLegalEntity = () => Boolean(siteInfo.legalEntityName);

/** 取政策生效日，未填则用今天（仅用于草稿展示，正式发布前须填写确认）。 */
export const effectiveDateLabel = () =>
  siteInfo.policyEffectiveDate || "（待确认，正式发布前填写）";