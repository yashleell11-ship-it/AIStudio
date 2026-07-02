"use client";

import { createContext, useContext } from "react";

const ScrollContainerContext = createContext<HTMLElement | null>(null);

export function ScrollContainerProvider({
  container,
  children,
}: {
  container: HTMLElement | null;
  children: React.ReactNode;
}) {
  return (
    <ScrollContainerContext.Provider value={container}>{children}</ScrollContainerContext.Provider>
  );
}

export function useScrollContainer(): HTMLElement | null {
  return useContext(ScrollContainerContext);
}
