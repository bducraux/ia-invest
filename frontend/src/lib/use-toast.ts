import { useCallback, useState } from "react";
import type { Toast, ToastVariant } from "@/components/ui/toast";

export function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, variant: ToastVariant = "info", duration?: number) => {
    const id = Math.random().toString(36).substring(2, 9);
    const toast: Toast = { id, message, variant, duration };

    setToasts((prev) => [...prev, toast]);

    return id;
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback((message: string, duration?: number) => {
    return addToast(message, "success", duration);
  }, [addToast]);

  const error = useCallback((message: string, duration?: number) => {
    return addToast(message, "error", duration);
  }, [addToast]);

  const info = useCallback((message: string, duration?: number) => {
    return addToast(message, "info", duration);
  }, [addToast]);

  return { toasts, addToast, removeToast, success, error, info };
}
