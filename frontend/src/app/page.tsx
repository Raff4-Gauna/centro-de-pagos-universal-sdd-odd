import { redirect } from "next/navigation";

// The root has no screen of its own: Inicio is the first screen of the Hub (07 §5.2).
export default function RootPage() {
  redirect("/inicio");
}
