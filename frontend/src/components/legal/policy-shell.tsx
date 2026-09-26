import Link from "next/link";
import type { ReactNode } from "react";
import {
  siteInfo,
  hasLegalEntity,
  effectiveDateLabel,
} from "@/lib/site";

/** 政策类页面（隐私政策 / 服务条款 / Cookie 政策）的统一外壳。 */
export function PolicyShell({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              法
            </div>
            <span className="text-lg font-semibold text-brand-700">
              {siteInfo.name}
            </span>
          </Link>
          <Link href="/" className="text-sm text-gray-600 hover:text-brand-700">
            返回首页
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        <p className="mt-2 text-sm text-gray-500">
          生效日期：{effectiveDateLabel()}
        </p>

        {!hasLegalEntity() && (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            本页面为待审阅草稿：经营主体、备案号与联系方式尚未填写，
            正式对外发布前须由运营方核对并补充，且需经法律专业意见审核。
          </div>
        )}

        <article className="prose-sm mt-6 space-y-6 text-[15px] leading-7 text-gray-700">
          {children}
        </article>
      </main>

      <footer className="border-t border-gray-200 bg-white py-6">
        <div className="mx-auto max-w-3xl px-6 text-center text-sm text-gray-500">
          <p>{siteInfo.name}</p>
          {siteInfo.legalEntityName && <p>{siteInfo.legalEntityName}</p>}
          {siteInfo.icpRecord && (
            <p>
              <a
                href="https://beian.miit.gov.cn/"
                target="_blank"
                rel="noreferrer"
                className="hover:text-brand-700"
              >
                {siteInfo.icpRecord}
              </a>
            </p>
          )}
          {siteInfo.icpSecurityRecord && <p>{siteInfo.icpSecurityRecord}</p>}
        </div>
      </footer>
    </div>
  );
}