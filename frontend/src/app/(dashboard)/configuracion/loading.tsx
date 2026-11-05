import { PageSkeleton } from "@/components/PageSkeleton";

// First load of Configuración (07 §2): a list-shaped skeleton, never a blank screen.
export default function SettingsLoading() {
  return <PageSkeleton variant="table" />;
}
