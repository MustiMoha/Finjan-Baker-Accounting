import type { AuthError } from "@supabase/supabase-js";

/** Map Supabase Auth errors to clearer sign-in / sign-up messages. */
export function formatAuthError(error: AuthError | Error): string {
  const auth = error as AuthError;
  const code = (auth.code || "").toLowerCase();
  const msg = (auth.message || error.message || "").trim();

  if (code === "email_not_confirmed" || msg.toLowerCase().includes("email not confirmed")) {
    return "Confirm your email before signing in. Check your inbox and spam folder for the verification link.";
  }
  if (code === "invalid_credentials" || msg.toLowerCase().includes("invalid login credentials")) {
    return "Invalid email or password. If you just registered, confirm your email first, then try again.";
  }
  if (code === "user_already_registered" || msg.toLowerCase().includes("already registered")) {
    return "An account with this email already exists. Sign in or reset your password.";
  }
  if (code === "signup_disabled" || msg.toLowerCase().includes("signup is disabled")) {
    return "New sign-ups are disabled. Contact your administrator.";
  }
  if (code === "email_address_invalid") {
    return "That email address is not allowed. Use a real email address (not a test domain).";
  }
  if (code === "over_email_send_rate_limit" || msg.toLowerCase().includes("rate limit")) {
    return "Too many emails sent. Wait a few minutes or configure custom SMTP in Supabase.";
  }
  if (code === "weak_password") {
    return msg || "Choose a stronger password (at least 6 characters).";
  }
  return msg || "Authentication failed";
}
