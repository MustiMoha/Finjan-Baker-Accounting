import { Translated } from "./Translated";

/** Inline field label or short UI copy (e.g. "Status:"). */
export function Label({ text, className }: { text: string; className?: string }) {
  return <Translated text={text} className={className} />;
}
