import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { Campaign } from "@/lib/types";

/** Duplicate, cancel and retry actions shared by the campaign list and detail pages. */
export function useCampaignActions() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [cancelTarget, setCancelTarget] = useState<Campaign | null>(null);

  const invalidate = () => queryClient.invalidateQueries();

  const duplicate = useMutation({
    mutationFn: (c: Campaign) => api.duplicateCampaign(c.id),
    onSuccess: (copy) => {
      toast.success("Campaign duplicated", { description: `“${copy.name}” was saved as a draft.` });
      invalidate();
      navigate(`/campaigns/${copy.id}/edit`);
    },
    onError: (e: Error) => toast.error("Couldn't duplicate campaign", { description: e.message }),
  });

  const cancel = useMutation({
    mutationFn: (c: Campaign) => api.cancelCampaign(c.id),
    onSuccess: (c) => {
      toast.success("Campaign cancelled", { description: `“${c.name}” will not be sent.` });
      setCancelTarget(null);
      invalidate();
    },
    onError: (e: Error) => {
      toast.error("Couldn't cancel campaign", { description: e.message });
      setCancelTarget(null);
      invalidate();
    },
  });

  const retry = useMutation({
    mutationFn: (c: Campaign) => api.retryFailed(c.id),
    onSuccess: (c) => {
      toast.success("Retrying failed deliveries", {
        description: `${c.runs.at(-1)?.job_count ?? ""} recipients queued for another attempt.`,
      });
      invalidate();
    },
    onError: (e: Error) => {
      toast.error("Couldn't start retry", { description: e.message });
      invalidate();
    },
  });

  const cancelDialog = (
    <Dialog open={!!cancelTarget} onOpenChange={(open) => !open && setCancelTarget(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Cancel this scheduled campaign?</DialogTitle>
          <DialogDescription>
            “{cancelTarget?.name}” will not be sent. If it has already started sending, it can no longer be cancelled.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setCancelTarget(null)}>
            Keep scheduled
          </Button>
          <Button variant="destructive" disabled={cancel.isPending} onClick={() => cancelTarget && cancel.mutate(cancelTarget)}>
            {cancel.isPending ? "Cancelling…" : "Cancel campaign"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { duplicate, cancel, retry, requestCancel: setCancelTarget, cancelDialog };
}
