"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * Redirect from old /arena/hubs/[hubId] route to new /arena/groups/[hubId].
 * This preserves any bookmarks or links pointing to the old Discord-clone routes.
 */
export default function HubRedirectPage() {
  const params = useParams();
  const router = useRouter();
  const hubId = params.hubId as string;

  useEffect(() => {
    router.replace(`/arena/groups/${hubId}`);
  }, [hubId, router]);

  return null;
}
