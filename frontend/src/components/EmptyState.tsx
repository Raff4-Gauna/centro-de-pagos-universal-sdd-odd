import InboxOutlined from "@mui/icons-material/InboxOutlined";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

// Explicit empty state (07 §2): the load finished and there is nothing to show. Never an empty
// table or a blank screen; an optional suggested action ("Conectá tu primera integración").
export type EmptyStateProps = Readonly<{
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}>;

export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <section
      aria-label={title}
      className="tw-flex tw-flex-col tw-items-center tw-gap-3 tw-px-4 tw-py-12 tw-text-center"
    >
      <span aria-hidden="true" className="tw-text-text-secondary">
        {icon ?? <InboxOutlined fontSize="large" />}
      </span>
      <Typography component="h2" variant="h6">
        {title}
      </Typography>
      {description ? (
        <Typography variant="body2" color="text.secondary" className="tw-max-w-md">
          {description}
        </Typography>
      ) : null}
      {action ? <div className="tw-mt-2">{action}</div> : null}
    </section>
  );
}
