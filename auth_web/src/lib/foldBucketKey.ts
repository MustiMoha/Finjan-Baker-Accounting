/** Case-insensitive key for bucket / category labels (matches backend fold_bucket_key). */
export function foldBucketKey(name: string): string {
  return (name || "")
    .trim()
    .normalize("NFKC")
    .replace(/\s+/g, " ")
    .toLowerCase();
}

export function pickLongerDisplayName(a: string, b: string): string {
  const aa = (a || "").trim();
  const bb = (b || "").trim();
  return bb.length > aa.length ? bb : aa;
}
