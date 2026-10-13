"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/client";

export function useSignedMedia(assetId: string | null | undefined) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let current = true;
    setUrl(null);
    setError(false);
    if (assetId) {
      apiRequest<{ signed_url: string }>(`/assets/${assetId}`)
        .then((media) => { if (current) setUrl(media.signed_url); })
        .catch(() => { if (current) setError(true); });
    }
    return () => { current = false; };
  }, [assetId]);

  return { url, error };
}
