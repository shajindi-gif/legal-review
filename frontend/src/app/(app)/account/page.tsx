import type { Metadata } from "next";
import { AccountCenter } from "@/components/account/AccountCenter";

export const metadata: Metadata = { title: "账户设置 · 智审 LegalReview" };

export default function AccountPage() {
  return <AccountCenter />;
}
