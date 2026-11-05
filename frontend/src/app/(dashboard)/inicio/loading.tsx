import { PageSkeleton } from "@/components/PageSkeleton";

// First load of Inicio (07 §2): a skeleton, never a blank screen.
export default function HomeLoading() {
  return <PageSkeleton variant="detail" />;
}
