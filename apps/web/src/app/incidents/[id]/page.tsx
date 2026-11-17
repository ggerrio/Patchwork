"use client";

import { useParams } from "next/navigation";

import { CommandCenter } from "@/components/CommandCenter";

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  return <CommandCenter initialIncidentId={params.id} />;
}
