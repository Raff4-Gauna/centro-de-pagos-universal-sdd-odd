"use client";

import { useRevokeOtherSessions } from "../hooks/useRevokeOtherSessions";
import { ConfirmDialog } from "./RevokeSessionDialog";

// Confirmation of "Cerrar las demás" (AC-IDA-33, design.md §3.4, texts of Q-129 a). On the `204`
// the dialog closes and the list is read again; there is no success message.
export const REVOKE_OTHERS_TEXTS = {
  title: "¿Cerrar las demás sesiones?",
  body: "Los otros dispositivos van a tener que ingresar de nuevo con Google. Esta sesión sigue abierta.",
  confirm: "Cerrar las demás",
} as const;

export function RevokeOthersDialog({ onClose }: Readonly<{ onClose: () => void }>) {
  const revokeOthers = useRevokeOtherSessions();
  return (
    <ConfirmDialog
      title={REVOKE_OTHERS_TEXTS.title}
      body={REVOKE_OTHERS_TEXTS.body}
      confirmLabel={REVOKE_OTHERS_TEXTS.confirm}
      onConfirm={() => revokeOthers.mutate(undefined, { onSuccess: onClose })}
      onClose={onClose}
      busy={revokeOthers.isPending}
      error={revokeOthers.isError ? revokeOthers.error : null}
    />
  );
}
