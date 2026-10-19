import { Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/common";
import { Button } from "@/components/ui/button";

export default function NotFoundPage() {
  return (
    <EmptyState
      icon={Compass}
      title="Page not found"
      description="The page you're looking for doesn't exist."
      action={
        <Button asChild variant="outline">
          <Link to="/">Back to dashboard</Link>
        </Button>
      }
    />
  );
}
