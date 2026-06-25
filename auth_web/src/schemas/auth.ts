import { z } from "zod";

export const signInSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});

export const registerSchema = z
  .object({
    fullName: z.string().trim().min(1, "Enter your name").max(120, "Name is too long"),
    email: z.string().trim().email("Enter a valid email address"),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .max(128, "Password is too long"),
    confirmPassword: z.string().min(1, "Confirm your password"),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match",
    path: ["confirmPassword"],
  });

export const createOrgSchema = z.object({
  name: z.string().trim().min(2, "Organization name must be at least 2 characters"),
  jobTitle: z.string().trim().min(1, "Enter your role title (e.g. CFO, Controller)"),
});

export const joinOrgSchema = z.object({
  joinCode: z
    .string()
    .trim()
    .toUpperCase()
    .length(6, "Join code must be 6 characters")
    .regex(/^[A-Z0-9]+$/, "Join code must be letters and numbers only"),
  jobTitle: z.string().trim().min(1, "Enter your role title"),
});

export type SignInValues = z.infer<typeof signInSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type CreateOrgValues = z.infer<typeof createOrgSchema>;
export type JoinOrgValues = z.infer<typeof joinOrgSchema>;

export type MembershipGate = "none" | "pending" | "rejected" | "active";
