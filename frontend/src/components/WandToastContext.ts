import { createContext, useContext } from "react";

export const WandToastContext = createContext<(message: string) => void>(() => {});

export function useWandToast(): (message: string) => void {
  return useContext(WandToastContext);
}
