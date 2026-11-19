"use client";

import Avatar from "@mui/material/Avatar";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { ErrorNotice } from "@/components/ErrorNotice";
import { PageSkeleton } from "@/components/PageSkeleton";

import { type Me, useMe } from "../hooks/useMe";

// "Mi perfil" (spec §14, design.md §3.4, 07 §5.3): name, email and avatar of the Google account,
// read only and without language (Q-115). Loading is the detail skeleton; an error is an alert
// whose "Reintentar" repeats `GET /api/me` (07 §2), with the fixed title of its code (C-08).
export const PROFILE_TITLE = "Mi perfil";
export const PROFILE_NOTE = "Los datos vienen de tu cuenta de Google";

// Up to two initials of the name; without one, the first letter of the email.
export function initialsOf(displayName: string, email: string): string {
  const words = displayName.trim().split(/\s+/).filter(Boolean);
  const letters = words.slice(0, 2).map((word) => word[0]!);
  return (letters.length > 0 ? letters.join("") : email.slice(0, 1)).toUpperCase();
}

// The avatar of Google, only over https; otherwise (or if it does not load) the initials.
export function UserAvatar({ me, size }: Readonly<{ me: Me; size: number }>) {
  const src = me.avatar_url?.startsWith("https://") ? me.avatar_url : undefined;
  return (
    <Avatar
      src={src}
      alt=""
      sx={{ width: size, height: size, fontSize: size * 0.4 }}
      slotProps={{ img: { referrerPolicy: "no-referrer" } }}
    >
      {initialsOf(me.display_name, me.email)}
    </Avatar>
  );
}

function Heading() {
  return (
    <Typography component="h1" variant="h5">
      {PROFILE_TITLE}
    </Typography>
  );
}

function ProfileDetails({ me }: Readonly<{ me: Me }>) {
  const name = me.display_name.trim();
  return (
    <Paper variant="outlined" className="tw-flex tw-max-w-xl tw-flex-col tw-gap-4 tw-p-6">
      <div className="tw-flex tw-items-center tw-gap-4">
        <UserAvatar me={me} size={64} />
        <Typography variant="h6" component="p" className="tw-break-all">
          {name || me.email}
        </Typography>
      </div>
      <dl className="tw-grid tw-grid-cols-[max-content_1fr] tw-gap-x-6 tw-gap-y-2">
        {name ? (
          <>
            <Typography component="dt" variant="body2" color="text.secondary">
              Nombre
            </Typography>
            <Typography component="dd" variant="body1">
              {name}
            </Typography>
          </>
        ) : null}
        <Typography component="dt" variant="body2" color="text.secondary">
          Email
        </Typography>
        <Typography component="dd" variant="body1" className="tw-break-all">
          {me.email}
        </Typography>
      </dl>
      <Typography variant="body2" color="text.secondary">
        {PROFILE_NOTE}
      </Typography>
    </Paper>
  );
}

export function ProfileCard() {
  const me = useMe();
  if (me.isPending) {
    return <PageSkeleton variant="detail" />;
  }
  return (
    <div className="tw-flex tw-flex-col tw-gap-4">
      <Heading />
      {me.isError ? (
        <ErrorNotice
          message={me.error.title}
          onRetry={() => void me.refetch()}
          retrying={me.isFetching}
        />
      ) : (
        <ProfileDetails me={me.data} />
      )}
    </div>
  );
}
