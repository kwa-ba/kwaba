"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { onTwoFactorRequired } from "@/lib/two-factor-signal";
import { TWO_FACTOR_KEY, useTwoFactorStatus } from "../../hooks";
import TwoFactorPrompt from "./TwoFactorPrompt";
import TwoFactorSetup from "./TwoFactorSetup";
import { usePostponed } from "./postpone";
import { gateScreen, msBeforeExpiry } from "./rules";

// setTimeout takes at most 2^31 - 1 ms
const MAX_TIMEOUT = 2_147_483_647;

/**
 * Back-office and agents' space of an admin: nothing shows before the second factor is set up and verified
 * (ADR-028). Display only: the API refuses the requests on its own. Other accounts pass through.
 */
export default function TwoFactorGate({ children }: { children: React.ReactNode }) {
  const { data: session, status: sessionStatus } = useSession();
  const isAdmin = session?.user?.role === "admin";
  const { data: status, isLoading } = useTwoFactorStatus(isAdmin);
  const postponed = usePostponed();
  const queryClient = useQueryClient();
  const [now, setNow] = useState(() => Date.now());
  const [opened, setOpened] = useState(false);

  // A 403 two_factor_required during the session: the status is read again, and the code screen comes back
  useEffect(() => onTwoFactorRequired(() => {
    setNow(Date.now());
    queryClient.invalidateQueries({ queryKey: TWO_FACTOR_KEY });
  }), [queryClient]);

  // The code is asked again when the 12 hours are over, even without any request
  useEffect(() => {
    const ms = msBeforeExpiry(status, Date.now());
    if (ms === null) return;
    const timer = setTimeout(() => setNow(Date.now()), Math.min(ms + 1_000, MAX_TIMEOUT));
    return () => clearTimeout(timer);
  }, [status]);

  if (sessionStatus === "loading") return <div className="min-h-screen bg-canvas" />;
  const screen = gateScreen({ isAdmin, loading: isLoading, status, postponed, now });
  if (screen === "open" && !opened) setOpened(true);

  if (screen === "loading") return <div className="min-h-screen bg-canvas" />;
  if (screen === "setup") return <TwoFactorSetup email={session?.user?.email ?? ""} />;
  if (screen === "code") {
    // Expired during the session: the page stays underneath, untouched, and comes back after the code
    if (!opened) return <TwoFactorPrompt />;
    return (
      <>
        <div inert aria-hidden>{children}</div>
        <div className="fixed inset-0 z-200 overflow-y-auto"><TwoFactorPrompt /></div>
      </>
    );
  }
  return children;
}

