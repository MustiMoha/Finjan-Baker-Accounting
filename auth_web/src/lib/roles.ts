import type { AppContext, AppPermissions, ViewRole } from "../types/app";



export type PreviewRole = ViewRole | null;



export function effectiveViewRole(ctx: AppContext, preview: PreviewRole): ViewRole {

  return preview ?? ctx.view_role;

}



function isLeadAccountant(

  viewRole: ViewRole,

  orgRole: string,

  canApprove: boolean,

  legacyRole: string | null,

): boolean {

  const org = orgRole.toLowerCase();

  if (org === "owner") return true;

  if (viewRole === "admin") return true;

  if (org === "admin" || legacyRole === "admin") return true;

  return viewRole === "accountant" && canApprove;

}



export function effectivePermissions(ctx: AppContext, preview: PreviewRole): AppPermissions {

  const viewRole = effectiveViewRole(ctx, preview);

  const orgRole = ctx.membership.org_role;

  const canApprove = ctx.membership.can_approve;

  const legacy = ctx.legacy_role;

  const lead = isLeadAccountant(viewRole, orgRole, canApprove, legacy);



  const real = ctx.permissions;

  const isOwner = orgRole === "owner";

  const isOrgAdmin = orgRole === "owner" || orgRole === "admin";

  const isAccountant = viewRole === "accountant" || orgRole === "accountant";

  const canSettings = isOwner || isAccountant;

  const canApproveMembers =

    isOwner || ctx.membership.can_approve || orgRole === "admin";



  return {

    view_role: viewRole,

    is_lead_accountant: lead,

    can_dashboard: viewRole === "admin" || viewRole === "viewer",

    can_accountant_home: viewRole === "accountant",

    can_entries: viewRole === "admin" || viewRole === "accountant",

    can_approvals: viewRole === "admin" || (viewRole === "accountant" && lead),

    can_financials: viewRole === "admin" || viewRole === "accountant",

    can_audit: viewRole !== "viewer" && (viewRole === "admin" || (viewRole === "accountant" && lead)),

    can_org_settings: viewRole !== "viewer" && (isOwner || isOrgAdmin || Boolean(ctx.org.join_code)),

    can_members: isOwner || isOrgAdmin,

    can_member_approvals: (isOwner || viewRole === "admin" || lead) && canApproveMembers,

    can_forecast_config: lead && viewRole === "accountant",

    can_settings: canSettings,

    pending_member_count: real.pending_member_count,

    pending_entry_count: real.pending_entry_count,

  };

}



export function homePathForRole(viewRole: ViewRole): string {

  return viewRole === "accountant" ? "/accountant" : "/dashboard";

}

