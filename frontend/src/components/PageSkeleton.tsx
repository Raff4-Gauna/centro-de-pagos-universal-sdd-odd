import Skeleton from "@mui/material/Skeleton";

// First load of a full screen (07 §2): MUI Skeleton laid out like the real content, so nothing
// jumps when the data arrives. Used by every route's loading.tsx.
export type PageSkeletonVariant = "table" | "form" | "detail";

export const TABLE_SKELETON_ROWS = 6;
export const FORM_SKELETON_FIELDS = 4;
export const DETAIL_SKELETON_FIELDS = 6;

const ROW_HEIGHT = 52;
const INPUT_HEIGHT = 56;

function TableSkeleton() {
  return (
    <div className="tw-flex tw-flex-col tw-gap-2">
      <Skeleton variant="rectangular" height={INPUT_HEIGHT} data-skeleton="header" />
      {Array.from({ length: TABLE_SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} variant="rectangular" height={ROW_HEIGHT} data-skeleton="row" />
      ))}
    </div>
  );
}

function FormSkeleton() {
  return (
    <div className="tw-flex tw-max-w-xl tw-flex-col tw-gap-4">
      {Array.from({ length: FORM_SKELETON_FIELDS }, (_, index) => (
        <div key={index} className="tw-flex tw-flex-col tw-gap-1" data-skeleton="field">
          <Skeleton variant="text" width="30%" />
          <Skeleton variant="rounded" height={INPUT_HEIGHT} />
        </div>
      ))}
      <Skeleton variant="rounded" width={120} height={40} data-skeleton="action" />
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="tw-grid tw-grid-cols-1 tw-gap-4 md:tw-grid-cols-2">
      {Array.from({ length: DETAIL_SKELETON_FIELDS }, (_, index) => (
        <div key={index} className="tw-flex tw-flex-col tw-gap-1" data-skeleton="field">
          <Skeleton variant="text" width="40%" />
          <Skeleton variant="text" width="70%" />
        </div>
      ))}
    </div>
  );
}

const BODIES = { table: TableSkeleton, form: FormSkeleton, detail: DetailSkeleton } as const;

export function PageSkeleton({ variant }: Readonly<{ variant: PageSkeletonVariant }>) {
  const Body = BODIES[variant];
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Cargando"
      data-variant={variant}
      className="tw-flex tw-flex-col tw-gap-6 tw-p-4"
    >
      <Skeleton variant="text" width="35%" height={40} data-skeleton="title" />
      <Body />
    </div>
  );
}
