import type { Conversation } from "@/lib/assistant-store";

/**
 * Assistant 会话匹配 helper（UI-M6.6）。
 *
 * 设计目标：
 *  - Home Hero 提问时如果存在"同一问题"或"高度相似"的最近会话，
 *    就跳到那条而不是新建一条；避免"提问一次就多一个会话"的污染。
 *  - 匹配规则要简单、可解释，**不要**用向量/embedding（前端无法承担）。
 *  - 必须"显式优于隐式"：高匹配才复用，低匹配/无匹配就新建。
 *
 * 匹配强度（由高到低）：
 *  1. EXACT     —— 完整 draft 文本归一化后相等
 *  2. PREFIX    —— draft 以 query 开头（>=8 字符，且 query 是 draft 的真前缀）
 *  3. CONTAINS  —— draft 包含 query（query 长度 >= 6，draft 长度 <= query * 3）
 *  4. NONE      —— 没有可复用会话
 *
 * 时间窗：只考虑 30 天内的会话；过期视为"冷数据"不命中。
 * 同强度匹配取 updatedAt 最大者。
 */

export type MatchStrength = "exact" | "prefix" | "contains" | "none";

export interface MatchResult {
  conversation: Conversation;
  strength: MatchStrength;
}

const WINDOW_MS = 30 * 24 * 60 * 60 * 1000; // 30 天

function normalize(s: string): string {
  return s
    .trim()
    .toLowerCase()
    .replace(/[\s\u3000]+/g, " ") // 合并空白（含全角空格）
    .replace(/[，。；、？！,.?!;:：]/g, ""); // 去掉中英常见标点
}

function withinWindow(conv: Conversation, now: number): boolean {
  return now - conv.updatedAt <= WINDOW_MS;
}

/**
 * 在 conversations 中查找与 query 最匹配的一条。
 * 返回 null 表示"没有可复用会话，应新建"。
 */
export function findMatchingConversation(
  conversations: Conversation[],
  rawQuery: string,
  now: number = Date.now(),
): MatchResult | null {
  const query = normalize(rawQuery);
  if (!query) return null;
  if (query.length < 2) return null; // 1 字符问号太容易误命中

  let bestExact: Conversation | null = null;
  let bestPrefix: Conversation | null = null;
  let bestContains: Conversation | null = null;

  for (const c of conversations) {
    if (!withinWindow(c, now)) continue;
    const draft = normalize(c.draft);
    if (!draft) continue;

    if (draft === query && (!bestExact || c.updatedAt > bestExact.updatedAt)) {
      bestExact = c;
      continue;
    }
    if (
      query.length >= 8 &&
      draft.startsWith(query) &&
      (!bestPrefix || c.updatedAt > bestPrefix.updatedAt)
    ) {
      bestPrefix = c;
      continue;
    }
    if (
      query.length >= 6 &&
      draft.includes(query) &&
      draft.length <= query.length * 3 &&
      (!bestContains || c.updatedAt > bestContains.updatedAt)
    ) {
      bestContains = c;
    }
  }

  if (bestExact) return { conversation: bestExact, strength: "exact" };
  if (bestPrefix) return { conversation: bestPrefix, strength: "prefix" };
  if (bestContains) return { conversation: bestContains, strength: "contains" };
  return null;
}
