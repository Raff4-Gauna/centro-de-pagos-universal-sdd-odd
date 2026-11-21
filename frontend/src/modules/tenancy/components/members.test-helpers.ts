import type { Member } from "../hooks/useMembers";
import { json } from "./branches.test-helpers";

// Fixtures of "Colaboradores": the rows follow the contract (`OrganizationMember` of
// specs/_contracts/openapi.yaml), with the `allowed_actions` and `assignable_roles` the backend
// computes, so the screen is checked against what the backend sends, never against a role.
export const ME: Member = {
  id: "9f8e7d6c-5b4a-4392-8170-6f5e4d3c2b1a",
  user: { id: "0a0b0c0d-1e1f-4a2b-8c3d-4e5f6a7b8c9d", email: "yo@acme.test", name: "Yo Mismo" },
  role: "owner",
  status: "active",
  ended_reason: null,
  created_at: "2026-11-01T12:00:00Z",
  allowed_actions: ["member.change_role", "member.leave"],
  assignable_roles: ["admin", "operator", "viewer"],
};

export const ANA: Member = {
  id: "3c4d5e6f-7a8b-4c9d-8e0f-1a2b3c4d5e6f",
  user: { id: "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e", email: "ana@acme.test", name: "Ana Pérez" },
  role: "operator",
  status: "active",
  ended_reason: null,
  created_at: "2026-11-02T12:00:00Z",
  allowed_actions: ["member.change_role", "member.revoke"],
  assignable_roles: ["admin", "viewer"],
};

// Another owner an admin may not touch: the backend brings no action for that row.
export const OTRO: Member = {
  id: "4d5e6f7a-8b9c-4d0e-9f1a-2b3c4d5e6f7a",
  user: { id: "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f", email: "otro@acme.test", name: "" },
  role: "owner",
  status: "active",
  ended_reason: null,
  created_at: "2026-11-03T12:00:00Z",
  allowed_actions: [],
  assignable_roles: [],
};

export const EX: Member = {
  id: "5e6f7a8b-9c0d-4e1f-8a2b-3c4d5e6f7a8b",
  user: { id: "3d4e5f6a-7b8c-4d9e-8f0a-1b2c3d4e5f6a", email: "ex@acme.test", name: "Ex Colega" },
  role: "viewer",
  status: "revoked",
  ended_reason: "left",
  created_at: "2026-10-01T12:00:00Z",
  allowed_actions: [],
  assignable_roles: [],
};

export function memberPage(results: readonly Member[]): Response {
  return json({ count: results.length, next: null, previous: null, results });
}

// The members the fake backend keeps for one company, filtered as `?status=` asks.
export function membersAnswer(request: Request, members: readonly Member[]): Response {
  const status = new URL(request.url).searchParams.get("status") ?? "active";
  return memberPage(members.filter((member) => member.status === status));
}
