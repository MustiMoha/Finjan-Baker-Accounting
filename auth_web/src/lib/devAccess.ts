/** Account allowed to use the sidebar role-preview switcher (testing only). */
export const ROLE_PREVIEW_EMAIL = "mlee5064@gmail.com";

export function canUseRolePreview(email: string | null | undefined): boolean {
  return email?.trim().toLowerCase() === ROLE_PREVIEW_EMAIL;
}
